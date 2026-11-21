# ------------------------------------------------------------------------------
# Copyright (c) 2026 Adrian Pascut (ESLAMERA LIMITED). All rights reserved.
#
# LICENCE NOTICE:
# Permitted ONLY for free, non-commercial personal job-search use by Private
# Individuals. Any use, copying, or modification by a Commercial Entity—or for
# non-job-search purposes—requires prior written permission from the author.
#
# BREACH PENALTIES (Liquidated Damages):
# - Commercial Entity Breach: £100,000 per breach/deployment + legal fees.
# - Private Individual Breach: £10,000 per breach + legal fees.
#
# See the root LICENSE file for full legal terms, restrictions, and disclaimers.
# ------------------------------------------------------------------------------

import asyncio
import re
from datetime import datetime
from playwright.async_api import Page
from bs4 import BeautifulSoup

class JobExtractor:
    """Extracts every detail of ONE LinkedIn job. Knows nothing about search pages,
    pagination, scrolling lists or duplicate tracking (that is LinkedInBot's job)."""

    JOB_VIEW_PATTERN = re.compile(r'(\d{9,13})(?:\?|$|/)', re.IGNORECASE)
    def __init__(self, page: Page):
        self.page = page

    @classmethod
    def job_id_from_url(cls, url: str) -> str | None:
        """Returns the numeric LinkedIn job id contained in a URL, or None."""
        if not url:
            return None
        match = cls.JOB_VIEW_PATTERN.search(url)
        return match.group(1) if match else None

    @staticmethod
    def build_job_url(job_id: str) -> str:
        """Canonical job URL without tracking parameters."""
        return f"https://www.linkedin.com/jobs/view/{job_id}/"

    async def _extract_description(self) -> str:
        """
        Extracts full job description by finding the 'About the job' text anchor,
        traversing to its parent/grandparent level, and reading the entire underlying
        text content from all neighboring downstream DOM nodes (even if visually hidden).
        """
        try:
            # 1. Primary Attempt: Select all DOM nodes following the parent of 'About the job'
            # Uses text_content() instead of inner_text() to grab full text even if hidden/truncated by CSS
            parent_following_nodes = self.page.locator(
                "xpath=(//*[text()='About the job' or contains(text(), 'About the job')])[1]/parent::*/following-sibling::*"
            )
            anchor_xpath = (
                "(//*["
                "text()='About the job' or contains(text(), 'About the job') or "
                "text()='Job Summary' or contains(text(), 'Job Summary') or "
                "text()='Job Description' or contains(text(), 'Job Description')"
                "])[1]"
            )
            
            parent_following_nodes = self.page.locator(f"xpath={anchor_xpath}/parent::*/following-sibling::*")
            
            node_count = await parent_following_nodes.count()
            text_parts = []

            if node_count > 0:
                for i in range(node_count):
                    # text_content() reads directly from the DOM tree regardless of visual visibility
                    raw_node_text = await parent_following_nodes.nth(i).text_content()
                    if raw_node_text and raw_node_text.strip():
                        text_parts.append(raw_node_text.strip())

            description_text = "\n".join(text_parts)

            # 2. Fallback Attempt: Step up to grandparent level and grab downstream siblings
            if not description_text or len(description_text.strip()) < 20:
                grandparent_following_nodes = self.page.locator(f"xpath={anchor_xpath}/parent::*/parent::*/following-sibling::*")
                
                gp_node_count = await grandparent_following_nodes.count()
                text_parts = []

                if gp_node_count > 0:
                    for i in range(gp_node_count):
                        raw_node_text = await grandparent_following_nodes.nth(i).text_content()
                        if raw_node_text and raw_node_text.strip():
                            text_parts.append(raw_node_text.strip())
                            
                description_text = "\n".join(text_parts)

            if not description_text:
                return ""
            clean_text = description_text
            for prefix in ["About the job", "Job Summary", "Job Description"]:
                clean_text = clean_text.replace(prefix, "")
            # 3. Clean up UI residual text like section headers or "Show less" strings
            clean_text = description_text.replace("About the job", "").split("Show less")[0].strip()
            
            # Format clean paragraph breaks
            lines = [line.strip() for line in clean_text.splitlines() if line.strip()]
            final_description = "\n".join(lines)

            return final_description if len(final_description) > 20 else ""

        except Exception:
            return ""

    async def extract_description_by_length(self) -> str:
        """
        Scans elements (div, section, article, main, p, strong) for markup-free text chunks 
        exceeding the threshold. Walks up to the parent first; if 'Show more' / 'Show less' 
        is absent, falls back to the grandparent.
        """
        try:
            target_str = (
                "This role is to support driving growth in our winning and delivery of architecture "
                "services. You will be supporting sales efforts, ensuring successful project delivery, "
                "and building internal enterprise/solution architecture capabilities."
            )
            threshold = len(target_str)  # 257 characters

            description_text = await self.page.evaluate(
                f"""() => {{
                    const threshold = {threshold};
                    const candidates = document.querySelectorAll('div, section, article, main, p, strong');
                    
                    for (const el of candidates) {{
                        let foundValidChunk = false;
                        
                        // Check internal text chunks that have no HTML markup
                        for (const child of el.childNodes) {{
                            if (child.nodeType === Node.TEXT_NODE) {{
                                const text = child.nodeValue.trim();
                                if (text.length > threshold) {{
                                    foundValidChunk = true;
                                    break;
                                }}
                            }} else if (child.nodeType === Node.ELEMENT_NODE) {{
                                if (child.children.length === 0) {{
                                    const text = child.textContent.trim();
                                    if (text.length > threshold) {{
                                        foundValidChunk = true;
                                        break;
                                    }}
                                }}
                            }}
                        }}
                        
                        if (!foundValidChunk && el.children.length === 0) {{
                            if (el.textContent.trim().length > threshold) {{
                                foundValidChunk = true;
                            }}
                        }}
                        
                        if (foundValidChunk) {{
                            let parent = el.parentElement;
                            if (parent) {{
                                // Step 1: Try extracting from parent first
                                let parentCollected = [];
                                let hasShowMoreInParent = false;
                                
                                const parentWalker = document.createTreeWalker(parent, NodeFilter.SHOW_TEXT, null, false);
                                let node;
                                while (node = parentWalker.nextNode()) {{
                                    const val = node.nodeValue.trim();
                                    if (!val) continue;
                                    
                                    if (val.includes('Show more') || val.includes('Show less')) {{
                                        hasShowMoreInParent = true;
                                        break;
                                    }}
                                    parentCollected.push(val);
                                }}
                                
                                const parentText = parentCollected.join('\\n');
                                
                                // If 'Show more' exists in parent or parent text is sufficiently long, use parent
                                if (hasShowMoreInParent || parentText.length > threshold) {{
                                    if (parentText.length > threshold) {{
                                        return parentText;
                                    }}
                                }}
                                
                                // Step 2: Fallback to grandparent if 'Show more' was not found in parent
                                let grandparent = parent.parentElement;
                                if (grandparent) {{
                                    let gpCollected = [];
                                    const gpWalker = document.createTreeWalker(grandparent, NodeFilter.SHOW_TEXT, null, false);
                                    while (node = gpWalker.nextNode()) {{
                                        const val = node.nodeValue.trim();
                                        if (!val) continue;
                                        
                                        if (val.includes('Show more') || val.includes('Show less')) {{
                                            break;
                                        }}
                                        gpCollected.push(val);
                                    }}
                                    
                                    const gpText = gpCollected.join('\\n');
                                    if (gpText.length > threshold) {{
                                        return gpText;
                                    }}
                                }}
                            }}
                        }}
                    }}
                    return '';
                }}"""
            )

            if not description_text:
                return ""

            # Normalize lines and clean up whitespace
            lines = [line.strip() for line in description_text.splitlines() if line.strip()]
            final_description = "\n".join(lines)

            return final_description if len(final_description) > 50 else ""

        except Exception:
            return ""

    async def extract_single_job_by_url(
        self, job_url: str, status_callback=None, title_hint: str = ""
    ) -> dict:
        """Opens one job page and returns all its details.
        `title_hint` (e.g. the title seen on the results card) is used when given,
        otherwise the title is read from the job page."""
        job_id = self.job_id_from_url(job_url)
        if not job_id:
            raise ValueError(f"No LinkedIn job id found in URL: {job_url}")
        # Open a new tab in the same browser context so search results are never lost
        context = self.page.context
        new_page = await context.new_page()
        temp_extractor = JobExtractor(new_page)
        try:
            await self.page.goto(self.build_job_url(job_id), wait_until="domcontentloaded")
           
            if status_callback:
                status_callback("⏱️ Waiting for the page to fully settle...")
            await asyncio.sleep(5)

            try:
                # Anchor on semantic content ("ago" or "About the job") rather than a card class
                semantic_anchor = self.page.locator("*:has-text('ago'), *:has-text('About the job')").first
                await semantic_anchor.wait_for(state="attached", timeout=10000)
            except Exception:
                if status_callback:
                    status_callback("⚠️ Timeout waiting for job details to render.")
     
            html_content = await self.page.content()
            job_details = self.extract_linkedin_job_time_location(html_content)
            if not job_details:
                job_details = {"location": "", "time": ""}
                if status_callback:
                    status_callback(f"⚠️ Missing Job title and location for No({job_id})")
            title = title_hint or await self._extract_job_title()
            location = job_details["location"]
            company_details = self.extract_linkedin_company(html_content)

            company = company_details["company"]
            # --- 4. EXTRACT TITLE & METRICS FROM DETAIL PANE ---
            description_clean = await self._extract_description()
            if len(description_clean) < 150: 
                description_clean = await self.extract_description_by_length()

            if not description_clean and status_callback:
                status_callback(f"⚠️ Missing Job description for No({job_id})")

            html_content = await self.page.content()
            point_of_contact = self.extract_hiring_contact_bs4(html_content)
            
            metadata = self.extract_job_metadata_bs4(html_content, job_id=job_id, description_text=description_clean)
            work_type_str = metadata["workplace_type"]
            employment_type = metadata["employment_type"]
            salary = metadata["salary"]
            
            full_text_context = f"| {job_id} | {title} | {company} | {location} | {work_type_str} | {employment_type} | {salary} |  {description_clean}"

            if status_callback:
                status_callback(f"\\ {title} | {location} | {company} | ID: {job_id} \\")

            return {
                    "id": job_id,
                    "title": title,
                    "linkedin_score": "0",
                    "company": company,
                    "point_of_contact": point_of_contact,
                    "location": location,
                    "salary": salary,
                    "hybrid": work_type_str,
                    "work_type": employment_type,
                    "job_url": self.build_job_url(job_id),
                    "description": full_text_context,
                    "job_status": "@",
                    "score": "@",
                    "job_score_result": "@"
                }
        finally:
            # Always close the temporary tab so resources are freed and search view remains intact
            await new_page.close()

    async def _extract_job_title(self) -> str:
        """
        Extracts the job title directly from the detail pane header.
        """
        detail_pane_selectors = [
            "div[data-sdui-screen*='SemanticJobDetails'] a[href*='/jobs/view/']",
            "div[data-sdui-destination-screen*='SemanticJobDetails'] a[href*='/jobs/view/']",
            "main#main a[href*='/jobs/view/']",
            "div#workspace a[href*='/jobs/view/']",
            "main#main h1",
            "h1"
        ]

        for selector in detail_pane_selectors:
            try:
                elem = self.page.locator(selector).first
                if await elem.count() > 0 and await elem.is_visible():
                    raw_title = await elem.inner_text()
                    cleaned = self._clean_title_text(raw_title)
                    if cleaned and cleaned != "N/A":
                        return cleaned
            except Exception:
                continue

        return "N/A"

    def _clean_title_text(self, raw_title: str) -> str:
        """Cleans up raw title strings captured from DOM elements."""
        if not raw_title:
            return "N/A"

        # 1. Take first line to ignore sub-labels like company name or status badges
        title = raw_title.split("\n")[0].strip()

        # 2. Strip UI badges, metadata annotations, and status flags
        patterns_to_remove = [
            r"with verification",
            r"verified",
            r"actively hiring",
            r"actively reviewing applicants",
            r"promoted",
            r"easy apply",
            r"viewed",
            r"\d+\s+days?\s+ago",
            r"\d+\s+hours?\s+ago"
        ]
    
        for pattern in patterns_to_remove:
            title = re.sub(pattern, "", title, flags=re.IGNORECASE).strip()

        # 3. Remove leading/trailing non-alphanumeric noise (bullet points, dashes)
        title = re.sub(r"^[^\w\s]+|[^\w\s]+$", "", title).strip()

        # 4. Collapse whitespace
        title = " ".join(title.split())

        return title if title else "N/A"
    


    def _is_compensation_format(self, text: str) -> bool:
        """Checks if a string matches typical salary pill patterns (e.g., '97.9K GBP/yr')."""
        if not text:
            return False
    
        pattern = r"(?:£|\$|€|\b[A-Z]{3}\b)?\s*\d+(?:\.\d+)?\s*[kK]?\s*(?:GBP|USD|EUR)?\s*(?:/|\bper\b)?\s*(?:yr|year|annum|hr|hour|day|daily)\b"
        return bool(re.search(pattern, text, re.IGNORECASE))

    
    def _extract_salary_from_text(self, text: str) -> str:
        """Parses compensation phrases, daily rates, and ranges from raw description text."""
        if not text:
            return "N/A"

        patterns = [
            r"(?:salary|compensation|daily rate|day rate|pay rate|rate|package|remuneration)\s*[:\-]?\s*((?:£|\$|€)?\s*\d{2,3}(?:,\d{3})*(?:\.\d+)?\s*[kK]?\s*(?:-|to)?\s*(?:£|\$|€)?\s*\d{2,3}(?:,\d{3})*(?:\.\d+)?\s*[kK]?\s*(?:GBP|USD|EUR)?\s*(?:/\s*(?:day|daily|yr|year|annum|hr|hour)|per\s+(?:day|daily|year|annum|hour))?)",
            r"((?:£|\$|€)\s*\d{2,3}(?:,\d{3})*(?:\.\d+)?\s*[kK]?\s*(?:-|to)\s*(?:£|\$|€)?\s*\d{2,3}(?:,\d{3})*(?:\.\d+)?\s*[kK]?\s*(?:GBP|USD|EUR)?\s*(?:/\s*(?:day|daily|yr|year|annum|hr|hour)|per\s+(?:day|daily|year|annum|hour))?)",
            r"((?:£|\$|€)\s*\d{2,3}(?:,\d{3})*(?:\.\d+)?\s*[kK]?\s*(?:/\s*(?:day|daily|yr|year|annum|hr|hour)|per\s+(?:day|daily|year|annum|hour)))"
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                extracted = match.group(1) if match.groups() else match.group(0)
                return self._clean_salary_text(extracted)

        return "N/A"


    def _clean_salary_text(self, text: str) -> str:
        """Standardizes extracted salary strings."""
        if not text:
            return "N/A"
    
        # Clean whitespace and trailing punctuation
        text = " ".join(text.split()).rstrip(".,;")
        return text if len(text) > 2 else "N/A"

    def extract_linkedin_company(self, html_content: str) -> dict:
        """
        Extracts company name and LinkedIn profile URL based on href semantic structure.
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        company_link = soup.find('a', href=re.compile(r'/company/'))
    
        if not company_link:
            return {"company": None, "company_url": None}
        
        return {
            "company": company_link.get_text(strip=True),
            "company_url": company_link.get('href', '').split('?')[0]
        }

    

    def extract_hiring_contact_bs4(self, html_content: str) -> dict | None:
        """
        Extracts hiring team point of contact using 'Meet the hiring team' text anchor.
        """
        soup = BeautifulSoup(html_content, 'html.parser')
    
        # 1. Anchor on 'Meet the hiring team' text node or header
        anchor = soup.find(string=re.compile(r'Meet the hiring team', re.IGNORECASE))
        if not anchor:
            return None
    
        # 2. Locate the parent section container
        header_element = anchor.find_parent(['p', 'h2', 'h3', 'div'])
        if not header_element:
            return None
        
        # 3. Find the profile anchor link following the header in the DOM
        profile_link = header_element.find_next('a', href=re.compile(r'/in/'))
        if not profile_link:
            return None

        profile_url = profile_link.get('href', '')

        # 4. Extract contact name (first non-empty text node inside the link)
        name = None
        for text_node in profile_link.stripped_strings:
            # Ignore badge symbols, separators, or role labels
            if text_node and text_node not in [".", "·", "2nd", "3rd", "1st", "Job poster"]:
                name = text_node
                break

        # 5. Extract role / job poster label if available
        poster_role = None
        role_p = profile_link.find_next(string=re.compile(r'Job poster', re.IGNORECASE))
        if role_p:
            poster_role = role_p.strip()

        return {
            "Name": name,
            "Profile URL": profile_url,
            "Role": poster_role
        }

    def extract_linkedin_job_time_location(self, html_content: str) -> dict | None:
        soup = BeautifulSoup(html_content, "html.parser")

        time_pattern = re.compile(
            r"\b\d+\s+(?:second|minute|hour|day|week|month|year)s?\s+ago\b",
            re.IGNORECASE,
        )
        time_node = soup.find(string=time_pattern)

        if not time_node:
            return None

        when_listed_match = time_pattern.search(str(time_node))
        when_listed = (
            when_listed_match.group(0) if when_listed_match else time_node.strip()
        )

        parent_container = time_node.find_parent(["p", "div"])
        if not parent_container:
            return {"location": "", "time": when_listed}

        elements = [
            elem.get_text(strip=True)
            for elem in parent_container.find_all(True)
            if elem.get_text(strip=True)
        ]

        cleaned_parts = [
            item
            for item in elements
            if item not in [".", "·", "•", "|", "-"]
            and when_listed not in item
            and "applicant" not in item.lower()
        ]

        location = cleaned_parts[0] if cleaned_parts else ""

        return {"location": location, "time": when_listed}

    def extract_job_metadata_bs4(
        self, html_content: str, job_id: str = "", description_text: str = ""
    ) -> dict:
        """
        Extracts workplace type, employment type, and salary in a single pass.
        Prioritizes <a href> links matching the specific job_id URL path (metadata pills),
        falling back to description text if not found.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        results = {
            "workplace_type": "N/A", 
            "employment_type": "N/A",
            "salary": "N/A"
        }

        workplace_keywords = {
            "Hybrid": ["Hybrid", "2 days", "3 days", "2, 3 days"],
            "Remote": ["Remote"],
            "On-site": ["On-site", "Onsite"],
        }

        employment_keywords = {
            "Full-time": ["Full-time", "Full time"],
            "Part-time": ["Part-time", "Part time"],
            "Contract": ["Contract", "Contractor"],
            "Temporary": ["Temporary"],
        }

        pay_pattern = re.compile(
            r"(?:£|\$|€)\s*\d{2,3}(?:,\d{3})*(?:\.\d+)?\s*[kK]?"
            r"|(?:\b(?:GBP|USD|EUR)\b)"
            r"|(?:\/(?:yr|year|hr|hour|day|month))",
            re.IGNORECASE,
        )

        # 1. Target specifically <a href> links containing the exact job view URL for this job_id
        job_view_links = []
        if job_id:
            specific_link_pattern = re.compile(rf'/jobs/view/{job_id}', re.IGNORECASE)
            job_view_links = soup.find_all('a', href=specific_link_pattern)

        found_workplace = []
        
        # Check specific job view links for workplace type
        for label, variants in workplace_keywords.items():
            for link in job_view_links:
                text = link.get_text(strip=True)
                if any(re.search(r"\b" + re.escape(v) + r"\b", text, re.IGNORECASE) for v in variants):
                    if label not in found_workplace:
                        found_workplace.append(label)

        # Check specific job view links for employment type
        for label, variants in employment_keywords.items():
            for link in job_view_links:
                text = link.get_text(strip=True)
                if any(re.search(r"\b" + re.escape(v) + r"\b", text, re.IGNORECASE) for v in variants):
                    results["employment_type"] = label
                    break
            if results["employment_type"] != "N/A":
                break

        # Check specific job view links for salary
        for link in job_view_links:
            text = link.get_text(strip=True)
            if text and pay_pattern.search(text) and self._is_compensation_format(text):
                results["salary"] = self._clean_salary_text(text)
                break

        if found_workplace:
            results["workplace_type"] = "; ".join(found_workplace)

        # 2. Description text regex fallback for any missing fields
        if description_text and (results["workplace_type"] == "N/A" or results["employment_type"] == "N/A" or results["salary"] == "N/A"):
            if results["workplace_type"] == "N/A":
                if re.search(r"\b(hybrid|flexible\s+working)\b", description_text, re.IGNORECASE):
                    results["workplace_type"] = "Hybrid"
                elif re.search(r"\b(remote|work\s+from\s+home|wfh)\b", description_text, re.IGNORECASE):
                    results["workplace_type"] = "Remote"
                elif re.search(r"\b(on-site|onsite|in-office|in\s+office)\b", description_text, re.IGNORECASE):
                    results["workplace_type"] = "On-site"

            if results["employment_type"] == "N/A":
                if re.search(r"\b(full-time|full\s+time)\b", description_text, re.IGNORECASE):
                    results["employment_type"] = "Full-time"
                elif re.search(r"\b(contract|contractor|fixed-term|freelance)\b", description_text, re.IGNORECASE):
                    results["employment_type"] = "Contract"
                elif re.search(r"\b(part-time|part\s+time)\b", description_text, re.IGNORECASE):
                    results["employment_type"] = "Part-time"
                elif re.search(r"\b(temporary|temp)\b", description_text, re.IGNORECASE):
                    results["employment_type"] = "Temporary"

            if results["salary"] == "N/A":
                results["salary"] = self._extract_salary_from_text(description_text)

        return results