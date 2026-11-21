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

# ai_query_panel.py
import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QCheckBox, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Signal, Qt

class AIQueryPanel(QWidget):
    # Signal emitted when user clicks "AI Query" button
    start_ai_query_signal = Signal(dict)

    def __init__(self, db_tracker, parent=None):
        super().__init__(parent)
        self.db = db_tracker
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # -------------------------------------------------------------
        # TOP CONTROLS BAR
        # -------------------------------------------------------------
        controls_layout = QHBoxLayout()

        controls_layout.addWidget(QLabel("Scraped Date Filter:"))
        self.date_combo = QComboBox()
        self.date_combo.addItems(["Today", "Today - 1", "Today - 2", "Today - 4"])
        self.date_combo.setCurrentIndex(0)  # Default: Today
        self.date_combo.currentIndexChanged.connect(self.refresh_tables)
        controls_layout.addWidget(self.date_combo)

        controls_layout.addSpacing(20)

        self.chk_do_scoring = QCheckBox("Do Scoring")
        self.chk_do_scoring.setChecked(True)  # Default: Checked
        controls_layout.addWidget(self.chk_do_scoring)

        self.chk_do_changes = QCheckBox("Do Changes")
        self.chk_do_changes.setChecked(True)  # Default: Checked
        controls_layout.addWidget(self.chk_do_changes)

        controls_layout.addSpacing(20)

        self.btn_ai_query = QPushButton("🤖 AI Query")
        self.btn_ai_query.setStyleSheet("font-weight: bold; background-color: #007ACC; color: white; padding: 6px 12px;")
        self.btn_ai_query.clicked.connect(self.on_ai_query_clicked)
        controls_layout.addWidget(self.btn_ai_query)

        controls_layout.addStretch()
        main_layout.addLayout(controls_layout)

        # -------------------------------------------------------------
        # TABLES LAYOUT (SIDE-BY-SIDE OR STACKED)
        # -------------------------------------------------------------
        tables_layout = QHBoxLayout()

        # Table 1: Scraped Jobs (Scoring Queue)
        vbox_left = QVBoxLayout()
        vbox_left.addWidget(QLabel("<b>Scoring Queue (Status: 'Scraped')</b>"))
        self.table_scraped = QTableWidget()
        self.table_scraped.setColumnCount(4)
        self.table_scraped.setHorizontalHeaderLabels(["Job ID", "Title", "Company", "Status"])
        self.table_scraped.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        vbox_left.addWidget(self.table_scraped)
        tables_layout.addLayout(vbox_left)

        # Table 2: Scored Jobs (Status: ToApply)
        vbox_right = QVBoxLayout()
        vbox_right.addWidget(QLabel("<b>Scored Matches (Status: 'ToApply')</b>"))
        self.table_to_apply = QTableWidget()
        self.table_to_apply.setColumnCount(5)
        self.table_to_apply.setHorizontalHeaderLabels(["Job ID", "Title", "Company", "Score", "Template #"])
        self.table_to_apply.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        vbox_right.addWidget(self.table_to_apply)
        tables_layout.addLayout(vbox_right)

        main_layout.addLayout(tables_layout)

        # Initial load
        self.refresh_tables()

    def get_selected_target_date(self) -> str:
        """Calculates the cutoff date string (YYYY-MM-DD) based on dropdown choice."""
        today = datetime.date.today()
        mapping = {
            "Today": 0,
            "Today - 1": 1,
            "Today - 2": 2,
            "Today - 4": 4
        }
        days_back = mapping.get(self.date_combo.currentText(), 0)
        target_date = today - datetime.timedelta(days=days_back)
        return target_date.strftime("%Y-%m-%d")

    def refresh_tables(self):
        """Populates both tables according to the selected date filter."""
        target_date_str = self.get_selected_target_date()

        # 1. Populate Scraped Table (jobs with status 'scraped' >= target_date)
        scraped_jobs = self.db.get_jobs_by_status_and_date(
            criteria={"created_at": target_date_str, "job_status": "scraped"}, 
        )
        self.table_scraped.setRowCount(len(scraped_jobs))
        for row_idx, job in enumerate(scraped_jobs):
            self.table_scraped.setItem(row_idx, 0, QTableWidgetItem(str(job.get("job_id", ""))))
            self.table_scraped.setItem(row_idx, 1, QTableWidgetItem(str(job.get("title", ""))))
            self.table_scraped.setItem(row_idx, 2, QTableWidgetItem(str(job.get("company", ""))))
            self.table_scraped.setItem(row_idx, 3, QTableWidgetItem(str(job.get("job_status", "Scraped"))))

        # 2. Populate ToApply Table (jobs with status 'ToApply' >= target_date)
        to_apply_jobs = self.db.get_jobs_by_status_and_date(
            criteria={"created_at": target_date_str, "job_status": "toapply"}, 
        )
        self.table_to_apply.setRowCount(len(to_apply_jobs))
        for row_idx, job in enumerate(to_apply_jobs):
            self.table_to_apply.setItem(row_idx, 0, QTableWidgetItem(str(job.get("job_id", ""))))
            self.table_to_apply.setItem(row_idx, 1, QTableWidgetItem(str(job.get("title", ""))))
            self.table_to_apply.setItem(row_idx, 2, QTableWidgetItem(str(job.get("company", ""))))
            self.table_to_apply.setItem(row_idx, 3, QTableWidgetItem(f"{job.get('match_score', 0)}%"))
            self.table_to_apply.setItem(row_idx, 4, QTableWidgetItem(str(job.get("cvtmpl_no", "-1"))))

    def on_ai_query_clicked(self):
        """Gathers parameters and emits signal to launch AutomationWorker."""
        params = {
            "do_scoring": self.chk_do_scoring.isChecked(),
            "do_changes": self.chk_do_changes.isChecked(),
            "target_date": self.get_selected_target_date(),
        }
        self.start_ai_query_signal.emit(params)