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

# daily_runner.py
from __future__ import annotations
import inspect
from dataclasses import dataclass
from job_prefilter import title_gate, prefilter as default_prefilter
from keyword_scheduler import KeywordPlan, KeywordScheduler
from keyword_store import split_keywords

@dataclass
class _Run:
    pages: int = 0
    reads: int = 0
    title_rejected: int = 0
    company_blacklisted: int = 0
    prefilter_reject: int = 0
    page_stageb: int = 0          # stage-B failures on the page being read (reset per page)
    bad_pages: int = 0            # pages that exceeded the keyword's prefilter-failure limit
    new_scraped_jobs: int = 0
    @property
    def prefilter_failed(self) -> int:
        return self.title_rejected + self.prefilter_reject +  self.company_blacklisted

class KeywordSearchEngine:
    def __init__(self, bot, scheduler: KeywordScheduler, 
                 say=print, progress=None, is_interrupted=None,
                 prefilter_fn=None, search_meta: dict | None = None):
        self.bot = bot
        self.scheduler = scheduler
        self.db = scheduler.db
        self.L = scheduler.limits
        self.say = say or print
        self.progress = progress
        self.is_interrupted = is_interrupted or (lambda: False)
        self.prefilter = prefilter_fn or default_prefilter
        self.meta = search_meta or {}
        self.abort = False

    def _reads_left(self) -> int:
        """Job pages that may still be opened today (config: max_jobs_read_per_day)."""
        used = self.scheduler.store.today_totals()["reads"]
        return max(self.L.max_reads_per_day - used, 0)

    async def run_day(self, domain: str | None = None, max_rounds: int = 3) -> dict:
        # Successes are only known after the AI scoring phase, so during scraping plan_day() always sees
        # the full target remaining. The daily read limit is what stops the rounds.
        for rnd in range(1, max_rounds + 1):
            if self.abort or self.is_interrupted():
                break
            if self._reads_left() <= 0:
                self.say(f"⛔ Daily read limit reached ({self.L.max_reads_per_day} jobs) - scraping stopped.")
                break
            plans = self.scheduler.plan_day(domain=domain)
            if not plans:
                break
            for plan in plans:
                if self.abort or self.is_interrupted():
                    break
                if self._reads_left() <= 0:
                    self.say(f"⛔ Daily read limit reached ({self.L.max_reads_per_day} jobs) - scraping stopped.")
                    self.abort = True
                    break
                await self.run_keyword(plan)
        return self.scheduler.today_totals()

    async def run_single(self, keyword_text: str) -> dict:
        await self.run_keyword(self.scheduler.plan_for_keyword(keyword_text))
        return self.scheduler.today_totals()

    async def run_url(self, url: str) -> dict:
        run = _Run()
        search_params = dict(self.meta)
        search_params["keyword"] = "(direct URL)"
        search_params["target_input"] = url
        
        search_id = self.db.log_search_start(search_params)
        handler = self._make_handler(run, search_id)
        try:
            await self.bot.search_and_extract_all_by_URL(url, self.say, 1, on_job=handler)
            run.pages = 1
        finally:
            self.db.update_search_metrics(search_id, run.reads, 0, 0, 0)
        return self.scheduler.today_totals()

    def _make_handler(self, run: _Run, search_id, max_reads: int | None = None):
        async def on_job(job: dict) -> bool:
            if self.is_interrupted():
                return False
            run.reads += 1
            job_id = str(job.get("id", "")).strip()
            company_name = job.get("company", "")
            title =  job.get("title", "")
            eval_dict = {}
            
            pref_Job = self.prefilter(job)
            return_message = ""
            if self.db.is_company_blacklisted(company_name):
                run.company_blacklisted += 1
                return_message = f"🚫 Blacklisted Company Skipped '{company_name}'"
                eval_dict = {"job_status": "Blacklisted", "score": -3500, "cvtmpl_no": -1,
                     "job_score_result": f"Blacklisted Company: {company_name}"}
            elif not pref_Job.passed:                 
                run.prefilter_reject += 1
                run.page_stageb += 1
                return_message = f"🚫 [PreFilter REJECT] [{title}] | {pref_Job.reason}"
                eval_dict = {
                    "score": -3508, 
                    "job_status": "PreFilter", 
                    "cvtmpl_no": -1,
                    "job_score_result": f"<prefilter_failed>{pref_Job.reason}</prefilter_failed>"
                }    
            else:
                run.new_scraped_jobs += 1
                return_message = f"📥 {job.get('title','')} [Scraped] successfully"
                eval_dict = {
                    "score": 1500, 
                    "job_status": "Scraped", 
                    "cvtmpl_no": -1,
                    "job_score_result": "Saved for AI processing."
                }
            job["job_status"] = eval_dict.get("job_status")
            job["match_score"] = eval_dict.get("score")
            job["job_score_result"] = eval_dict.get("job_score_result")
            job["cvtmpl_no"] = eval_dict.get("cvtmpl_no")
            
            # Save raw job and prefilter status
            self.db.log_job(job, eval_dict, search_id=search_id)
            self.db.save_prefilter_result(job_id, "Y" if pref_Job.passed else "N", pref_Job.score, pref_Job.reason)
            max_job_reads = max_reads is None or run.reads < max_reads
            # Attach structured data bundle for external inspection if needed
            on_job.last_result = {
                "run": run,
                "max_job_reads": max_job_reads,
                "return_message": return_message
            }
            
            return max_job_reads      # Returns boolean required by bot loop
            
        return on_job
        
    async def run_keyword(self, plan: KeywordPlan) -> dict:
        reads_left = self._reads_left()
        if reads_left <= 0:
            self.say(f"⛔ [{plan.keyword}] daily read limit ({self.L.max_reads_per_day}) reached - skipped.")
            return self.scheduler.today_totals()
        max_reads = min(plan.max_reads, reads_left)      # never read past today's allowance
        run = _Run()

        search_params = dict(self.meta)
        search_params["keyword"] = plan.keyword
        search_params["target_input"] = plan.query
        
        search_id = self.db.log_search_start(search_params)

        handler = self._make_handler(run, search_id, max_reads=max_reads)
        stop_reason = "scraped"
        try:
            for page_no in range(1, plan.max_pages + 1):
                if self.abort or self.is_interrupted():
                    break
                if run.reads >= max_reads:
                    break
                    
                run.page_stageb = 0
                run.title_rejected = 0
                run.company_blacklisted = 0
                run.prefilter_reject = 0
                run.new_scraped_jobs: int = 0
                
                self.say(f"🌲[{plan.keyword}] - page[{page_no}] daily limit ({self.L.max_reads_per_day}) - read[{run.reads}] = left[{reads_left}].")
                
                extracted_jobs = await self.bot.search_and_extract_all_by_parameters(
                    search_params, page_no, status_callback=self.say,
                    on_job=handler
                )
                run.pages += 1
                stats = getattr(self.bot, "last_page_stats", {}) or {}

                if run.title_rejected + run.page_stageb > plan.max_prefilter_fail:
                    run.bad_pages += 1          # costs the keyword score points (prefilter_penalty)
                if len(extracted_jobs)==0:
                    self.say(f"⛔ [{plan.keyword}] extracted 0 jobs on page[{page_no}], we do not read next pages.")    
                    break
        except Exception as e:
            self.say(f"❌ [{plan.keyword}] scraping error: {e}")
        finally:
            self.db.update_search_metrics(
                search_id, run.reads, 0, 0, 0
            )
            # Record basic scraping counts (no AI stats yet)
            self.scheduler.record_search(
                plan, search_id, run.pages, run.reads, run.title_rejected, 
                run.prefilter_failed, ai_jobs=0, ai_calls=0, successes=0, 
                maybes=0, bad_pages=run.bad_pages, stop_reason="scraped"
            )
        return self.scheduler.today_totals()

def register_user_keywords(scheduler: KeywordScheduler, raw_text: str, say=print) -> list[str]:
    names = []
    for text in split_keywords(raw_text):
        row, created = scheduler.register_user_keyword(text)
        if created:
            say(f"➕ Keyword saved: '{row['keyword']}'")
        names.append(row["keyword"])
    return names