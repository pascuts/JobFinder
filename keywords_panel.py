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

# keywords_panel.py
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
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


class KeywordsPanel(QWidget):
    """Every keyword with its parameters and statistics. Click a header to sort by that column.
    Select a keyword to add/remove interviews (the successful finds) and to see the summary of ALL
    the searches made with it."""

    NUMERIC_DEFAULT_DESC = True      # numbers sort high -> low on the first click, text A -> Z

    def __init__(self, db_tracker: DatabaseTracker = None, parent_log_callback=None):
        super().__init__()
        self.db_tracker = db_tracker if db_tracker else DatabaseTracker()
        self.append_log = parent_log_callback if parent_log_callback else lambda msg: None
        self.config_mgr = ConfigManager()
        self.scheduler = KeywordScheduler(self.db_tracker, SearchLimits.from_config(self.config_mgr))
        self.L = self.scheduler.limits
        self._rows: list[dict] = []

        L = self.L

        def ov(key, default):
            return lambda r: str(r[key]) if r.get(key) else f"({default})"   # (n) = config.txt default

        def rate(rate_key, n_key):
            return lambda r: f"{(r.get(rate_key) or 0):.0%}" if r.get(n_key) else "—"

        # (header, SQL sort key in keyword_store.SORT_COLUMNS, text sort?, cell text)
        self.columns = [
            ("Keyword", "keyword", True, lambda r: r["keyword"]),
            ("Domain", "domain", True, lambda r: r.get("domain") or ""),
            ("Base score", "base_score", False, lambda r: f"{r['base_score']:.2f}"),
            ("Current score", "current_score", False,
             lambda r: f"{r['current_score']:.2f}" if r.get("current_score") is not None else ""),
            ("Boost", "boost", False, lambda r: f"x{(r.get('boost') or 1.0):g}"),
            ("Enabled", "enabled", False, lambda r: "Yes" if r.get("enabled") else "No"),
            ("Max pages", "max_pages", False, ov("max_pages", L.max_pages_per_keyword)),
            ("Max jobs", "max_jobs", False, ov("max_jobs", L.max_reads_per_keyword)),
            ("Max successes", "max_success", False, ov("max_success", L.abs_max_success_per_keyword)),
            ("Max prefilter fails/page", "max_prefilter_fail", False,
             ov("max_prefilter_fail", L.max_prefilter_fail_per_page)),
            ("Interviews", "interviews", False, lambda r: str(r.get("interviews") or 0)),
            ("Searches", "total_searches", False, lambda r: str(r.get("total_searches") or 0)),
            ("Pages", "total_pages", False, lambda r: str(r.get("total_pages") or 0)),
            ("Jobs read", "total_reads", False, lambda r: str(r.get("total_reads") or 0)),
            ("Failed preselection", "total_prefilter_failed", False,
             lambda r: str(r.get("total_prefilter_failed") or 0)),
            ("Sent to Gemini", "total_ai_jobs", False, lambda r: str(r.get("total_ai_jobs") or 0)),
            ("To Apply", "total_successes", False, lambda r: str(r.get("total_successes") or 0)),
            ("Maybe", "total_maybes", False, lambda r: str(r.get("total_maybes") or 0)),
            ("Success rate", "success_rate", False, rate("success_rate", "total_ai_jobs")),
            ("Recent success rate", "recent_success_rate", False,
             lambda r: f"{r['recent_success_rate']:.0%}" if r.get("recent_success_rate") is not None else "—"),
            ("Last searched", "last_searched_at", False, lambda r: r.get("last_searched_display") or "never"),
        ]
        self.COL_INTERVIEWS = [c[0] for c in self.columns].index("Interviews")
        self.COL_SCORE = [c[0] for c in self.columns].index("Current score")

        self.sort_col = 0                 # Keyword A -> Z by default
        self.sort_order = "ASC"
        self._selected_keyword: str | None = None
        self.init_ui()
        self.load_keywords()

    # ------------------------------------------------------------------ #
    def init_ui(self):
        main_layout = QVBoxLayout(self)

        top_bar = QHBoxLayout()
        self.btn_refresh = QPushButton("🔄 Refresh Keywords")
        self.btn_refresh.setStyleSheet(
            "font-weight: bold; padding: 8px 16px; background-color: #0d6efd; color: white;"
        )
        self.btn_refresh.clicked.connect(lambda: self.load_keywords())
        top_bar.addWidget(self.btn_refresh)
        top_bar.addStretch()
        self.lbl_count = QLabel("")
        self.lbl_count.setStyleSheet("font-size: 11px; font-weight: bold;")
        top_bar.addWidget(self.lbl_count)
        main_layout.addLayout(top_bar)

        note = QLabel("Click a column header to sort.  (n) = the config.txt default, used when the keyword "
                      "has no limit of its own.")
        note.setStyleSheet("font-size: 10px; color: #666666;")
        main_layout.addWidget(note)

        splitter = QSplitter(Qt.Vertical)

        # ---- keywords table ------------------------------------------------
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.columns))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionsClickable(True)
        self.table.horizontalHeader().sectionClicked.connect(self.on_header_clicked)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_keyword_selected)
        self._update_header_labels()
        splitter.addWidget(self.table)

        # ---- under the table: [-] interviews [+]  and the summary of all its searches ----
        bottom = QWidget()
        bottom_v = QVBoxLayout(bottom)
        bottom_v.setContentsMargins(0, 0, 0, 0)

        bar = QHBoxLayout()
        self.lbl_keyword = QLabel("Select a keyword")
        self.lbl_keyword.setStyleSheet("font-size: 12px; font-weight: bold; color: #0d6efd;")
        bar.addWidget(self.lbl_keyword)
        bar.addStretch()
        btn_style = "font-weight: bold; padding: 4px 14px; min-width: 28px;"
        self.btn_minus = QPushButton("−")
        self.btn_minus.setStyleSheet(btn_style)
        self.btn_minus.clicked.connect(lambda: self._change_interviews(-1))
        self.lbl_interviews = QLabel("Interviews obtained: -")
        self.lbl_interviews.setStyleSheet("font-size: 12px; font-weight: bold;")
        self.btn_plus = QPushButton("+")
        self.btn_plus.setStyleSheet(btn_style)
        self.btn_plus.clicked.connect(lambda: self._change_interviews(+1))
        for w in (self.btn_minus, self.lbl_interviews, self.btn_plus):
            bar.addWidget(w)
        bottom_v.addLayout(bar)
        self._set_controls(False)

        summary_group = QGroupBox("Summary of all searches for the selected keyword")
        summary_v = QVBoxLayout(summary_group)
        self.lbl_summary = QLabel("Select a keyword to see everything its searches found.")
        self.lbl_summary.setWordWrap(True)
        self.lbl_summary.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        summary_v.addWidget(self.lbl_summary)
        bottom_v.addWidget(summary_group, 1)

        splitter.addWidget(bottom)
        splitter.setSizes([380, 220])
        main_layout.addWidget(splitter)

    # ------------------------------------------------------------------ #
    # Sorting
    # ------------------------------------------------------------------ #
    def _update_header_labels(self):
        labels = []
        for idx, (header, _key, _text, _fn) in enumerate(self.columns):
            arrow = (" ▲" if self.sort_order == "ASC" else " ▼") if idx == self.sort_col else ""
            labels.append(header + arrow)
        self.table.setHorizontalHeaderLabels(labels)

    def on_header_clicked(self, logical_index: int):
        if not (0 <= logical_index < len(self.columns)):
            return
        if logical_index == self.sort_col:
            self.sort_order = "DESC" if self.sort_order == "ASC" else "ASC"
        else:
            self.sort_col = logical_index
            self.sort_order = "ASC" if self.columns[logical_index][2] else "DESC"
        self._update_header_labels()
        self.load_keywords()

    # ------------------------------------------------------------------ #
    # Data
    # ------------------------------------------------------------------ #
    def load_keywords(self, keep: str | None = None):
        """(Re)loads the table, keeps the sort and re-selects the selected keyword."""
        keep = keep or self._selected_keyword
        sort_key = self.columns[self.sort_col][1]
        self._rows = self._fetch_rows(sort_key)

        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for r in self._rows:
            row_idx = self.table.rowCount()
            self.table.insertRow(row_idx)
            for col_idx, (_h, _k, _t, fn) in enumerate(self.columns):
                item = QTableWidgetItem(fn(r))
                if not r.get("enabled"):
                    item.setForeground(QColor("#999999"))
                self.table.setItem(row_idx, col_idx, item)
        self.table.blockSignals(False)

        enabled = sum(1 for r in self._rows if r.get("enabled"))
        self.lbl_count.setText(
            f"{len(self._rows)} keywords ({enabled} enabled) | "
            f"to apply {sum(r.get('total_successes') or 0 for r in self._rows)} | "
            f"interviews {sum(r.get('interviews') or 0 for r in self._rows)}")

        idx = next((i for i, r in enumerate(self._rows) if r["keyword"] == keep), None) if keep else None
        if idx is not None:
            self.table.selectRow(idx)            # fires _on_keyword_selected
        else:
            self._selected_keyword = None
            self._clear_selection()

    def _fetch_rows(self, sort_key):
        return self.scheduler.store.list_keywords(sort_key, self.sort_order)

    def _selected(self) -> dict | None:
        items = self.table.selectedItems()
        if not items:
            return None
        row = items[0].row()
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def _set_controls(self, enabled: bool):
        self.btn_minus.setEnabled(enabled)
        self.btn_plus.setEnabled(enabled)

    def _clear_selection(self):
        self.lbl_keyword.setText("Select a keyword")
        self.lbl_interviews.setText("Interviews obtained: -")
        self.lbl_summary.setText("Select a keyword to see everything its searches found.")
        self._set_controls(False)

    def _on_keyword_selected(self):
        r = self._selected()
        if not r:
            return
        self._selected_keyword = r["keyword"]
        self.lbl_keyword.setText(f"Keyword: {r['keyword']}   ({r.get('domain') or '-'})")
        self.lbl_interviews.setText(f"Interviews obtained: {r.get('interviews') or 0}")
        self._set_controls(True)
        self._show_summary(r["keyword"])

    # ------------------------------------------------------------------ #
    def _change_interviews(self, delta: int):
        r = self._selected()
        if not r:
            return
        kw = r["keyword"]
        total = self.scheduler.adjust_interviews(kw, delta)     # also recomputes the keyword's score
        self.load_keywords(keep=kw)                              # table, sort and summary stay in sync
        self.append_log(f"[*] Interviews for '{kw}': {total}")

    def _show_summary(self, keyword: str):
        s = self.scheduler.store.keyword_summary(keyword)
        self.lbl_summary.setText(self._summary_html(s) if s else "No data.")

    @staticmethod
    def _summary_html(s: dict) -> str:
        kw = s["keyword"]
        if not s["n"]:
            return (f"<b>{kw['keyword']}</b> has not been searched yet. "
                    f"Base score {kw['base_score']:.2f}, interviews {kw.get('interviews') or 0}.")
        rate = f"{s['success_rate']:.0%}" if s["ai_jobs"] else "n/a"
        jobs = s["jobs_by_status"]
        stops = ", ".join(f"{k} ×{v}" for k, v in s["stop_reasons"].items()) or "-"
        first = s["first_score"]
        delta = ""
        if isinstance(first, (int, float)) and isinstance(s["current_score"], (int, float)):
            d = s["current_score"] - first
            colour = "#28a745" if d > 0.004 else "#dc3545" if d < -0.004 else "#333333"
            delta = f" (<span style='color:{colour}'>{d:+.2f}</span>)"
        return (
            f"<b>{s['n']} search{'es' if s['n'] != 1 else ''}</b> between {s['first_search']} and {s['last_search']}"
            f" &nbsp;|&nbsp; <b>interviews {kw.get('interviews') or 0}</b><br>"
            f"<b>Pages</b> {s['pages']} &nbsp;|&nbsp; <b>Jobs read</b> {s['reads']} "
            f"(avg {s['reads_per_search']:.1f}/search) &nbsp;|&nbsp; "
            f"<b>Failed preselection</b> {s['prefilter_failed']} (title gate {s['title_rejected']}) "
            f"&nbsp;|&nbsp; <b>Sent to Gemini</b> {s['ai_jobs']} &nbsp;|&nbsp; "
            f"<b>AI calls</b> {s['ai_calls']}<br>"
            f"<span style='color:#28a745'><b>To apply {s['successes']}</b></span> &nbsp;|&nbsp; "
            f"<span style='color:#fd7e14'><b>Maybe {s['maybes']}</b></span> &nbsp;|&nbsp; "
            f"<span style='color:#dc3545'><b>Do not apply {s['do_not_apply']}</b></span> &nbsp;|&nbsp; "
            f"<b>Success rate {rate}</b> ({s['successes']}/{s['ai_jobs']}, "
            f"avg {s['successes_per_search']:.1f} per search) &nbsp;|&nbsp; "
            f"<b>Searches with no success</b> {s['empty_searches']}<br>"
            f"<b>Score</b> {first if first is None else f'{first:.2f}'} → "
            f"{s['current_score']:.2f}{delta} &nbsp;|&nbsp; range {s['min_score']:.2f} – {s['max_score']:.2f}"
            f" &nbsp;|&nbsp; <b>Pages over the preselection-failure limit</b> {s['bad_pages']}<br>"
            f"<b>Jobs stored by status:</b> "
            + (", ".join(f"{k or '-'} {v}" for k, v in sorted(jobs.items(), key=lambda kv: -kv[1])) or "-")
            + f"<br><b>Searches stopped by:</b> {stops}"
            + (f" &nbsp;|&nbsp; <b>Avg share of the daily target</b> {s['avg_target_pct']:.1f}%"
               if s.get("avg_target_pct") is not None else "")
        )
