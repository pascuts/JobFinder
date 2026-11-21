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
from urllib.parse import quote
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from base_portal_bot import BaseJobPortalBot
from db_tracker import DatabaseTracker
from job_prefilter import title_gate

class GovUkJobsBot(BaseJobPortalBot):
    """Scraper adapter for UK Civil Service Jobs (jobs.service.gov.uk)."""

    def __init__(self):
        self.playwright = None
        self.context = None
        self.page = None
        self.db_tracker = DatabaseTracker()

    async def init_browser(self):
        if not self.playwright:
            self.playwright = await async_playwright().start()
        
        self.context = await self.playwright.chromium.launch(headless=False)
        self.page = await self.context.new_page()

    async def check_and_ensure_login(self, status_callback=None) -> bool:
        # Civil Service jobs are public; no login required.
        if status_callback:
            status_callback("[*] Gov.uk Jobs does not require authentication.")
        return True

    def _build_search_url(self, search_meta: dict, page: int = 0, status_callback=None) -> str:
        location = search_meta.get("location")
        loc_encoded = quote(location if location else "UK")
        kw_encoded = quote(search_meta.get("target_input"))
        if status_callback:
            status_callback(f"📊 [Search]: {search_meta.get("target_input")} | f_wt[{f_wt}] | f_tpr[{f_tpr}] | f_e[{f_e}] | f_jt[{f_jt}] | {location} | PageNo[{page}][{start}] | ")

        return f"https://www.jobs.service.gov.uk/jobs/search?keywords={kw_encoded}&location={loc_encoded}&pageNumber={page}"

    async def extract_single_job_by_url(
        self, job_url: str, status_callback=None, title_hint: str = ""
    ) -> dict:
        """Opens one Gov.uk job page and extracts all its details using exact data-testids."""
        if status_callback:
            status_callback(f"[*] Navigating to job detail URL: {job_url}")

        await self.page.goto(job_url, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        html_content = await self.page.content()
        soup = BeautifulSoup(html_content, 'html.parser')

        # 1. Title from page heading
        title_elem = soup.find(attrs={"data-testid": "pageHeading"})
        title = title_elem.get_text(strip=True) if title_elem else (title_hint or "N/A")

        # 2. Extract fields using explicit data-testids from the summary table
        def get_field(testid: str, default: str = "N/A") -> str:
            elem = soup.find(attrs={"data-testid": testid})
            return elem.get_text(strip=True) if elem else default

        company = get_field("companyName", "UK Government / Public Sector")
        salary = get_field("salary", "N/A")
        job_pattern = get_field("jobPattern", "Full-time")
        remote_working = get_field("remoteWorking", "N/A")
        job_type = get_field("jobType", "Permanent")
        job_location = get_field("location", "Permanent")

        # 3. Full Job Description text inside rawHtmlContainer
        desc_elem = soup.find(class_="rawHtmlContainer")
        description = desc_elem.get_text(separator="\n", strip=True) if desc_elem else ""

        # 4. Extract unique Job ID from URL
        id_match = re.search(r'/jobs/([a-zA-Z0-9\-]+)', job_url)
        job_id = id_match.group(1) 

        log_line = f"\\ {title} | {company} | {salary} | ID: {job_id} \\"
        if status_callback:
            status_callback(log_line)

        return {
            "id": job_id,
            "title": title,
            "linkedin_score": "0",
            "company": company,
            "point_of_contact": "N/A",
            "location": job_location,
            "salary": salary,
            "hybrid": remote_working,
            "work_type": f"{job_pattern} ({job_type})",
            "job_url": job_url,
            "description": description,
            "job_status": "@",
            "score": "@",
            "job_score_result": "@"
        }

    async def search_and_extract_all_by_parameters(
        self, search_meta: dict, page_num: int, 
        status_callback=None, on_job=None) -> list[dict]:
        
        search_url = self._build_search_url(search_meta, page_num, status_callback)
        return await self.search_and_extract_all_by_URL(search_url, status_callback, page_num, on_job)

    async def close(self):
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()
            
    def classify_url(self, url: str) -> str:
        """Classifies whether a Gov.uk URL points to a single job or a list/search page."""
        if "/jobs/search" in url or "keywords=" in url:
            return "list"
        return "one"
         
    async def search_and_extract_all_by_URL(
        self,
        page_url: str,
        status_callback=None,
        page_num: int | None = None,
        on_job=None,
    ) -> list[dict]:
        """Classifies the URL as 'one' (single job) or 'list' (search results) and extracts with full gating."""
        if status_callback:
            status_callback(f"\n[*] Navigating to URL: {page_url}")
            
        type_of_url = self.classify_url(page_url)
        extracted_jobs = []
        
        if type_of_url == "one":
            job = await self.extract_single_job_by_url(page_url, status_callback=status_callback)
            extracted_jobs.append(job)
            if on_job is not None:
                await on_job(job)
            return extracted_jobs
            
        # List / Search page handling
        await self.page.goto(page_url, wait_until="domcontentloaded")
        await asyncio.sleep(2)
        
        html_content = await self.page.content()
        soup = BeautifulSoup(html_content, 'html.parser')
        
        job_anchors = soup.select('a[data-testid^="jobTitle-"]')
        
        collected_cards: dict[str, dict[str, str]] = {}
        seen_urls = set()
        
        for a in job_anchors:
            href = a.get("href")
            if not href:
                continue
            if "service.gov.uk" not in href:
                href = f"https://www.jobs.service.gov.uk{href}"
            if href in seen_urls:
                continue
            seen_urls.add(href)
            
            h2_elem = a.find("h2")
            title = h2_elem.get_text(strip=True) if h2_elem else a.get_text(strip=True)
            
            id_match = re.search(r'/jobs/([a-zA-Z0-9\-]+)', href)
            job_id = id_match.group(1) if id_match else f"gov_job_{len(collected_cards)}"
            
            collected_cards[job_id] = {
                "title": title,
                "job_url": href
            }
        collection_size = len(collected_cards)
        if status_callback:
            status_callback(f"Pg[{page_num}][*] Collected {collection_size} job IDs on page, extraction...")
            
        
        existing_ids: set = set()
        new_jobs: dict[str, dict[str, str]] = {}
        new_cards = 0
        title_rejected = 0

        for job_id, data in collected_cards.items():
            title = data.get("title")
            job_url = data.get("job_url")
            if not self._is_new_job(page_num, job_id, existing_ids, status_callback):
                continue
            existing_ids.add(job_id)
            # 1. Extract job details first
            try:
                job = await self.extract_single_job_by_url(
                    job_url,
                    status_callback=status_callback,
                    title_hint=title,
                )
            except Exception as e:
                if status_callback:
                    status_callback(f"⚠️ Job {job_id} failed: {e}")
                continue
                          
            extracted_jobs.append(job)
               
            if on_job is not None:
                try:
                    keep_going = await on_job(job)
                    # Print run stats right after on_job completes for this job
                    if hasattr(on_job, "last_result"):
                        run_data = on_job.last_result.get("run")
                        msg = on_job.last_result.get("return_message")
                        max_achieved = on_job.last_result.get("max_job_reads")
                        if status_callback and run_data:
                            status_callback(
                                f"📊 Page[{page_num}]Ids[{collection_size}]Job[{job_id}]Reads[{run_data.reads}]New[{run_data.new_scraped_jobs}]"
                                f"Failed[Title[{run_data.title_rejected}], Blacklist[{run_data.company_blacklisted}]"
                                f"PreFilter[{run_data.prefilter_reject}]]MaxJobsLimit[{max_achieved}], msg: [{msg}]"
                            )
                except Exception as e:
                    if status_callback:
                        status_callback(f"⚠️ on_job call failed for {job_id}: {e}")
                    keep_going = True
                if keep_going is False:
                    if status_callback:
                        status_callback("[*] Limit reached - not reading the remaining jobs on this page.")
                    break 
                    
        return extracted_jobs