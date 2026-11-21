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

 # groq_assistant.py

import asyncio
import os
import pathlib
import pypdf
from groq import Groq

from base_assistant import BaseAIAssistant
from config_manager import ConfigManager

class GroqAssistant(BaseAIAssistant):
    """Groq-specific AI assistant implementation extending BaseAIAssistant via Groq SDK without browser dependencies."""

    def __init__(self):
        # Pass None for browser context as Groq API calls do not require a browser page
        super().__init__(None, ai_tool_name=ConfigManager.AI_GROQ)
        self.config_mgr = ConfigManager()
        # Retrieve Groq API Key from config or environment variable
        resolved_key = str( self.config_mgr.get_constant("groq_api_key") ).strip().strip("'").strip('"')
        self.client = Groq(api_key=resolved_key)
                
        self.profile_context = ""

    async def initialize_tab(self, status_callback=None) -> None:
        """Overrides browser tab initialization since API calls are headless."""
        if status_callback:
            status_callback("[*] Initializing Groq API Client (headless mode)...")
        return None

    def _validate_model(self, model_name: str):
        if model_name not in self.VALID_GROQ_MODELS:
            raise ValueError(f"Invalid Groq model name: '{model_name}'. Must be one of {self.VALID_GROQ_MODELS}")

    async def load_personal_profile_xmls(
        self, folder_path: str, max_retries: int = 9, status_callback=None, target_model: str = None
    ) -> bool:
        self.profile_context = ""
        """Reads profile XML files from folder_path and caches them in self.profile_context."""
        if target_model is None:
            raise ValueError("target_model is required.")
        self._validate_model(target_model)

        if not folder_path or not os.path.exists(folder_path):
            if status_callback:
                status_callback(f"⚠️ Profile folder path invalid: {folder_path}")
            return False

        profile_files = [
            str(p) for p in pathlib.Path(folder_path).glob("*.xml")
        ]

        if not profile_files:
            if status_callback:
                status_callback("⚠️ No XML profile or template files found in profile folder.")
            return False

        try:
            if status_callback:
                status_callback("[*] Reading profile XML documents locally for Groq API context...")

            combined_text = "Here is my master profile, CV templates, and background data:\n\n"
            
            for file_path in profile_files:
                file_name = os.path.basename(file_path).lower()
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    file_content = f.read()

                combined_text += f"=== FILE: {file_name} ===\n{file_content}\n\n"

            self.profile_context = combined_text
            
            if status_callback:
                status_callback(f"✅ Groq API successfully ingested {len(profile_files)} XML file(s) into profile context.")
            return True

        except Exception as e:
            if status_callback:
                status_callback(f"❌ Error during Groq local XML parsing: {str(e)}")
            return False
            
    async def query_ai(self, prompt_text: str, expected_job_id: str = "", status_callback=None, target_model: str = None) -> str:
        self._validate_model(target_model)
        
        """Sends job evaluation prompt and cached profile context directly to Groq API."""
        try:
            full_prompt = f"{self.profile_context}\n\nUser Request:\n{prompt_text}"
            
            # Execute synchronous SDK call inside an executor to avoid blocking asyncio loop
            loop = asyncio.get_running_loop()
            
            def call_groq():
                completion = self.client.chat.completions.create(
                    model=target_model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a job evaluation AI assistant. Strictly respond in the requested XML format."
                        },
                        {
                            "role": "user",
                            "content": full_prompt
                        }
                    ],
                    temperature=0.2,
                )
                return completion.choices[0].message.content

            response_text = await loop.run_in_executor(None, call_groq)
            return response_text

        except Exception as e:
            raise e
            
    async def generate_cv_changes(self, job_id: str, job_title: str, description: str, cvtmpl_no: int, profile_folder: str, status_callback=None, target_model: str = None) -> str:
        templates_folder = os.path.join(profile_folder, "cvtmpl")
        target_template_file = f"CVTemplate_{cvtmpl_no}.xml"
        template_content = ""

        if os.path.exists(templates_folder):
            for f in os.listdir(templates_folder):
                if f.lower() == target_template_file.lower():
                    file_path = os.path.join(templates_folder, f)
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
                            template_content = file.read()
                    except Exception:
                        pass

        prompt_text = self._build_cv_prompt(job_id, job_title, description, cvtmpl_no)
        if template_content:
            prompt_text += f"\n\nSelected CV Template (CVTemplate_{cvtmpl_no}.xml):\n{template_content}"

        return await self.query_ai(prompt_text, expected_job_id=job_id, status_callback=status_callback, target_model=target_model)