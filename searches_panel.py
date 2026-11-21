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

import sys
import re
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QFrame,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from config_manager import ConfigManager
from db_tracker import DatabaseTracker
from keyword_scheduler import KeywordScheduler, SearchLimits


class SearchesPanel(QWidget):
    """One row per keyword search. Selecting a search shows the keyword's details, the job statuses of
    that search (selection box + statistics) and ONLY the jobs that search found, for the chosen status."""

    # statuses always offered in the selection box, in this order (any other status found is added)
    STANDARD_STATUSES = ["toapply", "maybe", "donotapply", "PreFilter"]

    def __init__(self, parent_log_callback=None):
        super().__init__()
        self.db_tracker = DatabaseTracker()
        self.append_log = parent_log_callback if parent_log_callback else lambda msg: None
        self.config_mgr = ConfigManager()
        self.scheduler = KeywordScheduler(self.db_tracker, SearchLimits.from_config(self.config_mgr))
        self._rows: list[dict] = []          # data behind each row of the searches table
        self._current: dict | None = None    # the selected search

        self.search_headers = [
            "Search ID",
            "Date",
            "Keyword",
            "Domain",
            "Score before",
            "Score after",
            "% of daily target",
            "Quota",
            "Pages",
            "Jobs read",
            "Failed preselection",
            "Sent to Gemini",
            "To Apply",
            "Maybe",
            "Success rate",
            "AI calls",
            "Stop reason",
            "KW score now",
            "KW interviews",
            "KW searches",
            "KW success rate",
            "Location",
            "Site",
            "Contract",
            "Target URL",
        ]

        self.job_headers = [
            "Job ID",
            "Job Title",
            "Company",
            "Score",
            "Status",
            "Location",
            "Work Type",
            "Hybrid",
        ]

        self.init_ui()
        self.load_searches()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # 1. TOP TOOLBAR WITH REFRESH BUTTON, AGGREGATE STATS & AI CALLS
        top_bar = QHBoxLayout()
        
        self.btn_refresh = QPushButton("🔄 Refresh Searches")
        self.btn_refresh.setStyleSheet(
            "font-weight: bold; padding: 8px 16px; background-color: #0d6efd; color: white;"
        )
        self.btn_refresh.clicked.connect(self.load_searches)
        top_bar.addWidget(self.btn_refresh)

        # Aggregate search statistics box with date prefix
        today_str = datetime.now().strftime("%d/%m/%Y")
        self.stats_box = QGroupBox(f"[{today_str}] Aggregate Search Statistics (s/d/M/Y/T)")
        self.stats_box.setStyleSheet(
            "QGroupBox { border: 1px solid black; font-weight: bold; font-size: 11px; padding: 4px; }"
        )

        stats_layout = QHBoxLayout(self.stats_box)
        stats_layout.setContentsMargins(8, 4, 8, 4)

        self.lbl_agg_searches = QLabel("Searches: 0/0/0/0/0")
        self.lbl_agg_extracted = QLabel("Extracted: 0/0/0/0/0")
        self.lbl_agg_to_apply = QLabel("ToApply: 0/0/0/0/0")
        self.lbl_agg_maybe = QLabel("Maybe: 0/0/0/0/0")
        self.lbl_agg_dna = QLabel("DoNotApply: 0/0/0/0/0")
        self.lbl_agg_calls = QLabel("AI calls: 0/0/0/0/0")

        for lbl in (
            self.lbl_agg_searches,
            self.lbl_agg_extracted,
            self.lbl_agg_to_apply,
            self.lbl_agg_maybe,
            self.lbl_agg_dna,
            self.lbl_agg_calls,
        ):
            lbl.setStyleSheet("font-size: 11px; font-weight: bold;")
            stats_layout.addWidget(lbl)

        top_bar.addWidget(self.stats_box)
        top_bar.addStretch()

        self.lbl_ai_today = QLabel("Gemini calls today: 0/250")
        self.lbl_ai_today.setStyleSheet("font-size: 11px; font-weight: bold;")
        top_bar.addWidget(self.lbl_ai_today)

        main_layout.addLayout(top_bar)

        # 2. SPLITTER: searches table + selected-search details (top) / jobs of that search (bottom)
        splitter = QSplitter(Qt.Vertical)

        searches_widget = QWidget()
        searches_vbox = QVBoxLayout(searches_widget)
        searches_vbox.setContentsMargins(0, 0, 0, 0)

        searches_vbox.addWidget(QLabel("<b>Execution History</b>"))

        self.table_searches = QTableWidget()
        self.table_searches.setColumnCount(len(self.search_headers))
        self.table_searches.setHorizontalHeaderLabels(self.search_headers)
        
        header = self.table_searches.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)

        if "Keyword" in self.search_headers:
            keyword_index = self.search_headers.index("Keyword")
            header.setSectionResizeMode(keyword_index, QHeaderView.Stretch)
        
        self.table_searches.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_searches.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table_searches.itemSelectionChanged.connect(self._on_search_selected)
        searches_vbox.addWidget(self.table_searches)

        # line 1: details of the keyword that made the selected search
        self.lbl_kw_details = QLabel("Select a search to see its keyword details")
        self.lbl_kw_details.setWordWrap(True)
        self.lbl_kw_details.setStyleSheet("font-size: 11px; font-weight: bold; color: #0d6efd;")
        searches_vbox.addWidget(self.lbl_kw_details)

        # line 2: job status selection box + statistics of the selected search
        status_bar = QHBoxLayout()
        status_bar.addWidget(QLabel("Job status:"))
        self.combo_status = QComboBox()
        self.combo_status.addItem("All", None)
        self.combo_status.setEnabled(False)
        self.combo_status.currentIndexChanged.connect(self._on_status_changed)
        status_bar.addWidget(self.combo_status)
        self.lbl_stats = QLabel("")
        self.lbl_stats.setWordWrap(True)
        self.lbl_stats.setStyleSheet("font-size: 11px; font-weight: bold;")
        status_bar.addWidget(self.lbl_stats, 1)
        searches_vbox.addLayout(status_bar)

        # Green separation line between searches and results
        green_line = QFrame()
        green_line.setFrameShape(QFrame.HLine)
        green_line.setFrameShadow(QFrame.Sunken)
        green_line.setStyleSheet("border: 2px solid #28a745; background-color: #28a745;")
        searches_vbox.addWidget(green_line)

        splitter.addWidget(searches_widget)

        # bottom: only the jobs found by the selected search, for the selected status
        jobs_widget = QWidget()
        jobs_vbox = QVBoxLayout(jobs_widget)
        jobs_vbox.setContentsMargins(0, 0, 0, 0)

        self.lbl_jobs_title = QLabel("<b>Jobs found by the selected search</b>")
        jobs_vbox.addWidget(self.lbl_jobs_title)

        self.table_jobs = QTableWidget()
        self.table_jobs.setColumnCount(len(self.job_headers))
        self.table_jobs.setHorizontalHeaderLabels(self.job_headers)
        self.table_jobs.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table_jobs.setSelectionBehavior(QTableWidget.SelectRows)
        self.table_jobs.setEditTriggers(QTableWidget.NoEditTriggers)
        jobs_vbox.addWidget(self.table_jobs)

        splitter.addWidget(jobs_widget)
        splitter.setSizes([320, 280])

        main_layout.addWidget(splitter)

    # ------------------------------------------------------------------ #
    @staticmethod
    def _fmt_date(s: dict) -> str:
        """dd/MM/yyyy HH:mm"""
        if s.get("run_at_display"):
            return s["run_at_display"]
        raw = s.get("search_date") or ""
        try:
            return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M")
        except ValueError:
            return raw

    @staticmethod
    def _num(v, fmt="{:.1f}") -> str:
        return fmt.format(v) if isinstance(v, (int, float)) else ""

    @staticmethod
    def _pct(rate, n) -> str:
        return f"{(rate or 0):.0%}" if n else "—"

    def _reset_details(self):
        self._current = None
        self.lbl_kw_details.setText("Select a search to see its keyword details")
        self.lbl_stats.setText("")
        self._fill_status_combo(None)
        self.combo_status.setEnabled(False)
        self.lbl_jobs_title.setText("<b>Jobs found by the selected search</b>")

    def load_searches(self):
        """Fetches all search execution records from the SQLite database."""
        self.table_searches.setRowCount(0)
        self.table_jobs.setRowCount(0)
        self._rows = []
        self._reset_details()

        used = self.db_tracker.ai_calls_today()
        self.lbl_ai_today.setText(f"Gemini calls today: {used}/{self.scheduler.limits.max_ai_calls_per_day}")
        self._update_aggregate_labels(selected_search=None)

        searches = self.db_tracker.get_all_searches()
        if not searches:
            return

        for s in searches:
            row_idx = self.table_searches.rowCount()
            self.table_searches.insertRow(row_idx)
            self._rows.append(s)

            row_data = [
                s.get("search_id"),
                self._fmt_date(s),
                s.get("kw_keyword") or s.get("keywords"),
                s.get("kw_domain"),
                self._num(s.get("score_before"), "{:.2f}"),
                self._num(s.get("score_after"), "{:.2f}"),
                self._num(s.get("target_pct"), "{:.1f}%"),
                s.get("quota"),
                s.get("pages"),
                s.get("reads"),
                s.get("prefilter_failed"),
                s.get("ai_jobs"),
                s.get("to_apply_count"),
                s.get("maybe_count"),
                self._pct(s.get("success_rate"), s.get("ai_jobs")),
                s.get("no_ai_calls"),
                s.get("stop_reason"),
                self._num(s.get("kw_score_now"), "{:.2f}"),
                s.get("kw_interviews"),
                s.get("kw_searches"),
                self._pct(s.get("kw_success_rate"), s.get("kw_ai_jobs")),
                s.get("location"),
                s.get("site"),
                s.get("work_type"),
                s.get("target_url"),
            ]

            for col_idx, val in enumerate(row_data):
                item = QTableWidgetItem(str(val) if val is not None else "")
                self.table_searches.setItem(row_idx, col_idx, item)

            # colour the score change: green = went up, red = went down
            b, a = s.get("score_before"), s.get("score_after")
            if isinstance(b, (int, float)) and isinstance(a, (int, float)) and abs(a - b) >= 0.005:
                self.table_searches.item(row_idx, 5).setForeground(
                    QColor("#28a745") if a > b else QColor("#dc3545"))

    # ------------------------------------------------------------------ #
    def _selected_search(self) -> dict | None:
        items = self.table_searches.selectedItems()
        if not items:
            return None
        row = items[0].row()
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def _fill_status_combo(self, stats: dict | None):
        """'All' (default) + one entry per status with its job count for the selected search."""
        self.combo_status.blockSignals(True)
        self.combo_status.clear()
        if stats is None:
            self.combo_status.addItem("All", None)
        else:
            by = stats["by_status"]
            self.combo_status.addItem(f"All ({stats['total']})", None)
            canonical = {s.lower(): s for s in self.STANDARD_STATUSES}
            others = sorted(k for k in by if k and k not in canonical)
            for key in [s.lower() for s in self.STANDARD_STATUSES] + others:
                label = canonical.get(key, key)
                self.combo_status.addItem(f"{label} ({by.get(key, 0)})", key)
        self.combo_status.setCurrentIndex(0)
        self.combo_status.blockSignals(False)

    @staticmethod
    def _clean_keyword_description(desc: str) -> str:
        """Strips out field labels to present clean values"""
        desc = re.sub(r"^Keyword:\s*", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\bdomain\s+", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\bscore base\s+", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\bcurrent\s+", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\bboost\s+", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\benabled\s+(yes|no)\s*\|\s*", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\blast searched\s+[\d/:\s]+", "", desc, flags=re.IGNORECASE)
        desc = re.sub(r"\s*\|\s*\|", " |", desc)
        return desc.strip(" |")

    def _on_search_selected(self):
        """A search row was clicked: keyword details, status box + statistics, and its jobs."""
        s = self._selected_search()
        if not s:
            return
        self._current = s
        
        self._update_aggregate_labels(selected_search=s)

        search_id = s.get("search_id")
        kw = s.get("kw_keyword")

        row = self.scheduler.store.get_keyword(kw) if kw else None
        if row:
            raw_desc = self.scheduler.describe_keyword(row)
            clean_desc = self._clean_keyword_description(raw_desc)
            self.lbl_kw_details.setText(clean_desc)
        else:
            self.lbl_kw_details.setText(f"'{s.get('keywords') or '-'}' "
                                        f"(search made before keyword tracking: no keyword details)")

        stats = self.db_tracker.get_search_stats(search_id)
        self._fill_status_combo(stats)
        self.combo_status.setEnabled(True)
        self.lbl_stats.setText(self._stats_text(s, stats))

        self.load_jobs_for_search(search_id, None)

    def _stats_text(self, s: dict, stats: dict) -> str:
        by = stats["by_status"]
        parts = [f"Found {stats['total']}"]
        if s.get("reads") is not None:
            parts.append(f"read {s.get('reads')}")
            parts.append(f"failed preselection {s.get('prefilter_failed') or 0}")
            parts.append(f"sent to Gemini {s.get('ai_jobs') or 0}")
        parts += [f"✔ toapply {by.get('toapply', 0)}", f"~ maybe {by.get('maybe', 0)}",
                  f"✘ donotapply {by.get('donotapply', 0)}", f"prefilter {by.get('prefilter', 0)}"]
        if s.get("ai_jobs"):
            parts.append(f"success rate {self._pct(s.get('success_rate'), s.get('ai_jobs'))}")
        if stats.get("avg_score") is not None:
            parts.append(f"avg score {stats['avg_score']:.0f}")
        if s.get("no_ai_calls") is not None:
            parts.append(f"AI calls {s.get('no_ai_calls')}")
        if s.get("stop_reason"):
            parts.append(f"stopped: {s.get('stop_reason')}")
        return " | ".join(parts)

    def _on_status_changed(self, _index=None):
        """Another status was picked: reload the jobs of the SAME search for that status."""
        if not self._current:
            return
        self.load_jobs_for_search(self._current.get("search_id"), self.combo_status.currentData())

    def load_jobs_for_search(self, search_id, status: str | None = None):
        """Loads ONLY the jobs found by this search, for the selected status (None = all)."""
        self.table_jobs.setRowCount(0)
        jobs = self.db_tracker.get_jobs_by_search_id(search_id, status)
        s = self._current or {}
        kw = s.get("kw_keyword") or s.get("keywords") or ""
        shown_status = status if status else "All"
        self.lbl_jobs_title.setText(
            f"<b>Jobs found by search #{search_id} ('{kw}' on {self._fmt_date(s)}) — "
            f"status: {shown_status} — {len(jobs)} jobs</b>"
        )

        for j in jobs:
            row_idx = self.table_jobs.rowCount()
            self.table_jobs.insertRow(row_idx)

            score_str = str(j.get("match_score", ""))
            status_str = str(j.get("job_status", ""))

            row_data = [
                j.get("job_id"),
                j.get("title"),
                j.get("company"),
                score_str,
                status_str,
                j.get("location"),
                j.get("work_type"),
                j.get("is_hybrid_remote"),
            ]

            for col_idx, val in enumerate(row_data):
                item = QTableWidgetItem(str(val) if val is not None else "")

                # Color code status
                if status_str.lower() == "toapply":
                    item.setForeground(QColor("#28a745"))  # Green
                elif status_str.lower() == "donotapply":
                    item.setForeground(QColor("#dc3545"))  # Red
                elif status_str.lower() == "maybe":
                    item.setForeground(QColor("#fd7e14"))  # Orange

                self.table_jobs.setItem(row_idx, col_idx, item)

    def _update_aggregate_labels(self, selected_search: dict | None = None):
        """Renders s/d/M/Y/T metrics inside the aggregate stats box and updates header date."""
        m = self.db_tracker.get_aggregate_metrics()
        
        # Determine the header date prefix: search date if selected, otherwise today's date
        if selected_search:
            date_prefix = self._fmt_date(selected_search).split()[0]  # Extracts dd/MM/yyyy
        else:
            date_prefix = datetime.now().strftime("%d/%m/%Y")

        self.stats_box.setTitle(f"[{date_prefix}] Aggregate Search Statistics (s/d/M/Y/T)")

        s_search = 1 if selected_search else 0
        s_extracted = (selected_search.get("total_found") or 0) if selected_search else 0
        s_to_apply = (selected_search.get("to_apply_count") or 0) if selected_search else 0
        s_maybe = (selected_search.get("maybe_count") or 0) if selected_search else 0
        s_dna = (selected_search.get("do_not_apply_count") or 0) if selected_search else 0
        s_calls = (selected_search.get("no_ai_calls") or 0) if selected_search else 0

        self.lbl_agg_searches.setText(
            f"Searches: {s_search}/{m.get('searches_d', 0)}/{m.get('searches_M', 0)}/{m.get('searches_Y', 0)}/{m.get('searches_T', 0)}"
        )
        self.lbl_agg_extracted.setText(
            f"Extracted: {s_extracted}/{m.get('extracted_d', 0)}/{m.get('extracted_M', 0)}/{m.get('extracted_Y', 0)}/{m.get('extracted_T', 0)}"
        )
        self.lbl_agg_to_apply.setText(
            f"ToApply: {s_to_apply}/{m.get('to_apply_d', 0)}/{m.get('to_apply_M', 0)}/{m.get('to_apply_Y', 0)}/{m.get('to_apply_T', 0)}"
        )
        self.lbl_agg_maybe.setText(
            f"Maybe: {s_maybe}/{m.get('maybe_d', 0)}/{m.get('maybe_M', 0)}/{m.get('maybe_Y', 0)}/{m.get('maybe_T', 0)}"
        )
        self.lbl_agg_dna.setText(
            f"DoNotApply: {s_dna}/{m.get('dna_d', 0)}/{m.get('dna_M', 0)}/{m.get('dna_Y', 0)}/{m.get('dna_T', 0)}"
        )
        self.lbl_agg_calls.setText(
            f"AI calls: {s_calls}/{m.get('calls_d', 0)}/{m.get('calls_M', 0)}/{m.get('calls_Y', 0)}/{m.get('calls_T', 0)}"
        )