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
import os
import re
import xml.etree.ElementTree as ET
from playwright.async_api import BrowserContext, Page
from config_manager import ConfigManager
from playwright.async_api import Locator


# Status Classification Constants
STATUS_TO_APPLY = "toapply"
STATUS_DO_NOT_APPLY = "donotapply"
STATUS_MAYBE = "maybe"

SCORE_TO_APPLY_THRESHOLD = 65
SCORE_DO_NOT_APPLY_THRESHOLD = 55

class BaseAIAssistant:
    """Contains shared prompt building, XML parsing, and validation logic for AI assistants."""
    VALID_GEMINI_MODELS = [
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash-lite",
        "gemini-3.6-flash",
        "gemini-3.8-flash",
        "gemini-3.1-pro-preview",
        "gemini-4-hydrogen",
        "gemini-4-carbon",
        "gemini-4-argon"
    ]
    VALID_GROQ_MODELS = [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "qwen/qwen3.6-27b",
        "qwen/qwen3.8-27b",
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant"
    ]
    
    def __init__(self, browser_context: BrowserContext, ai_tool_name: str):
        self.context = browser_context
        self.config_mgr = ConfigManager()
        self.page: Page = None
        self.ai_tool_name = ai_tool_name
        self.profile_context = ""

    async def initialize_tab(self, status_callback=None) -> Page:
        """Opens and navigates the dedicated AI tab using configuration URLs, or reuses it if already open."""
        if self.page and not self.page.is_closed():
            if status_callback:
                status_callback(f"[*] {self.ai_tool_name} tab already exists. Bringing to front...")
            await self.page.bring_to_front()
            return self.page

        if status_callback:
            status_callback(f"[*] Initializing {self.ai_tool_name} tab...")

        self.page = await self.create_ai_page()
        
        if status_callback:
            status_callback(f"✅ {self.ai_tool_name} tab successfully launched.")

        return self.page

    async def evaluate_job(
        self,
        job_id: str,
        job_title: str,
        company: str,
        description: str,
        linkedin_match_status: int = 0, # <-- Numeric int type
        status_callback=None,
    ) -> dict:
        """
        Queries the specified AI tool using structured XML prompts and parses the XML result to extract 
        the score and the full returned XML text as job_eval_result.
        """
        if status_callback:
            status_callback(
                f"[*] LinkedIn ID: {job_id}, LinkedIn score: {linkedin_match_status}. Asking {self.ai_tool_name} to evaluate: {job_title} at {company}..."
            )

        interrogation_prompt = self._build_prompt(
            job_id=job_id,
            job_title=job_title,
            company=company,
            linkedin_match_status=linkedin_match_status
        )

        response_text = await self.query_ai(
            prompt_text=interrogation_prompt, expected_job_id=job_id
        )
         
        # Debug print to terminal to see what the AI actually returned
        print(f"\n--- {self.ai_tool_name.upper()} RAW RESPONSE FOR {job_title} ---\n{response_text}\n------------------------------------------\n")

        # Parse structured XML response focusing on score and full XML content
        evaluation_result = self._parse_xml(response_text, expected_job_id=job_id)

        print(f"Parsed Match Score: {evaluation_result.get("score")} - {evaluation_result.get("job_status")}")

        return evaluation_result

    def _build_prompt(self, job_id, job_title, company, description, linkedin_match_status=0):
        prompt_path = os.path.join(os.path.dirname(__file__), "prompt.txt")
    
        # Read prompt from file if available, otherwise fall back to default template
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                template = f.read()
        else:
            template = (
                "Strictly output XML only.\n\n"
                "<JobResult><CompatibilityScore></CompatibilityScore></JobResult>\n\n"
                "LinkedIn Job ID: {job_id}\nJob Title: {job_title}\nCompany: {company}\nMatch Status: {linkedin_match_status}\nDescription: {description}"
            )

        return template.format(
            job_id=job_id,
            job_title=job_title,
            company=company,
            description=description,
            linkedin_match_status=linkedin_match_status
        )
    
    def _inject_error(self, raw_xml, message):
        idx = raw_xml.find("<Source>")
        if idx == -1:
            return f"<JobResult><Error>{message}</Error>" + raw_xml.replace("<JobResult>", "", 1)
        return raw_xml[:idx] + f"<Error>{message}</Error>" + raw_xml[idx:]

    def validate_job_result(self, raw_xml, expected_source, expected_uid, expected_job_name, template_titles):
        try:
            root = ET.fromstring(raw_xml)
        except Exception:
            return "<JobResult><Error>Malformed XML</Error><Source></Source></JobResult>"

        source = root.findtext("Source", "")
        uid = root.findtext("UniqueIdentifier", "")
        jobName = root.findtext("jobName", "")
        cvTemplateTitle = root.findtext("cvTemplateTitle", "")

        if source.strip() != expected_source.strip():
            return f"<JobResult><Error>Invalid Source: {source}</Error><Source></Source></JobResult>"
        if uid.strip() != expected_uid.strip():
            return f"<JobResult><Error>Invalid UniqueIdentifier: {uid}</Error><Source></Source></JobResult>"
        if jobName.strip() != expected_job_name.strip():
            return f"<JobResult><Error>Invalid jobName: {jobName}</Error><Source></Source></JobResult>"
        if cvTemplateTitle not in template_titles:
            return f"<JobResult><Error>Invalid cvTemplateTitle: {cvTemplateTitle}</Error><Source></Source></JobResult>"

        changes_node = root.find("changes")
        changes = []
        if changes_node is not None:
            for ch in changes_node.findall("change"):
                changes.append({
                    "cngNo": ch.findtext("cngNo", ""),
                    "reason": ch.findtext("reason", ""),
                    "changeSectionName": ch.findtext("changeSectionName", ""),
                    "changeContent": ch.findtext("changeContent", "")
                })

        return {
            "Source": source,
            "UniqueIdentifier": uid,
            "jobName": jobName,
            "cvTemplateTitle": cvTemplateTitle,
            "changes": changes
        }

    def validate_and_preserve(self, raw_xml, expected_source, expected_uid, expected_job_name, template_titles):
        try:
            root = ET.fromstring(raw_xml)
        except Exception:
            return "<JobResult><Error>Malformed XML</Error>" + raw_xml.replace("<JobResult>", "", 1)

        source = root.findtext("Source", "")
        uid = root.findtext("UniqueIdentifier", "")
        jobName = root.findtext("jobName", "")
        cvTemplateTitle = root.findtext("cvTemplateTitle", "")
        newCVTitle = root.findtext("NewCVTitle", "")

        if source.strip() != expected_source.strip():
            return self._inject_error(raw_xml, f"Invalid Source: {source}")
        if uid.strip() != expected_uid.strip():
            return self._inject_error(raw_xml, f"Invalid UniqueIdentifier: {uid}")
        if jobName.strip() != expected_job_name.strip():
            return self._inject_error(raw_xml, f"Invalid jobName: {jobName}")
        if cvTemplateTitle not in template_titles:
            return self._inject_error(raw_xml, f"Invalid cvTemplateTitle: {cvTemplateTitle}")
        if not newCVTitle.strip():
            return self._inject_error(raw_xml, "Invalid NewCVTitle: empty")

        return raw_xml

    async def load_personal_profile_xmls(
        self, folder_path: str, max_retries: int = 9, status_callback=None
    ) -> bool:
        """Uploads profile XMLs to the page and waits for the initial parsing response."""
        folder_path = folder_path+"/scoring/"
        if not folder_path or not os.path.exists(folder_path):
            if status_callback:
                status_callback(f"⚠️ Profile folder path invalid: {folder_path}")
            return False

        xml_files = [
            os.path.join(folder_path, f)
            for f in os.listdir(folder_path)
            if f.lower().endswith(".xml")
        ]

        if not xml_files:
            if status_callback:
                status_callback("⚠️ No XML files found in profile folder.")
            return False

        try:
            await self.page.bring_to_front()
            
            input_box = await self._wait_for_chat_input(status_callback)

            # Preload introductory text without pressing Enter so Copilot doesn't trigger voice mode
            pre_load_intro = "This is my LinkedIn profile, my certificates and a list of CV templates to apply for jobs"
            await self._type_and_press_enter_ai(input_box, pre_load_intro, False)
            await asyncio.sleep(2)

            file_input = self.page.locator("input[type='file']").first
            await file_input.set_input_files(xml_files)
            upload_success = False
            for attempt in range(max_retries):
                try:
                    if status_callback:
                        status_callback(f"[*] Iteration {attempt + 1}/{max_retries}: Checking file attachment and submit state...")
                    
                    await self.page.wait_for_selector(".file-preview, .upload-item, [class*='attachment']", timeout=2000)
                    upload_success = True
                    if status_callback:
                        status_callback(f"✅ XML files successfully loaded and verified on iteration {attempt + 1}.")
                    break
                except Exception:
                    if status_callback:
                        status_callback(f"[*] Iteration {attempt + 1}/{max_retries}: Files not yet confirmed. Waiting 10s and pressing Enter...")
                    
                    await asyncio.sleep(15)
                    await self.page.keyboard.press("Enter")
                    input_value = await input_box.input_value() if hasattr(input_box, "input_value") else await input_box.inner_text()
                    if not input_value.strip():
                        print("Enter key successfully submitted the input!")
                        break

            if not upload_success and status_callback:
                status_callback("⚠️ Max retries reached. Proceeding after upload attempts...")

            await asyncio.sleep(10)

            init_prompt = "These are my loaded profile and CV templates in XML format."

            if status_callback:
                status_callback("[*] Submitting profile XMLs...")

            await self._type_and_press_enter_ai(input_box, init_prompt)

            if status_callback:
                status_callback(
                    "[*] Waiting to process attached XML documents..."
                )

            response_locator = self.page.locator(
                "div[data-content='ai-message'], .cib-message-main, div.message-content, [role='region'], message-content, .model-response-text"
            )

            try:
                await response_locator.last.wait_for(
                    state="visible", timeout=30000
                )
                await asyncio.sleep(10)
            except Exception:
                await asyncio.sleep(15)

            if status_callback:
                status_callback(
                    "✅ Document processing finished. Starting pipeline."
                )

            return True

        except Exception as e:
            if status_callback:
                status_callback(f"❌ Error during XML ingestion: {str(e)}")
            return False

    def _parse_xml(self, raw: str, expected_job_id: str = ""):
        try:
            # 1. Clean non-printable control characters
            raw_clean = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', raw)

            # 2. Extract <JobResult>...</JobResult>
            match = re.search(r"<JobResult\b[^>]*>(.*?)</JobResult>", raw_clean, re.DOTALL | re.IGNORECASE)
            if not match:
                print("[!] No JobResult XML found.")
                return {
                    "score": -1000,
                    "cvtmpl_no": -1000,
                    "job_status": "Error",
                    "job_score_result": raw_clean,
                }

            raw_cleaned = "<JobResult>" + match.group(1).strip() + "</JobResult>"

            # 3. Parse fields using ElementTree
            root = ET.fromstring(raw_cleaned)

            def get_text(tag_name: str, default: str = "") -> str:
                node = root.find(tag_name)
                return node.text.strip() if node is not None and node.text else default

            score = int(get_text("CompatibilityScore", "-1000"))
            cvtmpl_no = int(get_text("cvTemplateNo", "-1000"))
            status_text = get_text("TOAPPLYSTATUS", "Error")

            return {
                "score": score,
                "cvtmpl_no": cvtmpl_no,
                "job_status": status_text,
                "job_score_result": raw_cleaned,
            }

        except Exception as e:
            print(f"[!] Exception in _parse_xml: {str(e)}")
            return {
                "score": -1000,
                "cvtmpl_no": -1000,
                "job_status": "Error",
                "job_score_result": raw,
            }


    async def _type_and_press_enter_ai(self, input_box, text: str, pressEnter: bool = True):
        """Focuses input, sets the full text block instantly, and submits."""
        box = await input_box.bounding_box()
        if box:
            await self.page.mouse.click(
                box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            )
        else:
            await input_box.click(force=True)

        await asyncio.sleep(0.5)
        await input_box.focus()

        # Instantly set the entire text payload into the element
        await input_box.fill(text)

        # Force-trigger framework events so Copilot's React UI registers the value and displays the submit arrow
        await self.page.evaluate(
            """() => {
                const element = document.querySelector("textarea, div[contenteditable='true'], .ql-editor");
                if (element) {
                    element.dispatchEvent(new Event('input', { bubbles: true }));
                    element.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }"""
        )

        await asyncio.sleep(1)
        
        if pressEnter:
            await self.page.keyboard.press("Enter")
            await asyncio.sleep(1.5)

            # Fallback: explicitly look for and click the submit button if it's visible
            try:
                submit_btn = self.page.locator(
                    "button[aria-label*='Submit'], button[aria-label*='Send'], button:has(svg)"
                ).last

                if await submit_btn.is_visible() and await submit_btn.is_enabled():
                    btn_box = await submit_btn.bounding_box()
                    if btn_box:
                        await self.page.mouse.click(
                            btn_box["x"] + btn_box["width"] / 2,
                            btn_box["y"] + btn_box["height"] / 2,
                        )
            except Exception:
                pass

    async def _type_and_press_enter_ai2(self, input_box, text: str, pressEnter: bool = True):
        """Focuses input, types text sequentially using native events to wake up UI state, and submits."""
        box = await input_box.bounding_box()
        if box:
            await self.page.mouse.click(
                box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
            )
        else:
            await input_box.click(force=True)

        await asyncio.sleep(0.5)
        await input_box.focus()

        # Clear any existing text first just in case
        await input_box.fill("")
        
        # Type text sequentially so Copilot's React framework registers the changes and shows the submit arrow
        await input_box.press_sequentially(text, delay=5)

        await asyncio.sleep(2)
        
        if pressEnter:
            await self.page.keyboard.press("Enter")
            await asyncio.sleep(1.5)

            # Fallback: explicitly look for and click the submit button if it's visible
            try:
                submit_btn = self.page.locator(
                    "button[aria-label*='Submit'], button[aria-label*='Send'], button:has(svg)"
                ).last

                if await submit_btn.is_visible() and await submit_btn.is_enabled():
                    btn_box = await submit_btn.bounding_box()
                    if btn_box:
                        await self.page.mouse.click(
                            btn_box["x"] + btn_box["width"] / 2,
                            btn_box["y"] + btn_box["height"] / 2,
                        )
            except Exception:
                pass

    async def create_ai_page(self) -> Page:
        key = f"{self.ai_tool_name.lower()}_url"
        ai_url = self.config_mgr.get_constant(key)

        new_page = await self.context.new_page()
        await new_page.goto(
            ai_url, wait_until="domcontentloaded"
        )
        return new_page

    async def _wait_for_chat_input(self, status_callback=None) -> Locator:
        """Waits for the chat input box to become visible, handling sign-in prompts if necessary."""
        input_box = self.page.locator("textarea, div[contenteditable='true']").first
        
        is_visible = False
        for _ in range(20):
            if await input_box.is_visible():
                is_visible = True
                break
            if status_callback and _ == 0:
                status_callback("⚠️ Sign-in detected. Please complete login in browser...")
            await asyncio.sleep(5)

        if not is_visible:
            if status_callback:
                status_callback("❌ Chat input not visible. Login incomplete.")
            return None

        return input_box

    def _get_xml_tag_text(self, xml_content: str, tag_name: str, default: str = "") -> str:
            """
            Cleans control characters and extracts inner text for a given XML tag name.
            """
            if not xml_content:
                return default
        
            # Strip ASCII control characters (\x00-\x08, \x0B, \x0C, \x0E-\x1F)
            cleaned = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', xml_content)
        
            pattern = rf'<{tag_name}(?:\s+[^>]*)?>\s*(.*?)\s*'
            match = re.search(pattern, cleaned, re.DOTALL | re.IGNORECASE)
        
            return match.group(1).strip() if match else default


    def _build_scoring_prompt(self, job_id, job_title, company, description, linkedin_match_status=0):
        prompt_path = os.path.join(os.path.dirname(__file__), "promptScoring.txt")
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                template = f.read()
            return template.format(
                job_id=job_id, job_title=job_title, company=company,
                description=description, linkedin_match_status=linkedin_match_status
            )
        else:
            return ""
        

    def _build_cv_prompt(self, job_id, job_title, description, cvtmpl_no: int):
        prompt_path = os.path.join(os.path.dirname(__file__), "promptCV.txt")
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                template = f.read()
            return template.format(
                job_id=job_id, job_title=job_title, description=description,
                cvtmpl_no=cvtmpl_no
            )
        else:
            return ""

    def _load_cv_template_file(self, folder_path: str, cvtmpl_no: int) -> str:
        """Locates and reads the specific CV template XML file matching cvtmpl_no from the cvtmpl folder."""
        if not folder_path:
            return "failed"
            
        templates_folder = os.path.join(folder_path, "cvtmpl")           
        if not os.path.exists(templates_folder):
            return "failed"

        target_template_file = f"CVTemplate_{cvtmpl_no}.xml"

        for f in os.listdir(templates_folder):
            # Matches XML files like CVTemplate_3.xml containing the template number
            if f.lower() == target_template_file.lower():
                file_path = os.path.join(templates_folder, f)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as file:
                        return file.read()
                except Exception:
                    pass
        return ""
        
    def getStep1Model(self) -> str:
        return self.config_mgr.get_constant("model_name_step1") or "gemini-3.1-flash-lite"

    def getStep1ModelBackUp(self) -> str:
        return self.config_mgr.get_constant("backup_model_name_step1") or "gemini-3.5-flash-lite"

    def getStep2Model(self) -> str:
        return self.config_mgr.get_constant("model_name_step2") or "openai/gpt-oss-120b"

    def getStep2ModelBackUp(self) -> str:
        return self.config_mgr.get_constant("backup_model_name_step2") or "gemini-3.5-flash-lite"
        
    @staticmethod
    def getAIAssistantName(target_model: str) -> str:
        """Returns the ConfigManager AI assistant identifier based on the target model name."""
        if not target_model:
            return ConfigManager.AI_COPILOT

        clean_model = target_model.strip()

        if clean_model in BaseAIAssistant.VALID_GEMINI_MODELS:
            return ConfigManager.AI_GEMINI
        elif clean_model in BaseAIAssistant.VALID_GROQ_MODELS:
            return ConfigManager.AI_GROQ
        else:
            return ConfigManager.AI_COPILOT