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

# ui_panel.py
import sys
from db_tracker import DatabaseTracker
from adzuna_panel import AdzunaPanel
from keyword_store import KeywordStore
from keyword_seed import seed_database
from config_manager import ConfigManager
from log_search import SearchableLogEdit
from db_search_panel import DBSearchPanel
from bkup_panel import BkupPanel
from multi_select_combobox import MultiSelectComboBox
from ai_query_panel import AIQueryPanel
from searches_panel import SearchesPanel
from keywords_panel import KeywordsPanel
from job_view_panel import JobViewPanel
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTabWidget,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class JobAssistantUI(QWidget):
    start_search_requested = Signal(dict)
    stop_search_requested = Signal()

    def __init__(self):
        super().__init__()
        self.config_mgr = ConfigManager()
        self.db = DatabaseTracker()                      # SQLite only: Excel is no longer used
        self.keyword_store = KeywordStore(self.db)
        seed_database(self.keyword_store)                # idempotent: only inserts missing keywords
        self.init_ui()
        self.is_running = False

        # Initialize accumulated UI state metrics
        self.total_pages = 0
        self.total_jobs = 0
        self.total_toapply = 0
        # Reading settings retrieves saved profile folder and extra config options
        self.setWindowTitle("Job Search & CV Automation Assistant")

    def init_ui(self):

        self.resize(880, 600)

        main_layout = QVBoxLayout()
        self.tab_widget = QTabWidget()

        # Create individual tab widgets
        self.tab_search = QWidget()
        self.tab_ai_query = QWidget()  # <-- Add this
        self.tab_bkup = QWidget()
        self.tab_db_search = QWidget()
        self.tab_view_job = QWidget()
        self.tab_searches = QWidget()
        self.tab_keywords = QWidget()
        # Build tab layouts
        self._build_search_tab()
        self._build_ai_query_tab()
        self._build_bkup_tab()
        self._build_db_search_tab()
        self._build_view_job_tab()
        self._build_searches_tab()
        self._build_keywords_tab()
        
        self.tab_adzuna = QWidget()
        self._build_adzuna_tab()

        # Add tabs to container
        self.tab_widget.addTab(self.tab_search, "Search Automation")
        self.tab_widget.addTab(self.tab_ai_query, "AI Query")
        self.tab_widget.addTab(self.tab_bkup, "BkUp")
        self.tab_widget.addTab(self.tab_db_search, "DB Search")
        self.tab_widget.addTab(self.tab_view_job, "View Job")
        self.tab_widget.addTab(self.tab_searches, "LnIn Searches")
        self.tab_widget.addTab(self.tab_keywords, "Keywords")
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        self.tab_widget.addTab(self.tab_adzuna, "Adzuna")

        main_layout.addWidget(self.tab_widget)
        self.setLayout(main_layout)

    def _build_search_tab(self):
        # TOP BAR: Search Configuration
        top_group = QGroupBox("Search Configuration")
        top_layout = QHBoxLayout()
        layout = QVBoxLayout(self.tab_search)
        # Left Column: Keywords, Location, Profile Folder
        form_left = QFormLayout()
        self.keywords_input = QLineEdit()
        self.keywords_input.setPlaceholderText(
            "e.g. Enterprise Architect, Solution Architect"
        )
        self.keywords_input.setText("Enterprise Architect")

        self.location_input = QLineEdit()
        self.location_input.setPlaceholderText("e.g. London, United Kingdom")
        self.location_input.setText("UK")

        self.target_input_field = QLineEdit()
        self.target_input_field.setPlaceholderText("e.g. Linkedin Job or Page URL")

        form_left.addRow(QLabel("Keywords:"), self.keywords_input)
        form_left.addRow(QLabel("Location:"), self.location_input)
        form_left.addRow(QLabel("Specific URL:"), self.target_input_field)

        # Right Column: Portal & Contract Specs
        form_right = QFormLayout()
        self.portal_dropdown = QComboBox()
        self.portal_dropdown.addItems([
            "LinkedIn (https://www.linkedin.com/)",
            "Indeed (https://www.indeed.com/)",
            "TotalJobs (https://www.totaljobs.com/)",
            "Gov.uk Jobs (https://www.jobs.service.gov.uk/)",
        ])
        self.portal_dropdown.setCurrentIndex(0)
        
        # Contract Quick Checkbox
        self.contract_checkbox = QCheckBox("Contract")
        self.contract_checkbox.setToolTip("Check to filter strictly by Contract (C). Uncheck for non-contract types.")
        self.contract_checkbox.toggled.connect(self._on_contract_checkbox_toggled)
        
        self.contract_type = MultiSelectComboBox()
        self.contract_type.addItemsWithData([
            ("Contract", "C"),
            ("Full-time", "F"),
            ("Part-time", "P"),
            ("Temporary", "T"),
            ("Other", "O"),
        ])
        
        self.experience_level = MultiSelectComboBox()
        exp_items = [
            ("Mid-Senior level", "4"),
            ("Director", "5"),
            ("Executive", "6"),
        ]
        for text, key in exp_items:
            self.experience_level.addItemWithData(text, key, checked=True)
        
        self.distance_input = QLineEdit()
        self.distance_input.setMaxLength(3)
        self.distance_input.setFixedWidth(40)
        self.distance_input.setPlaceholderText("Dist")
        self.distance_input.setValidator(QIntValidator(0, 999))  # Only allow
        self.distance_input.setText("100")

        filters_layout = QHBoxLayout()       
        filters_layout.setContentsMargins(0, 0, 0, 0) # Keep alignment tight
        filters_layout.addWidget(self.contract_checkbox)
        filters_layout.addWidget(QLabel("Work:"))
        filters_layout.addWidget(self.contract_type)
        filters_layout.addWidget(QLabel("Exp:"))
        filters_layout.addWidget(self.experience_level)
        filters_layout.addWidget(self.distance_input)
        
        self.date_posted_combo = QComboBox()
        self.date_posted_combo.addItem("Past 24h", "r86400")
        self.date_posted_combo.addItem("Past week", "r604800")
        self.date_posted_combo.addItem("Past month", "r2592000")
        self.date_posted_combo.addItem("Any time", "")
        self.date_posted_combo.setCurrentIndex(1)  # Default: Past week

        self.workplace_type = MultiSelectComboBox()
        self.workplace_type.addItemsWithData([
            ("On-site", "1"),
            ("Remote", "2"),
            ("Hybrid", "3"),
        ])
        self.workplace_type.lineEdit().setPlaceholderText("Select Remote/Site...")

        # 3. Sort By (sortBy) Single Selection ComboBox (Default: Most recent -> DD)
        self.sort_by_combo = QComboBox()
        self.sort_by_combo.addItem("Most recent", "DD")
        self.sort_by_combo.addItem("Most relevant", "R")
        self.sort_by_combo.setCurrentIndex(0)  # Default: Most recent

        extra_filters_layout = QHBoxLayout()
        extra_filters_layout.setContentsMargins(0, 0, 0, 0)
        
        extra_filters_layout.addWidget(QLabel("Posted:"))
        extra_filters_layout.addWidget(self.date_posted_combo)
        
        extra_filters_layout.addWidget(QLabel("Remote:"))
        extra_filters_layout.addWidget(self.workplace_type)
        
        extra_filters_layout.addWidget(QLabel("Sort:"))
        extra_filters_layout.addWidget(self.sort_by_combo)

        form_right.addRow(QLabel("Job Portal:"), self.portal_dropdown)
        form_right.addRow(filters_layout)
        form_right.addRow(extra_filters_layout)

        top_layout.addLayout(form_left, stretch=3)
        top_layout.addLayout(form_right, stretch=2)
        top_group.setLayout(top_layout)

        # MIDDLE PANEL: Output Log
        log_group = QGroupBox("Execution Output & Status Log")
        log_layout = QVBoxLayout()
        self.log_output = SearchableLogEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText(
            "Extraction activity, Gemini evaluation status and database events will appear here..."
        )
        log_layout.addWidget(self.log_output)
        log_group.setLayout(log_layout)

        # BOTTOM BAR: Action Controls
        bottom_layout = QHBoxLayout()

        # Left side: Live search statistics label
        self.stats_label = QLabel("TODAY( Pages: 0 | All Jobs: 0 | TOAPPLY: 0)")
        self.stats_label.setStyleSheet("font-weight: bold; color: #333333; margin-right: 10px;")

        # Domain selection box (Left of Start Search button)
        self.domain_label = QLabel("Domain:")
        self.domain_dropdown = QComboBox()
        self._refresh_domains()                          # Keyword, ALL + the domains found in the database

        self.btn_run = QPushButton("Search")
        self.btn_run.setStyleSheet(
            "font-weight: bold; padding: 8px; background-color: #0077B5; color: white;"
        )
        self.btn_run.clicked.connect(self._on_start_clicked)

        # Target TOAPPLY input field right after search button
        self.target_toapply_label = QLabel("Target TOAPPLY:")
        self.target_toapply_input = QLineEdit()
        self.target_toapply_input.setText("30")
        self.target_toapply_input.setFixedWidth(35)
        self.target_toapply_input.setMaxLength(2)
        self.target_toapply_input.setValidator(QIntValidator(1, 99))
        self.target_toapply_input.setToolTip("Target number of TOAPPLY jobs before stopping search")

        self.btn_clear = QPushButton("Clear Log")
        self.btn_clear.clicked.connect(lambda: self.log_output.clear())

        bottom_layout.addWidget(self.stats_label)
        bottom_layout.addStretch()  # Pushes stats to left and buttons to right
        bottom_layout.addWidget(self.domain_label)
        bottom_layout.addWidget(self.domain_dropdown)
        # Add them to bottom_layout before btn_run
        bottom_layout.addWidget(self.btn_run)
        bottom_layout.addWidget(self.target_toapply_label)
        bottom_layout.addWidget(self.target_toapply_input)
        bottom_layout.addWidget(self.btn_clear)

        layout.addWidget(top_group)
        layout.addWidget(log_group)
        layout.addLayout(bottom_layout)

    def _on_start_clicked(self):
        if self.is_running:
            # STOP ACTION
            self.btn_run.setEnabled(False)
            self.btn_run.setText("Stopping Search...")
            self.btn_run.setStyleSheet(
                "font-weight: bold; padding: 8px; background-color: #D9534F; color: white;"
            )
            self.stop_search_requested.emit()
            return
        
        # Visual feedback: disable start button during execution
        self.is_running = True
        self.btn_run.setEnabled(True)
        self.btn_run.setText("Stop Search")
        self.btn_run.setStyleSheet(
            "font-weight: bold; padding: 8px; background-color: #CC0000; color: white;"
        )

        target_val = int(self.target_toapply_input.text().strip() or "30")
        selected_date_posted = self.date_posted_combo.currentData()  
        selected_sort_by = self.sort_by_combo.currentData()

        payload = {
            "keyword": self.keywords_input.text().strip(),
            "location": self.location_input.text().strip(),
            "target_input": self.target_input_field.text().strip(),
            "portal": self.portal_dropdown.currentText(),
            "contract_keys_f_JT": self.contract_type.selected_keys_param(),  
            "experience_keys_f_E": self.experience_level.selected_keys_param(),
            "date_posted_f_TPR": selected_date_posted,
            "workplace_type_f_WT": self.workplace_type.selected_keys_param(),
            "sort_sortBy": selected_sort_by,
            "distance": self.distance_input.text().strip(),

            "max_pages": self.config_mgr.get_constant(self.config_mgr.KEY_NO_PAGES),
            "channel": self.config_mgr.get_constant(self.config_mgr.KEY_CHANNEL),
            "target_today_toapply": target_val,
            "do_scrapping": True,
            "search_domain": self.domain_dropdown.currentText(),
        }
        self.start_search_requested.emit(payload)


    def _refresh_domains(self):
        """Keyword / ALL / every domain currently in search_keywords (includes 'user_insert')."""
        current = self.domain_dropdown.currentText()
        self.domain_dropdown.clear()
        domains = sorted(self.keyword_store.domains(), key=str.lower)
        self.domain_dropdown.addItems(["Keyword", "ALL"] + domains)
        idx = self.domain_dropdown.findText(current)
        self.domain_dropdown.setCurrentIndex(idx if idx >= 0 else 0)

    def _refresh_data_tabs(self):
        self.lnsrch_panel.load_searches()
        self.keywords_panel.load_keywords()
        self.bkup_panel.refresh_metrics()
        self.ai_query_panel.refresh_tables()
        self._refresh_domains()

    def _on_tab_changed(self, index: int):
        """Data tabs show fresh numbers whenever they are opened."""
        w = self.tab_widget.widget(index)
        if w is self.tab_searches:
            self.lnsrch_panel.load_searches()
        elif w is self.tab_keywords:
            self.keywords_panel.load_keywords()
        elif w is self.tab_bkup:
            self.bkup_panel.refresh_metrics()
        elif w is self.tab_ai_query:
            self.ai_query_panel.refresh_tables()

    def on_automation_finished(self):
        self.is_running = False
        self.btn_run.setEnabled(True)
        self.btn_run.setText("Search")
        self.btn_run.setStyleSheet(
            "font-weight: bold; padding: 8px; background-color: #0077B5; color: white;"
        )
        self._refresh_data_tabs()

    def append_log(self, text: str):
        self.log_output.append(text)


    def update_progress(self, update: dict):
        """Updates the status label on the bottom bar when summary_data is emitted[cite: 5]."""
        self.total_pages = update.get("pages", 0)
        self.total_jobs = update.get("total_jobs", 0)
        self.total_toapply = update.get("toapply_jobs", 0)
        
        self.stats_label.setText(
            f"TODAY( Pages: {self.total_pages} | All Jobs: {self.total_jobs} | TOAPPLY: {self.total_toapply})"
        )

        target_limit = int(self.target_toapply_input.text().strip() or "30")
        
        if self.is_running:
            self.append_log(
                f"🎯 TOAPPLY ({self.total_toapply}/{target_limit}) in {self.total_pages} pages & {self.total_jobs} extractions. "
            )
            #self.stop_search_requested.emit()

    def _build_bkup_tab(self):
        """Layout and functionality for the Backup management tab."""
        layout = QVBoxLayout(self.tab_bkup)
        self.bkup_panel = BkupPanel(db_tracker=self.db, parent_log_callback=self.append_log)
        layout.addWidget(self.bkup_panel)

    def _build_searches_tab(self):
        """Layout and functionality for the Searches tab."""
        layout = QVBoxLayout(self.tab_searches)
        self.lnsrch_panel = SearchesPanel(parent_log_callback=self.append_log
        )
        layout.addWidget(self.lnsrch_panel)

    def _build_keywords_tab(self):
        """Keywords with their parameters and statistics."""
        layout = QVBoxLayout(self.tab_keywords)
        self.keywords_panel = KeywordsPanel(db_tracker=self.db, parent_log_callback=self.append_log)
        layout.addWidget(self.keywords_panel)

    def _build_db_search_tab(self):
        """Layout and queries for searching SQLite database tables."""
        layout = QVBoxLayout(self.tab_db_search)
        self.db_search_panel = DBSearchPanel(db_tracker=self.db)
        self.db_search_panel.view_job_requested.connect(self.open_view_job_tab)
        layout.addWidget(self.db_search_panel)

    def _build_adzuna_tab(self):
        layout = QVBoxLayout(self.tab_adzuna)
        self.adzuna_panel = AdzunaPanel(db_tracker=self.db, parent_log_callback=self.append_log)
        layout.addWidget(self.adzuna_panel)

    def _build_view_job_tab(self):
        """Layout for viewing and analyzing individual job details."""
        layout = QVBoxLayout(self.tab_view_job)
        self.job_view_panel = JobViewPanel(db_tracker=self.db)
        layout.addWidget(self.job_view_panel)

    def open_view_job_tab(self, job_id: str):
        """Loads job details in JobViewPanel and switches to the View Job tab."""
        self.job_view_panel.load_job_data(job_id)
        self.tab_widget.setCurrentWidget(self.tab_view_job)

    def _build_ai_query_tab(self):
        layout = QVBoxLayout(self.tab_ai_query)
        self.ai_query_panel = AIQueryPanel(db_tracker=self.db)
        # Connect AI Query panel signal to trigger the worker
        self.ai_query_panel.start_ai_query_signal.connect(self.handle_ai_query_request)
        layout.addWidget(self.ai_query_panel)

    def handle_ai_query_request(self, params: dict):
        """Receives parameters from AIQueryPanel and starts the AutomationWorker."""
        if self.is_running:
            self.append_log("⚠️ Automation already running.")
            return

        params["do_scrapping"] = False  # AI Query panel handles evaluation rounds only

        self.is_running = True
        self.append_log("[*] Initializing AI Query Automation Worker...")
        self.start_search_requested.emit(params)
        
    def _on_contract_checkbox_toggled(self, checked: bool):
        """Toggles contract_type selections based on the Contract Only checkbox."""
        # Block signals temporarily to prevent redundant UI state updates during iteration
        self.contract_type.model.blockSignals(True)
        
        non_contract_keys = {"F", "P", "T", "O"}

        for row in range(self.contract_type.model.rowCount()):
            item = self.contract_type.model.item(row)
            key = item.data(Qt.UserRole)
            
            if checked:
                # Checked: Only "C" (Contract) is selected
                item.setCheckState(Qt.Checked if key == "C" else Qt.Unchecked)
            else:
                # Unchecked: Non-contract keys (F, P, T, O) are selected
                item.setCheckState(Qt.Checked if key in non_contract_keys else Qt.Unchecked)

        self.contract_type.model.blockSignals(False)
        self.contract_type._update_text()