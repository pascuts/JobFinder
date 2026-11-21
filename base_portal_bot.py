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

from abc import ABC, abstractmethod
#base_portal_bot.py
class BaseJobPortalBot(ABC):
    """Abstract interface for all job board scrapers."""

    @abstractmethod
    async def init_browser(self):
        pass

    @abstractmethod
    async def check_and_ensure_login(self, status_callback=None) -> bool:
        """Handles authentication or session checks if required by the portal."""
        pass

    @abstractmethod
    async def search_and_extract_all_by_parameters(
        self,
        search_meta: dict,
        page_num: int,
        status_callback=None,
        on_job=None
    ) -> list[dict]:
        """Searches and yields jobs for a specific page."""
        pass

    @abstractmethod
    def _build_search_url(search_meta: dict, page: int = 0, status_callback=None) -> str:
        pass

    @abstractmethod
    async def close(self):
        pass
        
    @abstractmethod
    def classify_url(self, url: str) -> str:
        pass
        
    @abstractmethod
    async def search_and_extract_all_by_URL(
        self,
        page_url: str,
        status_callback=None,
        page_num: int | None = None,
        on_job=None,
    ) -> list[dict]:
        pass
        
    @abstractmethod    
    async def extract_single_job_by_url(
        self, job_url: str, status_callback=None, title_hint: str = ""
    ) -> dict:
        pass
        
    def _is_new_job(self, page_no:int, job_id: str, existing_ids: set, status_callback=None) -> bool:
        """False if the job is repeated on this page or already stored in the database."""
        if not job_id:
            return False
        if job_id in existing_ids:
            if status_callback:
                status_callback(f"Pg[{page_no}]ℹ️ Skipping duplicate job on this page: {job_id}")
            return False
        if self.db_tracker.is_job_processed_or_excluded(job_id):
            if status_callback:
                status_callback(f"Pg[{page_no}]ℹ️ Skipping duplicate job in Database: {job_id}")
            return False
        return True