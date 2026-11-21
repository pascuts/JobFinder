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

# adzuna_panel.py
import os
import json
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QTabWidget, QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox, QComboBox
)
from db_tracker import DatabaseTracker
from keyword_store import KeywordStore

class AdzunaPanel(QWidget):
    """Panel component for Adzuna cached data inspection. 
    All live API calls are exhausted; data is loaded directly from local JSON cache files.
    """
    def __init__(self, db_tracker: DatabaseTracker = None, parent_log_callback=None):
        super().__init__()
        self.db_tracker = db_tracker if db_tracker else DatabaseTracker()
        self.keyword_store = KeywordStore(self.db_tracker)
        self.log_callback = parent_log_callback
        self.cache_dir = "adzuna_cache"
        os.makedirs(self.cache_dir, exist_ok=True)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # Top Info Bar
        top_bar = QHBoxLayout()
        self.lbl_status = QLabel("Adzuna Data Viewer: Loaded from Local Cache (API Calls Exhausted)")
        self.lbl_status.setStyleSheet("font-weight: bold; color: #0077B5; font-size: 13px;")
        top_bar.addWidget(self.lbl_status)
        top_bar.addStretch()
        main_layout.addLayout(top_bar)

        # Sub-tabs for each Adzuna data category
        self.sub_tab_widget = QTabWidget()

        # 1. Categories Tab
        self.tab_categories = QWidget()
        self._init_categories_tab()
        self.sub_tab_widget.addTab(self.tab_categories, "Categories")

        # 2. Top Companies Tab
        self.tab_companies = QWidget()
        self._init_companies_tab()
        self.sub_tab_widget.addTab(self.tab_companies, "Top Companies")

        # 3. Regional Data & History Tab
        self.tab_regional = QWidget()
        self._init_regional_tab()
        self.sub_tab_widget.addTab(self.tab_regional, "Regional Data & History")

        # 4. Histogram Tab
        self.tab_histogram = QWidget()
        self._init_histogram_tab()
        self.sub_tab_widget.addTab(self.tab_histogram, "Histogram (Bham vs London)")

        main_layout.addWidget(self.sub_tab_widget)

        # Load initial cached data on startup
        self.load_all_cached_data()

    def _log(self, msg: str):
        if self.log_callback:
            self.log_callback(f"[Adzuna Cache] {msg}")

    def _load_cache_json(self, filename: str) -> dict:
        filepath = os.path.join(self.cache_dir, filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                self._log(f"Error loading {filename}: {e}")
        return {}

    def _get_scored_keywords(self) -> list:
        mandatory = ["Scrum Master", "Project Manager", "Java Software Engineer"]
        db_keywords = []
        try:
            raw = self.keyword_store.get_all_keywords()
            sorted_raw = sorted(raw, key=lambda x: float(x[2] if len(x) > 2 and x[2] else 0), reverse=True)
            db_keywords = [k[0] for k in sorted_raw if k[0]]
        except Exception:
            db_keywords = ["Delivery Manager", "Senior Project Manager", "Solution Architect"]

        combined = mandatory.copy()
        for kw in db_keywords:
            if kw not in combined:
                combined.append(kw)
        return combined

    # --- 1. CATEGORIES TAB ---
    def _init_categories_tab(self):
        layout = QVBoxLayout(self.tab_categories)
        self.table_cats = QTableWidget()
        self.table_cats.setColumnCount(2)
        self.table_cats.setHorizontalHeaderLabels(["Category Label", "Tag Slug"])
        self.table_cats.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table_cats)

    def load_categories(self):
        data = self._load_cache_json("categories_cache.json")
        results = data.get("results", [])
        self.table_cats.setRowCount(0)
        for cat in results:
            row = self.table_cats.rowCount()
            self.table_cats.insertRow(row)
            self.table_cats.setItem(row, 0, QTableWidgetItem(cat.get("label", "")))
            self.table_cats.setItem(row, 1, QTableWidgetItem(cat.get("tag", "")))
        self._log(f"Loaded {len(results)} categories from cache.")

    # --- 2. TOP COMPANIES TAB ---
    def _init_companies_tab(self):
        layout = QVBoxLayout(self.tab_companies)
        
        control_layout = QHBoxLayout()
        control_layout.addWidget(QLabel("Cached Keyword Data:"))
        self.combo_comp_keyword = QComboBox()
        self.combo_comp_keyword.addItems(self._get_scored_keywords())
        self.combo_comp_keyword.currentIndexChanged.connect(self.load_top_companies)

        control_layout.addWidget(self.combo_comp_keyword)
        control_layout.addStretch()
        layout.addLayout(control_layout)

        self.table_comps = QTableWidget()
        self.table_comps.setColumnCount(3)
        self.table_comps.setHorizontalHeaderLabels(["Company Name", "Job Count", "Average Salary (£)"])
        self.table_comps.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table_comps)

    def load_top_companies(self):
        data = self._load_cache_json("top_companies_cache.json")
        leaderboard = data.get("leaderboard", [])
        self.table_comps.setRowCount(0)
        for comp in leaderboard:
            row = self.table_comps.rowCount()
            self.table_comps.insertRow(row)
            self.table_comps.setItem(row, 0, QTableWidgetItem(str(comp.get("canonical_name", ""))))
            self.table_comps.setItem(row, 1, QTableWidgetItem(str(comp.get("count", ""))))
            self.table_comps.setItem(row, 2, QTableWidgetItem(str(comp.get("average_salary", ""))))
        self._log("Loaded top companies from cache.")

    # --- 3. REGIONAL DATA & HISTORY TAB ---
    def _init_regional_tab(self):
        layout = QVBoxLayout(self.tab_regional)
        
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("Region:"))
        self.combo_region = QComboBox()
        self.combo_region.addItems(["UK", "London", "West Midlands", "North West", "East Midlands"])
        self.combo_region.currentIndexChanged.connect(self.load_regional_data)
        
        ctrl.addWidget(self.combo_region)
        ctrl.addStretch()
        layout.addLayout(ctrl)

        self.text_regional = QTextEdit()
        self.text_regional.setReadOnly(True)
        layout.addWidget(self.text_regional)

    def load_regional_data(self):
        region = self.combo_region.currentText()
        data = self._load_cache_json("history_cache.json")
        self.text_regional.setPlainText(json.dumps(data, indent=2))
        self._log(f"Loaded regional history cache for {region}.")

    # --- 4. HISTOGRAM TAB ---
    def _init_histogram_tab(self):
        layout = QVBoxLayout(self.tab_histogram)
        
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("Keyword:"))
        self.combo_hist_keyword = QComboBox()
        self.combo_hist_keyword.addItems(self._get_scored_keywords())
        self.combo_hist_keyword.currentIndexChanged.connect(self.load_histogram_comparison)

        ctrl.addWidget(self.combo_hist_keyword)
        ctrl.addStretch()
        layout.addLayout(ctrl)

        hist_layout = QHBoxLayout()
        
        self.text_bham = QTextEdit()
        self.text_bham.setReadOnly(True)
        
        self.text_london = QTextEdit()
        self.text_london.setReadOnly(True)

        bham_box = QGroupBox("Birmingham (West Midlands) Salary Histogram")
        bham_box.setLayout(QVBoxLayout())
        bham_box.layout().addWidget(self.text_bham)

        london_box = QGroupBox("London Salary Histogram")
        london_box.setLayout(QVBoxLayout())
        london_box.layout().addWidget(self.text_london)

        hist_layout.addWidget(bham_box)
        hist_layout.addWidget(london_box)
        layout.addLayout(hist_layout)

    def load_histogram_comparison(self):
        data = self._load_cache_json("histogram_cache.json")
        # Display cached histogram data across panels
        self.text_bham.setPlainText(json.dumps(data, indent=2))
        self.text_london.setPlainText(json.dumps(data, indent=2))
        self._log("Loaded salary histograms from cache.")

    def load_all_cached_data(self):
        """Populates all tabs from the local cache files automatically."""
        self.load_categories()
        self.load_top_companies()
        self.load_regional_data()
        self.load_histogram_comparison()
        self._log("All cached Adzuna datasets successfully loaded into UI.")