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

# automation_worker.py
import asyncio
import threading
from datetime import datetime
from PySide6.QtCore import QThread, Signal

from linkedin_bot import LinkedInBot
from govuk_jobs_bot import GovUkJobsBot
from base_portal_bot import BaseJobPortalBot
from gemini_assistant import GeminiAssistant
from base_assistant import BaseAIAssistant
from groq_assistant import GroqAssistant
from db_tracker import DatabaseTracker, DailyAIQuotaReached
from config_manager import ConfigManager
from keyword_scheduler import KeywordScheduler, SearchLimits
from keyword_seed import seed_database
from daily_runner import KeywordSearchEngine, register_user_keywords


class AutomationWorker(QThread):
    log_signal = Signal(str)
    progress_signal = Signal(dict)
    finished_signal = Signal(dict)
    error_prompt_signal = Signal(str, str, object)  # (step_name, error_msg, callback_event_container)
    refresh_tables_signal = Signal()

    def __init__(self, search_params: dict):
        super().__init__()
        self._common_cache_creation_time = None
        self.search_params = search_params
        self.db_tracker = DatabaseTracker()
        self.search_id = None
        self.bot = None
        self.base_AI = None
        self.config_mgr = ConfigManager()
        self.profile_folder = self.config_mgr.get_constant(ConfigManager.KEY_MY_PROF_PROFILE)
        self.step1_switched_to_backup = False
        self.step2_switched_to_backup = False

    def run(self):
        """Entry point for QThread."""
        self.log_signal.emit("[*] Worker thread started successfully...")
        try:           
            target_date = self.search_params.get("target_date", datetime.now().strftime("%Y-%m-%d"))
            
            do_scrapping = self.search_params.get("do_scrapping", False)
            do_scoring = self.search_params.get("do_scoring", False)
            do_changes = self.search_params.get("do_changes", False)
            portal_selection = self.search_params.get("portal", "")
            if "gov.uk" in portal_selection.lower():
                self.bot = GovUkJobsBot()
            else:
                self.bot = LinkedInBot()  # Default fallback
            self.base_AI = self.bot.ai_assistant.gemini
            
            # 1. Scraping Phase
            if do_scrapping:
                asyncio.run(self._execute_scrapping())

            # 2. AI Scoring Round
            if do_scoring:
                asyncio.run(self._run_ai_scoring_round(target_date, self.log_signal.emit))

            # 3. CV Changes Round
            if do_changes:
                asyncio.run(self._run_cv_changes_round(target_date, self.log_signal.emit))

            if not (do_scrapping or do_scoring or do_changes):
                self.log_signal.emit("⚠️ No action flags selected ('do_scrapping', 'do_scoring', 'do_changes').")

        except Exception as e:
            self.log_signal.emit(f"❌ Uncaught Thread Exception: {str(e)}")
        finally:
            self.bot.close()
            self.bot = None
            self.base_AI = None
            
    def stop(self):
        """Triggers QThread's built-in interruption flag."""
        self.requestInterruption()

    def _build_scheduler(self) -> KeywordScheduler:
        target = int(self.search_params.get("target_today_toapply", 30) or 30)
        limits = SearchLimits.from_config(self.config_mgr)
        scheduler = KeywordScheduler(self.db_tracker, limits)
        added = seed_database(scheduler.store)
        if added:
            self.log_signal.emit(f"[*] {len(added)} keywords added to search_keywords.")
        return scheduler

    async def _ensure_profile_cached(self, active_model: str, cache_for: str, say) -> bool:
        """Checks cache age against gemini_cache_duration; re-loads profiles if expired or missing."""
        cache_duration_mins = self.config_mgr.get_int(ConfigManager.KEY_GEM_CACHE_DURATION, 60)
        now = datetime.now()
        ai_name = self.base_AI.getAIAssistantName(active_model)  
        
        should_load = False
        if self._common_cache_creation_time is None:
            should_load = True
            say("[*] Initial profile cache load required...")
        else:
            elapsed_minutes = (now - self._common_cache_creation_time).total_seconds() / 60.0
            if elapsed_minutes >= cache_duration_mins:
                say(f"⏱️ Cache duration expired ({elapsed_minutes:.1f}m >= {cache_duration_mins}m limit). Reloading profile XMLs...")
                should_load = True
            else:
                say(f"✅ Cache active ({elapsed_minutes:.1f}m elapsed < {cache_duration_mins}m limit). Skipping reload.")
                if ai_name == ConfigManager.AI_GEMINI:
                    gemini = self.bot.ai_assistant.gemini
                    if not gemini.profile_cache:
                        gemini.profile_cache = gemini.list_active_remote_caches(cache_for)

        if should_load:
            if ai_name == ConfigManager.AI_GEMINI:
                gemini = self.bot.ai_assistant.gemini
                ok = await gemini.load_personal_profile_xmls(folder_path=self.profile_folder, cache_for=cache_for, status_callback=say, target_model=active_model)
            elif ai_name == ConfigManager.AI_GROQ:
                groq = self.bot.ai_assistant.groq
                ok = await groq.load_personal_profile_xmls(folder_path=self.profile_folder, cache_for=cache_for, status_callback=say, target_model=active_model)
            if ok:
                self._common_cache_creation_time = datetime.now()
            return ok
        return True

    # ------------------------------------------------------------------ #
    # PHASE 1: PURE LINKEDIN SCRAPING
    # ------------------------------------------------------------------ #
    async def _execute_scrapping(self):
        say = self.log_signal.emit
        try:
            keyword = self.search_params.get("keyword", "Enterprise Architect")
            target_input = self.search_params.get("target_input", "").strip()
            selected_domain = self.search_params.get("search_domain", "Keyword")
            scheduler = self._build_scheduler()
            
            L = scheduler.limits
            say(f"[*] Limits: target {L.daily_success_target} successes/day | {L.max_pages_per_keyword} pages and "
                f"{L.max_reads_per_keyword} jobs per keyword...")

            say("[*] Phase 0: Initializing browser...")
            await self.bot.init_browser()

            say("[*] Phase 1: Checking LinkedIn session...")
            authenticated = await self.bot.check_and_ensure_login(status_callback=say)
            if not authenticated:
                say("❌ LinkedIn authentication failed. Stopping execution.")
                return

            engine = KeywordSearchEngine(
                self.bot, scheduler,
                say=say,
                progress=self.progress_signal.emit,
                is_interrupted=self.isInterruptionRequested,
                search_meta=self.search_params,
            )

            if target_input.startswith(("http://", "https://")):
                say(f"[*] Navigating directly to provided URL: {target_input}")
                totals = await engine.run_url(target_input)
            elif selected_domain == "Keyword":
                names = register_user_keywords(scheduler, keyword, say)
                if not names:
                    say("⚠️ No keyword entered.")
                totals = scheduler.today_totals()
                for name in names:
                    if self.isInterruptionRequested():
                        break
                    say(f"[*] Searching LinkedIn for '{name}' ...")
                    totals = await engine.run_single(name)
            elif selected_domain == "ALL":
                say("[*] Rotating through all keywords...")
                totals = await engine.run_day()
            else:
                domain = selected_domain.replace("domain_", "", 1)
                if domain.lower() in {d.lower() for d in scheduler.store.domains()}:
                    say(f"[*] Rotating through the '{domain}' keywords...")
                    totals = await engine.run_day(domain=domain)
                else:
                    say(f"[*] '{selected_domain}' is not a known domain; searching as a keyword.")
                    totals = scheduler.today_totals()
                    for name in register_user_keywords(scheduler, selected_domain, say):
                        totals = await engine.run_single(name)

            self.finished_signal.emit(dict(totals))
            say("🚀 Scraping pipeline completed successfully!")

        except Exception as e:
            say(f"❌ Pipeline Execution Error: {str(e)}")
        finally:
            say("[*] Worker thread finished cleanup.")

    # ------------------------------------------------------------------ #
    # PHASE 2: AI SCORING ROUND
    # ------------------------------------------------------------------ #
    async def _run_ai_scoring_round(self, target_date: str, say):
        say("\n[*] --- Starting AI Score & Template Selection Round ---")
        scheduler = self._build_scheduler()
        max_ai_limit = scheduler.limits.max_ai_calls_per_day
        saved_jobs = self.db_tracker.get_jobs_by_status_and_date(
            criteria={"created_at": target_date, "job_status": "scraped"}, 
            limit=max_ai_limit
        )

        if len(saved_jobs)<=0:
            return

        # Determine active model based on user switching state
        active_step1_model = self.base_AI.getStep1ModelBackUp() if self.step1_switched_to_backup else self.base_AI.getStep1Model()       
        ai_name = self.base_AI.getAIAssistantName(active_step1_model)  
        ok = await self._ensure_profile_cached(active_step1_model, "score", say)
        if not ok:
            say("❌ Failed to load profile cache for scoring.")
            return
        
        calls_by_search: dict = {}       # search_id -> AI requests used in this round
        affected_search_ids = set()

        try:
            for job in saved_jobs:
                if self.isInterruptionRequested():
                    break

                job_id = job.get("job_id")
                job_title = job.get("title", "")
                company = job.get("company", "")
                description = job.get("description", "")
                match_score = int(job.get("match_score") or 0)

                say(f"🤖 Interrogating AI Score for Job {job_id} ({job_title})...")

                scoring_prompt = self.base_AI._build_scoring_prompt(
                    job_id=str(job_id),
                    job_title=job_title,
                    company=company,
                    description=description,
                    linkedin_match_status=match_score
                )

                calls_before = self.db_tracker.ai_calls_today()
                try:
                    if ai_name == ConfigManager.AI_GEMINI:
                        gemini = self.bot.ai_assistant.gemini
                        response_text = await gemini.query_ai(
                            scoring_prompt, 
                            expected_job_id=str(job_id), 
                            status_callback=say, 
                            target_model=active_step1_model
                        )
                    elif ai_name == ConfigManager.AI_GROQ:
                        groq = self.bot.ai_assistant.groq
                        response_text = await groq.query_ai(
                            scoring_prompt, 
                            expected_job_id=str(job_id), 
                            status_callback=say, 
                            target_model=active_step1_model
                        )
                    
                except DailyAIQuotaReached:
                    say("⛔ Daily AI allowance reached - stopping the scoring round.")
                    break
                except Exception as e:
                    action = self._prompt_user_on_error("Step 1 (Scoring)", str(e))
                    if action == "stop":
                        say("⛔ Execution stopped by user.")
                        return
                    elif action == "continue":
                        say("[*] Retrying Step 1 with current model...")
                        continue
                    elif action == "switch_backup":
                        if self.step1_switched_to_backup:
                            say("⚠️ Already running on Step 1 Backup Model. Cannot switch further. Stopping.")
                            return
                        say("🔄 Switching completely to Step 1 Backup Model. Resetting cache...")
                        self.step1_switched_to_backup = True
                        active_step1_model = self.base_AI.getStep1ModelBackUp()
                        self._common_cache_creation_time = None  # Cache lost/invalidated
                        
                        # Recursive call: picks up remaining unscraped/unscored jobs with backup model
                        await self._run_ai_scoring_round(target_date, say)
                        return
                finally:
                    used = self.db_tracker.ai_calls_today() - calls_before   # retries included

                result = self.base_AI._parse_xml(response_text, expected_job_id=str(job_id))

                score = result.get("score", -1000)
                status = result.get("job_status", "XXXStatus")
                cvtmpl_no = result.get("cvtmpl_no", -1)

                with self.db_tracker.get_connection() as conn:
                    row = conn.execute("SELECT search_id FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
                    search_id = row[0] if row else None
                if search_id:
                    affected_search_ids.add(search_id)
                    calls_by_search[search_id] = calls_by_search.get(search_id, 0) + max(used, 0)

                current_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                job_dict = {
                    "id": job_id,
                    "title": job.get("title", ""),
                    "company": job.get("company", ""),
                    "match_score": score,
                    "job_status": status,
                    "cvtmpl_no": cvtmpl_no,
                    "date_scoring": current_ts
                }
                eval_dict = {
                    "job_score_result": response_text,
                    "score": score,
                    "job_status": status,
                    "cvtmpl_no": cvtmpl_no
                }

                self.db_tracker.log_job(job_dict, eval_dict, search_id=search_id)

                say(f"✅ Score: {score}% | Status: {status} | Template: {cvtmpl_no}")
                await asyncio.sleep(1)
        finally:
            # Always runs - also after a stop request, a quota stop or an exception - so keyword
            # statistics never miss the jobs that were already scored.
            for s_id in affected_search_ids:
                try:
                    scheduler.update_search_ai_results(s_id, ai_calls=calls_by_search.get(s_id, 0))
                except Exception as e:
                    say(f"⚠️ Could not update statistics for search {s_id}: {e}")
            if affected_search_ids:
                say("📊 Keyword statistics, success rates and scores updated with the AI results.")

        # Emit signal to refresh UI tables upon completion of scoring round
        self.refresh_tables_signal.emit()

    # ------------------------------------------------------------------ #
    # PHASE 3: CV CHANGES ROUND
    # ------------------------------------------------------------------ #
    async def _run_cv_changes_round(self, target_date: str, say):
        say("\n[*] --- Starting CV Changes Round ---")
        scheduler = self._build_scheduler()
        daily_target = scheduler.limits.daily_success_target

        to_apply_jobs = self.db_tracker.get_jobs_by_status_and_date(
            criteria={"created_at": target_date, "job_status": "toapply"}, 
            limit=daily_target
        )

        if len(to_apply_jobs)<=0:
            return
        # Determine active model based on user switching state
        active_step2_model = self.base_AI.getStep2ModelBackUp() if self.step2_switched_to_backup else self.base_AI.getStep2Model()
        ai_name = self.base_AI.getAIAssistantName(active_step2_model) 
        ok = await self._ensure_profile_cached(active_step2_model, "cv", say)
        if not ok:
            say("❌ Failed to load profile cache for CV changes.")
            return
        
        for job in to_apply_jobs:
            if self.isInterruptionRequested():
                break

            job_id = job.get("job_id")
            job_title = job.get("title", "")
            company = job.get("company", "")
            description = job.get("description", "")
            tmpl_no = job.get("cvtmpl_no")
            if tmpl_no is None or int(tmpl_no) < 0:
                continue

            say(f"📝 Generating CV Changes for Job {job_id} using template #{tmpl_no}...")
            
            
            try:
                if ai_name == ConfigManager.AI_GEMINI:
                    gemini = self.bot.ai_assistant.gemini
                    response_text = await gemini.generate_cv_changes(
                        job_id=str(job_id),
                        job_title=job_title,
                        description=description,
                        cvtmpl_no=int(tmpl_no),
                        profile_folder=self.profile_folder,
                        status_callback=say,
                        target_model=active_step2_model
                    )
                elif ai_name == ConfigManager.AI_GROQ:
                    groq = self.bot.ai_assistant.groq
                    response_text = await groq.generate_cv_changes(
                        job_id=str(job_id),
                        job_title=job_title,
                        description=description,
                        cvtmpl_no=int(tmpl_no),
                        profile_folder=self.profile_folder,
                        status_callback=say,
                        target_model=active_step2_model
                    )
                else:
                    raise ValueError(f"Unsupported AI assistant provider: {ai_name}")

            except Exception as e:
                action = self._prompt_user_on_error("Step 2 (CV Changes)", str(e))
                if action == "stop":
                    say("⛔ Execution stopped by user.")
                    return
                elif action == "continue":
                    say("[*] Skipping current job and continuing...")
                    continue
                elif action == "switch_backup":
                    if self.step2_switched_to_backup:
                        say("⚠️ Already running on Step 2 Backup Model. Cannot switch further. Stopping.")
                        return

                    say("🔄 Switching completely to Step 2 Backup Model. Resetting cache and restarting round recursively...")
                    self.step2_switched_to_backup = True
                    active_step2_model = self.base_AI.getStep2ModelBackUp()
                    self._common_cache_creation_time = None  # Cache lost/invalidated
                    
                    # Recursive call: picks up remaining 'toapply' jobs with backup model
                    await self._run_cv_changes_round(target_date, say)
                    return
        
            self.db_tracker.update_job_evaluation_fields(job_id, [("cv_xml_response", response_text)])
            self.db_tracker.update_status(job_id, 'HasCVCngs')

            say(f"✅ CV changes saved for Job {job_id}")
            await asyncio.sleep(1)

        # Emit signal to refresh UI tables upon completion of scoring round
        self.refresh_tables_signal.emit()        
        
    def _prompt_user_on_error(self, step_name: str, error_msg: str) -> str:
        """Pauses the worker thread and waits for the user's choice via UI/Console."""
        choice_container = {"action": "stop"}
        event = threading.Event()
        
        # Emit signal to main thread to show the interactive prompt / dialog
        self.error_prompt_signal.emit(step_name, error_msg, (choice_container, event))
        
        # Block worker thread until user makes a selection
        event.wait()
        return choice_container["action"]