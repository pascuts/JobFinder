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

# bkup_panel.py  -  database backup + score metrics (Excel is no longer used)
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from db_tracker import DatabaseTracker


class BkupPanel(QWidget):
    """Backs up the SQLite database and shows how many jobs there are per status, with min/max score."""

    CATEGORIES = [                       # label -> statuses (lower case) counted in it
        ("Submitted", ("submitted", "applied")),
        ("ToApply", ("toapply",)),
        ("Maybe", ("maybe",)),
        ("DoNotApply", ("donotapply",)),
        ("PreFilter", ("prefilter",)),
    ]

    def __init__(self, db_tracker: DatabaseTracker = None, parent_log_callback=None):
        super().__init__()
        self.db_tracker = db_tracker if db_tracker else DatabaseTracker()
        self.append_log = parent_log_callback if parent_log_callback else lambda msg: None
        self.headers = [
            "Job ID", "Job Title", "Created At", "Status", "Match Score", "Company",
            "Point of Contact", "Location", "Salary", "Hybrid Y/N",
        ]
        self.init_ui()
        self.refresh_metrics()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        btn_layout = QHBoxLayout()
        self.btn_backup = QPushButton("Backup Database")
        self.btn_backup.setStyleSheet(
            "font-weight: bold; padding: 10px; background-color: #28a745; color: white;"
        )
        self.btn_backup.clicked.connect(self._on_backup_clicked)

        self.btn_refresh = QPushButton("Refresh Metrics")
        self.btn_refresh.setStyleSheet(
            "font-weight: bold; padding: 10px; background-color: #6f42c1; color: white;"
        )
        self.btn_refresh.clicked.connect(self.refresh_metrics)

        btn_layout.addWidget(self.btn_backup)
        btn_layout.addWidget(self.btn_refresh)
        main_layout.addLayout(btn_layout)

        summary_group = QGroupBox("Jobs in the database by status (min / max score)")
        summary_layout = QHBoxLayout()
        self.lbl_categories = {}
        for name, _ in self.CATEGORIES + [("Miscellaneous", ())]:
            lbl = QLabel(f"{name}: 0 (min: - | max: -)")
            lbl.setStyleSheet("font-size: 11px; font-weight: bold;")
            summary_layout.addWidget(lbl)
            self.lbl_categories[name] = lbl
        self.lbl_score_1000 = QLabel("Score -1000: 0")
        self.lbl_score_1000.setStyleSheet("font-size: 11px; font-weight: bold;")
        summary_layout.addWidget(self.lbl_score_1000)
        summary_group.setLayout(summary_layout)
        main_layout.addWidget(summary_group)

        main_layout.addWidget(QLabel("<b>Last 10 jobs stored</b>"))
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.headers))
        self.table.setHorizontalHeaderLabels(self.headers)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        main_layout.addWidget(self.table)

    # ------------------------------------------------------------------ #
    def refresh_metrics(self):
        agg = {name: {"n": 0, "lo": None, "hi": None} for name, _ in self.CATEGORIES}
        agg["Miscellaneous"] = {"n": 0, "lo": None, "hi": None}
        errors = 0
        for m in self.db_tracker.get_status_metrics():
            cat = next((n for n, sts in self.CATEGORIES if m["job_status"] in sts), "Miscellaneous")
            a = agg[cat]
            a["n"] += m["n"]
            errors += m["errors"] or 0
            for key, fn in (("lo", min), ("hi", max)):
                if m[key] is not None:
                    a[key] = m[key] if a[key] is None else fn(a[key], m[key])
        for name, a in agg.items():
            lo = "-" if a["lo"] is None else a["lo"]
            hi = "-" if a["hi"] is None else a["hi"]
            self.lbl_categories[name].setText(f"{name}: {a['n']} (min: {lo} | max: {hi})")
        self.lbl_score_1000.setText(f"Score -1000: {errors}")

        self.table.setRowCount(0)
        for j in self.db_tracker.get_jobs_by_status_and_date(criteria={}, limit=10):
            row_idx = self.table.rowCount()
            self.table.insertRow(row_idx)
            values = [j["job_id"], j["title"], j["created_at"], j["job_status"], j["match_score"], j["company"],
                      j["contact"], j["location"], j["salary_range"], j["is_hybrid_remote"]]
            for col_idx, v in enumerate(values):
                self.table.setItem(row_idx, col_idx, QTableWidgetItem("" if v is None else str(v)))

    def _on_backup_clicked(self):
        self.append_log("[*] Backing up the database...")
        try:
            path = self.db_tracker.backup_database()
            size_mb = os.path.getsize(path) / (1024 * 1024)
            self.append_log(f"✅ Database backed up: {path} ({size_mb:.1f} MB)")
        except Exception as e:
            self.append_log(f"❌ Backup failed: {e}")
        self.refresh_metrics()
