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

# File name: gemini_assistant.py

import asyncio
import os
import pathlib
import pypdf
from google import genai
from base_assistant import BaseAIAssistant
from config_manager import ConfigManager
from datetime import datetime, timezone
from google.genai import types
from db_tracker import DatabaseTracker, DailyAIQuotaReached, HARD_MAX_AI_CALLS_PER_DAY


class GeminiAssistant(BaseAIAssistant):
    def __init__(self):
        # We pass None for the browser context since API communication does not use a browser page
        super().__init__(None, ai_tool_name=ConfigManager.AI_GEMINI)
        
        # Initialize the official Google GenAI client
        self.config_mgr = ConfigManager()
        resolved_key = self.config_mgr.get_constant("gemini_api_key")
        self.client = genai.Client(api_key=resolved_key)
        # Step 1 Model configuration with backup fallback
        self.profile_context = ""
        self.profile_cache = None
        # Daily Gemini request allowance, persisted in the DB (never above 250)
        self.db_tracker = DatabaseTracker()
        self.max_ai_calls_per_day = min(
            self.config_mgr.get_int(ConfigManager.KEY_MAX_AI_CALLS_DAY), HARD_MAX_AI_CALLS_PER_DAY
        )
        
    def _validate_model(self, model_name: str):
        if model_name not in self.VALID_GEMINI_MODELS:
            raise ValueError(f"Invalid Gemini model name: '{model_name}'. Must be one of {self.VALID_GEMINI_MODELS}")
            
    async def initialize_tab(self, status_callback=None) -> None:
        """Overrides browser tab initialization since API calls are headless and require no browser page."""
        if status_callback:
            status_callback("[*] Initializing Gemini API Client (headless mode)...")
        return None

    async def load_personal_profile_xmls(
        self,
        folder_path: str,
        max_retries: int = 9,
        status_callback=None,
        db_tracker=None,
        cache_for: str = "score",
        target_model: str = None,
    ) -> bool:
        self.profile_context = ""
        self._validate_model(target_model)
        
        db = db_tracker or getattr(self, "db_tracker", None) or DatabaseTracker()

        clean_cache_for = "cv" if cache_for.lower() == "cv" else "score"

        # 1. Check DB for valid cache matching the target type ('score' or 'cv')
        cached_obj = self.list_active_remote_caches(clean_cache_for)
        cache_id = getattr(cached_obj, "name", None)
        if cached_obj is not None: 
            valid_cache_record = db.get_valid_profile_cache(cache_for=clean_cache_for, buffer_minutes=5)
            if valid_cache_record:
                cache_id = valid_cache_record["cache_id"]
                try:
                    cached_obj = self.client.caches.get(name=cache_id)
                except Exception as e:
                    cached_obj = None
                    if status_callback:
                        status_callback(f"⚠️ Cache in DB invalid or expired on server ({str(e)}). Re-creating...")           
        if cached_obj is not None: 
            self.profile_cache = cached_obj
            if status_callback:
                status_callback(f"✅ Loaded valid Context Cache ({clean_cache_for}) from DB: {cache_id}")
            self.display_cache(status_callback)
            return True
    
        # 2. Build combined text profile from folder
        target_folder = folder_path + "/scoring/"
        if not target_folder or not os.path.exists(target_folder):
            if status_callback:
                status_callback(f"⚠ Profile folder path invalid: {target_folder}")
            return False

        profile_files = [
            str(p) for p in pathlib.Path(target_folder).glob("*.*") 
            if p.suffix.lower() == ".xml"
        ]

        if not profile_files:
            if status_callback:
                status_callback("⚠️ No XML profile or template files found in profile folder.")
            return False

        try:
            if status_callback:
                status_callback(f"[*] Reading profile XML documents locally to create Gemini Context Cache ({clean_cache_for})...")

            combined_text = "Here is my master profile, CV templates, and background data:\n\n"
        
            for file_path in profile_files:
                file_name = os.path.basename(file_path).lower()
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    file_content = f.read()

                combined_text += f"=== FILE: {file_name} ===\n{file_content}\n\n"

            self.profile_context = combined_text

            if status_callback:
                status_callback(f"[*] Uploading profile context to Gemini Server Cache for {clean_cache_for}...")
            
            cache_duration = int(self.config_mgr.get_constant(ConfigManager.KEY_GEM_CACHE_DURATION)) * 60
            ttl_str = f"{cache_duration}s"
            cache = self.client.caches.create(
                model=target_model,
                config=types.CreateCachedContentConfig(
                    display_name=f"cache_{clean_cache_for}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                    contents=[combined_text],
                    ttl=ttl_str
                )
            )
            
            self.profile_cache = cache

            meta = getattr(cache, "usage_metadata", None)
            tk = getattr(meta, "total_token_count", 0) if meta else 0

            exp_time = getattr(cache, "expire_time", datetime.now(timezone.utc))
            exp_iso = exp_time.strftime("%Y-%m-%d %H:%M:%S")

            # 3. Save cache record to DB with cache_for populated
            db.save_profile_cache(
                cache_id=cache.name,
                display_name=getattr(cache, "display_name", f"job_{clean_cache_for}_profile_context"),
                model=getattr(cache, "model", target_model),
                token_count=tk,
                expires_at_iso=exp_iso,
                cache_for=clean_cache_for,
            )

            if status_callback:
                status_callback(
                    f"✅ Context Cache created & saved to DB! Type: {clean_cache_for} | Name: {cache.name} (Expires at {exp_iso} UTC)"
                )
            return True

        except Exception as e:
            if status_callback:
                status_callback(f"❌ Error during Gemini Context Cache creation: {str(e)}")
            return False
    
    async def query_ai(self, prompt_text: str, expected_job_id: str = "", status_callback=None, target_model: str = None, ignore_quota: bool = False, attachment_path: str = None) -> str:   
        self._validate_model(target_model)
        
        # Build contents payload, attaching the file object if provided
        parts = []
        if attachment_path and os.path.exists(attachment_path):
            # Upload file attachment to Gemini API for this request
            uploaded_file = self.client.files.upload(file=attachment_path)
            parts.append(uploaded_file)

        parts.append(prompt_text)

        if self.profile_cache and hasattr(self.profile_cache, "name"):
            config = types.GenerateContentConfig(cached_content=self.profile_cache.name)
            contents_payload = [parts] if isinstance(parts, list) else [parts] # or structured contents config depending on SDK version
        else:
            config = None
            contents_payload = [self.profile_context, *parts]

        max_retries = 5
        base_delay = 2  # seconds
        
        for attempt in range(max_retries):
            if not ignore_quota:
                if not self.db_tracker.try_reserve_ai_call(self.max_ai_calls_per_day):
                    raise DailyAIQuotaReached(
                        f"Daily Gemini allowance of {self.max_ai_calls_per_day} requests is used up."
                    )
            try:
                loop = asyncio.get_running_loop()
            
                def _execute_call():
                    return self.client.models.generate_content(
                        model=target_model,
                        contents=contents_payload,
                        config=config,
                    )

                response = await loop.run_in_executor(None, _execute_call)
                return response.text

            except Exception as e:
                error_msg = str(e)
                is_transient = any(err in error_msg for err in ["503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED"])

                if is_transient and attempt < max_retries - 1:
                    wait_time = base_delay * (2 ** attempt)
                    if status_callback:
                        status_callback(
                            f"⚠️ [WARN] Gemini API Throttled (503/429). Retrying in {wait_time}s... (Attempt {attempt + 1}/{max_retries})"
                        )
                    await asyncio.sleep(wait_time)
                else:
                    if status_callback:
                        status_callback(f"❌ Model {target_model} failed ({error_msg}). Falling back...")
                    raise e
        

    def display_cache(self, status_callback=None) -> dict:
        """Logs all Gemini Context Cache metadata on a single squeezed line using acronyms."""
        if not getattr(self, "profile_cache", None):
            msg = "⚠️ Cache Status: None"
            (status_callback or print)(msg)
            return {}

        c = self.profile_cache
        c_id = getattr(c, "name", "N/A")
        dn = getattr(c, "display_name", "N/A")
        mdl = getattr(c, "model", "N/A")
    
        meta = getattr(c, "usage_metadata", None)
        tk = getattr(meta, "total_token_count", "?") if meta else "?"

        exp_at = getattr(c, "expire_time", None)
        exp_str = exp_at.strftime("%H:%M:%S UTC") if exp_at else "N/A"

        is_expired, rem_str = False, "?"
        if exp_at:
            diff_s = (exp_at - datetime.now(timezone.utc)).total_seconds()
            if diff_s <= 0:
                is_expired, rem_str = True, "0m0s (EXPIRED)"
            else:
                m, s = divmod(int(diff_s), 60)
                rem_str = f"{m}m{s}s"

        icon = "❌" if is_expired else "✅"
        # Squeezed single-line log
        single_line_msg = (
            f"{icon} EXP:{exp_str} |REM:{rem_str} |DN:{dn} |CN:{c_id} |M:{mdl} |TK:{tk} "
        )

        (status_callback or print)(single_line_msg)

        return {
            "cache_id": c_id, "display_name": dn, "model": mdl,
            "token_count": tk, "expires_at": exp_str, "time_remaining": rem_str,
            "is_expired": is_expired
        }

    def list_active_remote_caches(self, cache_for: str = "score"):
        """Retrieves the active Gemini server cache with the highest expiration time

        matching cache_for in display_name.

        Returns:
            CachedContent object (same as client.caches.get) or None if not found.
        """
        clean_cache_for = "cv" if cache_for.lower() == "cv" else "score"
        matching_caches = []

        try:
            # 1. Fetch active caches from Google GenAI SDK
            remote_caches = list(self.client.caches.list())

            # 2. Filter caches where display_name contains cache_for
            for cache in remote_caches:
                display_name = getattr(cache, "display_name", "") or ""
                if clean_cache_for in display_name.lower():
                    matching_caches.append(cache)

            if not matching_caches:
                return None

            # 3. Sort descending by expire_time and pick the highest expiration match
            matching_caches.sort(
                key=lambda c: getattr(c, "expire_time", None) or datetime.min,
                reverse=True,
            )

            return matching_caches[0]

        except Exception as e:
            print(f"❌ Error fetching remote caches: {str(e)}")
            return None

    async def generate_cv_changes(self, job_id: str, job_title: str, description: str, cvtmpl_no: int, profile_folder: str, status_callback=None, target_model: str = None) -> str:
        self._validate_model(target_model)
        
        """Generates tailored CV changes by combining promptCV.txt, the profile context cache, and attaching the specific CV template file."""
        templates_folder = os.path.join(profile_folder, "cvtmpl")
        target_template_file = f"CVTemplate_{cvtmpl_no}.xml"
        attachment_path = None

        if os.path.exists(templates_folder):
            for f in os.listdir(templates_folder):
                if f.lower() == target_template_file.lower():
                    attachment_path = os.path.join(templates_folder, f)
                    break

        prompt_text = self._build_cv_prompt(job_id, job_title, description, cvtmpl_no)
        
        # Pass the template path as an attachment to query_ai
        response = await self.query_ai(
            prompt_text, 
            expected_job_id=job_id, 
            status_callback=status_callback,
            target_model = target_model,            
            ignore_quota=True, 
            attachment_path=attachment_path
        )
        return response