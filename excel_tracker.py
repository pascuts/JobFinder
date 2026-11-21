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

import os
from datetime import datetime
from openpyxl import Workbook, load_workbook
from db_tracker import DatabaseTracker


class ExcelTracker:

    def __init__(self, filename="Job_Applications_Tracker.xlsx", db_tracker=None):
        self.filename = filename
        self.sheet_name = "LInJobs"
        self.processed_sheet_name = "processed"
        self.ignore_sheet_name = "Ignore"
        self.headers = [
            "Job ID",
            "Job Title",
            "Date Extracted",
            "Status",
            "Match Score",
            "Company",
            "Point of Contact",
            "Location",
            "Salary",
            "Hybrid Y/N",
            "Work Type",
            "Link",
            "Job Description",
            "CV4Job",
        ]
        self.processed_headers = [
            "Job ID",
            "Job Title",
            "Date Extracted",
            "Status",
            "Match Score",
            "Company",
            "Point of Contact",
        ]
        self.db = db_tracker if db_tracker else DatabaseTracker()
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        """Creates the workbook and 'LInJobs' worksheet if it doesn't exist."""
        if not os.path.exists(self.filename):
            wb = Workbook()
            ws = wb.active
            ws.title = self.sheet_name
            ws.append(self.headers)
            wb.save(self.filename)
            wb.close()
        else:
            wb = load_workbook(self.filename)
            if self.sheet_name not in wb.sheetnames:
                ws = wb.create_sheet(title=self.sheet_name)
                ws.append(self.headers)
                wb.save(self.filename)
            wb.close()


    def get_existing_job_ids(self) -> set:
        """Reads column A (Job ID) from 'LInJobs' to prevent duplicate entries."""
        if not os.path.exists(self.filename):
            return set()

        wb = load_workbook(self.filename, read_only=True)
        if self.sheet_name not in wb.sheetnames:
            wb.close()
            return set()

        ws = wb[self.sheet_name]
        existing_ids = set()

        for row in ws.iter_rows(min_row=2, values_only=True):
            if row and row[0]:
                existing_ids.add(str(row[0]).strip())

        wb.close()
        return existing_ids

    def log_jobs(self, extracted_jobs: list[dict]) -> int:
        """Appends new jobs to 'LInJobs' using the updated column layout."""
        existing_ids = self.get_existing_job_ids()
        added_count = 0

        wb = load_workbook(self.filename)
        ws = wb[self.sheet_name]

        for job in extracted_jobs:
            job_id = str(job.get("id", "")).strip()

            if job_id and job_id not in existing_ids:
                row_data = [
                    job_id,  # Job ID
                    job.get("title", ""),  # Job Title
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # Date Extracted
                    job.get("status", "Extracted"),  # Status
                    job.get("match_score", ""),  # Match Score
                    job.get("company", ""),  # Company
                    job.get("point_of_contact", ""),  # Point of Contact
                    job.get("location", ""),  # Location
                    job.get("salary", ""),  # Salary
                    job.get("hybrid", ""),  # Hybrid Y/N
                    job.get("work_type", ""),  # Work Type
                    job.get("job_url", ""),  # Link
                    job.get("description", ""),  # Job Description
                    job.get("cv4job", ""),  # CV4Job
                ]
                ws.append(row_data)
                existing_ids.add(job_id)
                added_count += 1

        if added_count > 0:
            wb.save(self.filename)

        wb.close()
        return added_count

    def log_job(self, job: dict, eval_copilot_result: dict) -> bool:
        """
        Logs a single job entry along with its Copilot evaluation results into the 'LInJobs' worksheet.
        Appends a new row if the job ID does not already exist, or updates it if found.
        """
        wb = load_workbook(self.filename)
        ws = wb[self.sheet_name]
        
        job_id = str(job.get("id", "")).strip()
        # Extract Copilot evaluation details
        status = eval_copilot_result.get("status", "N/A")
        score = eval_copilot_result.get("score", -1000)
        job_score_result = eval_copilot_result.get("job_score_result", "")

        row_data = [
            job_id,  # Job ID
            job.get("title", ""),  # Job Title
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # Date Extracted
            status,
            score,
            job.get("company", ""),  # Company
            job.get("point_of_contact", ""),  # Point of Contact
            job.get("location", ""),  # Location
            job.get("salary", ""),  # Salary
            job.get("hybrid", ""),  # Hybrid Y/N
            job.get("work_type", ""),  # Work Type
            job.get("job_url", ""),  # Link
            job.get("description", ""),  # Job Description
            job_score_result
        ]
        row_data = [self.sanitize_cell_value(item) for item in row_data]
        ws.append(row_data)
        wb.save(self.filename)
        wb.close()
        return True

    def process_scored_jobs(self):
        """
        Moves 'DoNotApply' and 'Maybe' jobs completely to the 'Ignore' sheet.
        Moves other valid scored jobs to 'processed', backs up full deleted rows 
        to a timestamped backup file, and removes moved rows from 'LInJobs'.
        """
        if not os.path.exists(self.filename):
            return

        wb = load_workbook(self.filename)
        if self.sheet_name not in wb.sheetnames:
            wb.close()
            return

        ws_source = wb[self.sheet_name]

        # Ensure target sheets exist with headers
        if self.processed_sheet_name not in wb.sheetnames:
            ws_target_processed = wb.create_sheet(title=self.processed_sheet_name)
            ws_target_processed.append(self.processed_headers)
        else:
            ws_target_processed = wb[self.processed_sheet_name]

        if self.ignore_sheet_name not in wb.sheetnames:
            ws_target_ignore = wb.create_sheet(title=self.ignore_sheet_name)
            ws_target_ignore.append(self.headers)
        else:
            ws_target_ignore = wb[self.ignore_sheet_name]

        rows_to_delete_indices = []
        full_rows_to_backup = []

        ignore_statuses = {"donotapply", "maybe"}

        # Iterate through data rows (skipping header)
        for row_idx, row in enumerate(
            ws_source.iter_rows(min_row=2, values_only=True), start=2
        ):
            if not row or row[0] is None:
                continue

            # Read Status (column index 3) and Match Score (column index 4)
            status_val = str(row[3]).strip().lower() if row[3] is not None else ""
            match_score = row[4]

            # 1. ACTION FOR IGNORED JOBS ("DoNotApply" / "Maybe")
            if status_val in ignore_statuses:
                # Append full row (all 15 columns) to 'Ignore' sheet
                ws_target_ignore.append(list(row))
                
                # Store full row and index for backup & deletion from main sheet
                full_rows_to_backup.append(row)
                rows_to_delete_indices.append(row_idx)

            # 2. ACTION FOR REGULAR VALID SCORED JOBS
            elif (
                match_score is not None
                and match_score != ""
                and str(match_score) != "-1000"
            ):
                # Build truncated row for 'processed' sheet
                processed_row = [
                    row[0],  # Job ID
                    row[1],  # Job Title
                    row[2],  # Date Extracted
                    row[3],  # Status
                    row[4],  # Match Score
                    row[5],  # Company
                    row[6],  # Point of Contact
                ]
                ws_target_processed.append(processed_row)

                # Store full row and index for backup & deletion from main sheet
                full_rows_to_backup.append(row)
                rows_to_delete_indices.append(row_idx)

        # Create Backup file if rows were moved
        if full_rows_to_backup:
            base, ext = os.path.splitext(self.filename)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"{base}_BkUp_{timestamp}{ext}"

            wb_backup = Workbook()
            ws_backup = wb_backup.active
            ws_backup.title = "Deleted_Backup"
            ws_backup.append(self.headers)

            for backup_row in full_rows_to_backup:
                ws_backup.append(list(backup_row))

            wb_backup.save(backup_filename)
            wb_backup.close()

            # Delete moved rows in reverse order to keep indices stable
            for row_idx in reversed(rows_to_delete_indices):
                ws_source.delete_rows(row_idx)

            wb.save(self.filename)

        wb.close()

    def sync_to_db(self) -> int:
        """Invokes the database tracker to persist all records from 'LInJobs' to SQLite."""
        return self.db.save_linjobs_from_excel(
            excel_filename=self.filename, sheet_name=self.sheet_name
        )

    # In excel_tracker.py -> log_job
    def sanitize_cell_value(self, val):
        if isinstance(val, dict):
            # Convert dictionary values or extract specific string representations
            return ", ".join(f"{k}: {v}" for k, v in val.items())
        return val