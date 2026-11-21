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

# linkedin_bot.py
import asyncio
import os
import re
from urllib.parse import quote
from playwright.async_api import async_playwright
from playwright_stealth import Stealth  # For Playwright async API
from ai_assistant import AIAssistant
from job_extractor import JobExtractor
from db_tracker import DatabaseTracker
from config_manager import ConfigManager
from job_prefilter import title_gate, prefilter
from base_portal_bot import BaseJobPortalBot

class LinkedInBot(BaseJobPortalBot):
    """Browser, login, search/pagination and job-list collection.
    Extracting the details of ONE job is delegated to JobExtractor."""

    JOB_LINK_SELECTOR = "a[href*='/jobs/view/']"

    JOBS_PER_PAGE = 55
    SETTLE_SECONDS = 15

    # Finds the real scrollable results list (starting from the first job link)
    # and scrolls it one step, so we never depend on LinkedIn's CSS class names.
    _SCROLL_JS_OLD = """
    () => {
        const links = [...document.querySelectorAll("a[href*='/jobs/view/']")];
        if (!links.length) { window.scrollBy(0, 800); return 'window'; }
        let el = links[0].parentElement;
        while (el && el !== document.body && el !== document.documentElement) {
            const oy = getComputedStyle(el).overflowY;
            if (/(auto|scroll)/.test(oy) && el.scrollHeight > el.clientHeight + 5) {
                el.scrollTop += Math.max(300, el.clientHeight * 0.7);
                return 'container';
            }
            el = el.parentElement;
        }
        links[links.length - 1].scrollIntoView({block: 'end'});
        window.scrollBy(0, 600);
        return 'window';
    }
    """
    _SCROLL_JS = """
    () => {
        window.scrollBy(0, 800);
        return 'window';
    }
    """

    def __init__(self):
        # Default fallback to active Windows user Edge profile path if not explicitly provided
        user_name = os.getlogin()
        
        self.config_mgr = ConfigManager()
        self.user_data_dir = self.config_mgr.get_constant(ConfigManager.KEY_USER_DATA_DIR)
        self.channel = self.config_mgr.get_constant(ConfigManager.KEY_CHANNEL)
        self.profile_directory = self.config_mgr.get_constant(ConfigManager.KEY_MY_PROF_PROFILE)
        self.db_tracker = DatabaseTracker()
        self.playwright = None
        self.context = None
        self.page = None
        self.ai_assistant = None
        self.job_extractor = None

    async def init_browser(self):
        if not self.playwright:
            self.playwright = await async_playwright().start()
        
        base_user_data = self.user_data_dir
        profile_name = "JobSearchPy"

        # 🚀 Launch Chrome WITHOUT viewport (required for real maximization)
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=base_user_data,
            headless=False,
            no_viewport=True,
            channel="chrome",
            args=[
                "--start-maximized",
                "--force-device-scale-factor=1",
                "--disable-features=RestoreSessionState",
                "--disable-features=BrowserStartupWindowBounds",
                f"--profile-directory={profile_name}",
                "--disable-blink-features=AutomationControlled",
            ],
            ignore_default_args=["--enable-automation"],
        )

        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        # 🚀 TRUE OS-level maximize using Chrome DevTools Protocol
        session = await self.context.new_cdp_session(self.page)
        window = await session.send("Browser.getWindowForTarget")
        await session.send("Browser.setWindowBounds", {
            "windowId": window["windowId"],
            "bounds": {"windowState": "maximized"}
        })
        await self.page.wait_for_load_state("domcontentloaded")
        
        # Apply stealth
        stealth = Stealth()
        await stealth.apply_stealth_async(self.context)
        self.job_extractor = JobExtractor(self.page)
        self.ai_assistant = AIAssistant(self.context)
        # await self.ai_assistant.initialize_tabs()



    @classmethod
    def job_id_from_url(cls, url: str) -> str | None:
        """Returns the numeric LinkedIn job id contained in a URL, or None."""
        if not url:
            return None
        match = cls.JOB_VIEW_PATTERN.search(url)
        return match.group(1) if match else None

    async def check_and_ensure_login(self, status_callback=None):
        """Validates LinkedIn session state."""
        if not self.context:
            await self.init_browser()
        await self.page.goto("https://www.linkedin.com/jobs/search/", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        await self.page.bring_to_front()
        return True
    async def check_and_ensure_withlogin(self, status_callback=None):
        
        """Validates LinkedIn session state."""
        if not self.context:
            await self.init_browser()

        if status_callback:
            status_callback("[*] Checking LinkedIn authentication state...")

        await self.page.goto("https://www.linkedin.com/", wait_until="domcontentloaded")
        await asyncio.sleep(2)

        is_logged_in = await self._is_logged_in()

        while not is_logged_in:
            if status_callback:
                status_callback("⚠️ ACTION REQUIRED: NOT LOGGED IN! Please complete login...")
            await asyncio.sleep(3)
            is_logged_in = await self._is_logged_in()

        if status_callback:
            status_callback("✅ ACTIVE SESSION DETECTED!")

        await self.page.bring_to_front()
        return True

    async def _is_logged_in_OLD(self):
        return true
    async def _is_logged_in_OLD(self):
        try:
            url = self.page.url
            if any(
                term in url
                for term in ["/login", "/signup", "authwall", "checkpoint"]
            ):
                return False

            if "/feed" in url or "/jobs" in url:
                return True

            profile_selectors = [
                "img.global-nav__me-photo",
                "button[aria-label*='me']",
                ".global-nav__me",
                ".global-nav",
                "#global-nav",
                ".feed-outlet-container"
            ]
            
            for selector in profile_selectors:
                if await self.page.locator(selector).first.is_visible(timeout=1000):
                    return True
            return False
        except Exception:
            return False

    async def search_and_extract_all_by_parameters(
        self,
        search_meta: dict,
        page_num: int,
        status_callback=None,
        on_job=None,
    ):  
        search_url = self._build_search_url(search_meta, page_num, status_callback)
        
        extracted_jobs = await self.search_and_extract_all_by_URL(search_url, status_callback, page_num, on_job=on_job)
            
        return extracted_jobs
    # ------------------------------------------------------------------ #
    # Search / pagination helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_search_url(search_meta: dict, page: int = 0, status_callback=None) -> str:
        
        start = (page - 1) * 25 if page > 0 else 0
        location = search_meta.get("location", "UK")
        f_tpr = search_meta.get("date_posted_f_TPR") or "r604800"
        f_e = search_meta.get("experience_keys_f_E") or "3,4,5,6"
        f_jt = search_meta.get("contract_keys_f_JT") or "F,P,C"
        f_wt = search_meta.get("workplace_type_f_WT")
        keyword = search_meta.get("target_input")
        distance = search_meta.get("distance") or None
        sort_by = search_meta.get("sort_by") or None
        
        if status_callback:
            status_callback(f"📊 [Search]: {keyword} |d[{distance}] | f_wt[{f_wt}] | f_tpr[{f_tpr}] | f_e[{f_e}] | f_jt[{f_jt}] | {location} | PageNo[{page}][{start}] | ")

        url = (
            f"https://www.linkedin.com/jobs/search/?"
            f"keywords={quote(keyword)}"
            f"&location={quote(location)}"
        )
        if distance:
            url += f"&distance={quote(distance)}"
        if f_tpr:
            url += f"&f_TPR={f_tpr}"
        if f_e:
            url += f"&f_E={f_e}"
        if f_jt:
            url += f"&f_JT={f_jt}"
        if f_wt:
            url += f"&f_WT={f_wt}"
        if sort_by:
            url += f"&sortBy={sort_by}"
            
        url += f"&start={start}"
        return url

    async def _wait_for_results(self, status_callback=None, page_num: int | None = None):
        label = f"page {page_num}" if page_num else "the page"
        if status_callback:
            status_callback(f"⏱️ Waiting {self.SETTLE_SECONDS} seconds for {label} to fully settle...")
        await asyncio.sleep(self.SETTLE_SECONDS)
        try:
            await self.page.wait_for_selector(self.JOB_LINK_SELECTOR, timeout=10000)
        except Exception:
            await asyncio.sleep(3)

    async def _collect_job_links(self, target: int = 55, max_cycles: int = 40) -> dict[str, dict[str, str]]:
        """Collects all visible job links by extracting a min 9-digit job ID from the URL before the '?'."""
        collected: dict[str, dict[str, str]] = {}
        stable = 0

        for _ in range(max_cycles):
            # 1. Grab all hrefs and text from anchor tags inside <li> elements or the whole page
            anchors = await self.page.eval_on_selector_all(
                "li a[href*='/jobs/view/'], a[href*='/jobs/view/']",
                """els => els.map(e => ({
                    href: e.href,
                    text: (e.innerText || e.textContent || '').trim(),
                    aria: e.getAttribute('aria-label') || ''
                }))"""
            )

            before = len(collected)
            for a in anchors:
                job_id = JobExtractor.job_id_from_url(a["href"])
                if not job_id:
                    continue
                
                title = self._clean_card_title(a["text"]) or self._clean_card_title(a["aria"])
                job_url = JobExtractor.build_job_url(job_id)

                if job_id not in collected:
                    collected[job_id] = {"title": title, "job_url": job_url}
                else:
                    if title and not collected[job_id].get("title"):
                        collected[job_id]["title"] = title

            if len(collected) >= target:
                break

            # If no new jobs were found in this scroll cycle, increment stability counter
            stable = stable + 1 if len(collected) == before else 0
            if stable >= 4:
                break

            # Scroll down to load the next batch of <li> items into view
            await self.page.evaluate(self._SCROLL_JS)
            await asyncio.sleep(0.8)

        return collected

    async def _collect_job_links_old(self, target: int = 25, max_cycles: int = 40) -> dict[str, dict[str, str]]:
        collected: dict[str, dict[str, str]] = {}
        stable = 0

        for _ in range(max_cycles):
            anchors = await self.page.eval_on_selector_all(
                self.JOB_LINK_SELECTOR,
                """els => els.map(e => ({
                    href: e.href,
                    text: (e.innerText || e.textContent || '').trim(),
                    aria: e.getAttribute('aria-label') || ''
                }))""",
            )

            before = len(collected)
            for a in anchors:
                job_id = JobExtractor.job_id_from_url(a["href"])
                if not job_id:
                    continue
                
                title = self._clean_card_title(a["text"]) or self._clean_card_title(a["aria"])
                job_url = a["href"]

                if job_id not in collected:
                    collected[job_id] = {"title": title, "job_url": job_url}
                else:
                    if title and not collected[job_id].get("title"):
                        collected[job_id]["title"] = title
                    if job_url and not collected[job_id].get("job_url"):
                        collected[job_id]["job_url"] = job_url

            if len(collected) >= target:
                break

            stable = stable + 1 if len(collected) == before else 0
            if stable >= 4:
                break

            await self.page.evaluate(self._SCROLL_JS)
            await asyncio.sleep(0.8)

        return collected
        
    @staticmethod
    def _clean_card_title(raw: str) -> str:
        """LinkedIn repeats the title in hidden spans; keep the first real line."""
        for line in (raw or "").splitlines():
            line = line.strip()
            if len(line) >= 2:
                return line
        return ""

    async def close(self):
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()


    def classify_url(self, url: str) -> str:
        """Classifies whether a LinkedIn URL points to a single job or a list/search page."""
        # Check for search/list pages FIRST, since search URLs can also contain currentJobId
        if "/jobs/search" in url or "keywords=" in url:
            return "list"
        # Check for direct single job views second
        elif "/jobs/view/" in url:
            return "one"
        else:
            return "na"
            
    async def extract_single_job_by_url(
        self, job_url: str, status_callback=None, title_hint: str = ""
    ) -> dict:
        return await self.job_extractor.extract_single_job_by_url(
                    job_url,
                    status_callback=status_callback,
                    title_hint=title_hint,
                )
                
    async def search_and_extract_all_by_URL(
        self,
        page_url: str,
        status_callback=None,
        page_num: int | None = None,
        on_job=None,
    ):
        """`on_job(job) -> bool` (async) is awaited right after each job is read.
        Return False from it to stop reading the rest of the page."""
        if status_callback:
            status_callback(f"\n[*] Navigating directly to URL: {page_url}")
            
        typeOfURL = self.classify_url(page_url)
        extracted_jobs = []
        
        if typeOfURL == "one":
            job = await self.extract_single_job_by_url(page_url, status_callback=status_callback)
            extracted_jobs.append(job)
            if on_job is not None:
                await on_job(job)
            return extracted_jobs
        #Multiple jobs URL
        await self.page.goto(page_url, wait_until="domcontentloaded")
        await self._wait_for_results(status_callback, page_num)
        
        existing_ids: set = set()      # ids seen on this page; everything else is checked against the database
        results_url = self.page.url
        
        collected = await self._collect_job_links(target=self.JOBS_PER_PAGE)
        if status_callback:
            status_callback(f"[*] Collected {len(collected)} job IDs on page {page_num}. Processing extraction...")
            
        collection_size = len(collected)

        for job_id, data in collected.items():
            title = data.get("title")
            job_url = JobExtractor.build_job_url(job_id)
            if not self._is_new_job(page_num, job_id, existing_ids, status_callback):
                continue
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

        #try:
        #    await self.page.goto(results_url, wait_until="domcontentloaded")
        #except Exception:
        #    pass
        return extracted_jobs