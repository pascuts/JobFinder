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

# batch_processor.py
import asyncio
import os
import re
from openpyxl import load_workbook
from playwright.async_api import Page
from ai_assistant import AIAssistant
from excel_tracker import ExcelTracker


class JobBatchEvaluator:

    def __init__(self, page: Page, ai_assistant: AIAssistant, tracker: ExcelTracker):
        self.page = page
        self.ai = ai_assistant
        self.tracker = tracker

    async def process_and_evaluate_jobs(self, status_callback=None):
        wb_path = self.tracker.filename
        if not os.path.exists(wb_path):
            if status_callback:
                status_callback("⚠️ Excel file does not exist. Skipping enrichment step.")
            return

        # -------------------------------------------------------------
        # 1. ENRICH MISSING DESCRIPTIONS & COMPANY DETAILS
        # -------------------------------------------------------------
        rows_to_enrich = self.tracker.get_rows_needing_enrichment()
        if status_callback and rows_to_enrich:
            status_callback(
                f"[*] Found {len(rows_to_enrich)} rows needing details extraction..."
            )

        for item in rows_to_enrich:
            row_idx = item["row_idx"]
            link = item["job_url"]

            if not link or "linkedin.com" not in link:
                continue

            if status_callback:
                status_callback(f"[*] Navigating to direct job link: {link}")

            await self.page.bring_to_front()
            await self.page.goto(link, wait_until="domcontentloaded")

            # Enforce delay per requirements
            await asyncio.sleep(5)

            # Extract full Job Description
            desc_elem = self.page.locator(
                "#job-details, .jobs-description__content"
            ).first
            description = (
                await desc_elem.inner_text()
                if await desc_elem.count() > 0
                else "N/A"
            )

            # Extract Company Details
            comp_elem = self.page.locator(
                "section.jobs-company, .jobs-company__box"
            ).first
            company_details = (
                " ".join((await comp_elem.inner_text()).split())
                if await comp_elem.count() > 0
                else "Not Listed"
            )

            # Extract Point of Contact
            poc_selectors = [
                ".hirer-card__choice",
                ".jobs-poster",
                "section:has-text('Meet the hiring team')",
                "section:has-text('People you can reach out to')",
            ]
            poc_text = "Hiring Team"
            for sel in poc_selectors:
                elem = self.page.locator(sel).first
                if await elem.count() > 0 and await elem.is_visible():
                    raw = await elem.inner_text()
                    cleaned = re.sub(
                        r"(meet the hiring team|people you can reach out to|job poster)",
                        "",
                        raw,
                        flags=re.IGNORECASE,
                    ).strip()
                    poc_text = " ".join(cleaned.split()) or "Hiring Team"
                    break

            # Update Excel with enriched details
            self.tracker.update_job_details(
                row_idx, description.strip(), poc_text
            )

        # -------------------------------------------------------------
        # 2. EVALUATE ALL UNPROCESSED JOBS WITH COPILOT
        # -------------------------------------------------------------
        wb = load_workbook(wb_path)
        ws = wb["Jobs Log"]

        # Cache rows to iterate without holding openpyxl pointer locks
        job_rows = list(ws.iter_rows(min_row=2, values_only=True))
        wb.close()

        for row_idx, row in enumerate(job_rows, start=2):
            job_title = row[1]
            company = row[2]
            description = row[10] if len(row) > 10 else ""
            existing_status = row[12] if len(row) > 12 else ""

            if existing_status in ["ToApply", "DoNotApply", "Maybe"]:
                continue  # Skip already evaluated jobs

            if not description or description in ["N/A", "Not Listed"]:
                continue

            if status_callback:
                status_callback(
                    f"[*] Asking Copilot to evaluate job: {job_title} at {company}"
                )

            # Send interrogation prompt to Copilot
            interrogation_prompt = (
                f"Job Title: {job_title}\n"
                f"Company: {company}\n"
                f"Job Description:\n{description}\n\n"
                f"Based on my Master CV, certificates, and templates previously provided:\n"
                f"1. Should I apply for this job?\n"
                f"2. What score (0 to 100) is my compatibility with this job?\n"
                f"Provide your answer with a line explicitly formatted as: SCORE: <number>"
            )

            response_text = await self.ai.query_copilot(
                interrogation_prompt, return_to_page=self.page
            )

            # Parse score out of Copilot response
            score_match = re.search(
                r"SCORE:\s*(\d+)", response_text, re.IGNORECASE
            )
            score = int(score_match.group(1)) if score_match else 50

            # Determine application status classification
            if score > 60:
                status_text = "ToApply"
            elif score < 45:
                status_text = "DoNotApply"
            else:
                status_text = "Maybe"

            # -------------------------------------------------------------
            # 3. GENERATE TAILORED CV IF SCORE > 55
            # -------------------------------------------------------------
            cv_content = ""
            if score > 55:
                if status_callback:
                    status_callback(
                        f"[*] Score is {score} (> 55). Requesting CV generation from Copilot..."
                    )

                cv_prompt = (
                    f"Choose the best matching CV template from my loaded documents for the role of '{job_title}' at '{company}'. "
                    f"Create a new tailored CV making maximum 7 strategic changes to the best matching template to align with this job description. "
                    f"Output the full updated CV text."
                )
                cv_content = await self.ai.query_copilot(
                    cv_prompt, return_to_page=self.page
                )

            # Save status, score, and CV content to Excel
            self.tracker.update_evaluation_and_cv(
                row_idx, status_text, score, cv_content
            )

        # -------------------------------------------------------------
        # 4. SORT ROWS BY STATUS DESCENDING
        # -------------------------------------------------------------
        self.tracker.sort_by_status_descending()
        if status_callback:
            status_callback(
                "✅ Batch evaluation complete. Excel sorted by status descending."
            )