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

# db_search_panel.py
import math
import sqlite3
from db_tracker import DatabaseTracker
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class DBSearchPanel(QWidget):
    view_job_requested = Signal(str)

    def __init__(self, db_tracker: DatabaseTracker = None):
        super().__init__()
        self.db_tracker = db_tracker if db_tracker else DatabaseTracker()
        self.current_results = []
        self.page_size = 50
        self.current_page = 1
        self.total_pages = 1

        # Column base headers mapping
        self.base_headers = [
            "Job ID",
            "PDF",
            "View",
            "Company",
            "Job Title",
            "Location",
            "Salary",
            "Score",
            "Status",
            "Created At",
        ]

        # Column index to SQL column mapping for sortable headers
        self.column_sql_map = {
            0: "j.job_id",
            3: "j.company",
            7: "j.match_score",
            8: "j.job_status",
            9: "j.created_at",
        }

        # Header click sort tracking: (col_idx, "ASC" | "DESC")
        self.active_sort_col = 0
        self.active_sort_order = "DESC"

        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # 1. SEARCH CRITERIA PANEL
        search_group = QGroupBox("Database Search Criteria")
        search_layout = QHBoxLayout()

        # Left Column: Job ID, Company, Job Title, Description
        left_form = QFormLayout()
        self.input_job_id = QLineEdit()
        self.input_company = QLineEdit()
        self.input_title = QLineEdit()
        self.input_description = QLineEdit()

        left_form.addRow(QLabel("Job ID:"), self.input_job_id)
        left_form.addRow(QLabel("Company:"), self.input_company)
        left_form.addRow(QLabel("Job Title:"), self.input_title)
        left_form.addRow(QLabel("Description:"), self.input_description)

        # Right Column: Score >=, Salary >=, Status, Days Back (0..356)
        right_form = QFormLayout()
        self.input_score = QLineEdit()
        self.input_score.setPlaceholderText("e.g. 70")

        self.input_salary = QLineEdit()
        self.input_salary.setPlaceholderText("e.g. 50000")

        self.combo_status = QComboBox()
        self.combo_status.addItems(self.db_tracker.populate_job_status())

        # Added Days Back SpinBox (Range: 0 to 356, Default: 0)
        self.input_days_back = QSpinBox()
        self.input_days_back.setRange(0, 356)
        self.input_days_back.setValue(0)
        self.input_days_back.setToolTip("0 = Extracted Today. Filter extracted within last N days.")

        right_form.addRow(QLabel("Score >=:"), self.input_score)
        right_form.addRow(QLabel("Salary >=:"), self.input_salary)
        right_form.addRow(QLabel("Status:"), self.combo_status)
        right_form.addRow(QLabel("Days Back (0=Today):"), self.input_days_back)

        search_layout.addLayout(left_form, stretch=1)
        search_layout.addLayout(right_form, stretch=1)

        # Action Buttons Column
        btn_layout = QVBoxLayout()
        self.btn_search = QPushButton("Search DB")
        self.btn_search.setStyleSheet(
            "font-weight: bold; padding: 10px; background-color: #0077B5; color: white;"
        )
        self.btn_search.clicked.connect(self.execute_search)

        self.btn_reset = QPushButton("Reset Filters")
        self.btn_reset.clicked.connect(self.reset_filters)

        btn_layout.addWidget(self.btn_search)
        btn_layout.addWidget(self.btn_reset)

        btn_layout.addStretch()

        search_layout.addLayout(btn_layout)
        search_group.setLayout(search_layout)
        main_layout.addWidget(search_group)

        # 2. RESULTS TABLE
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.base_headers))
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )

        # Connect header click signal for dynamic sorting
        header = self.table.horizontalHeader()
        header.setSectionsClickable(True)
        header.sectionClicked.connect(self.on_header_clicked)

        self.update_header_labels()
        main_layout.addWidget(self.table)

        # 3. PAGINATION CONTROLS BAR
        pagination_layout = QHBoxLayout()
        self.btn_prev = QPushButton("< Previous")
        self.btn_prev.clicked.connect(self.prev_page)

        self.lbl_page_info = QLabel("Page 0 of 0 (0 Records)")
        self.lbl_page_info.setAlignment(Qt.AlignCenter)

        self.btn_next = QPushButton("Next >")
        self.btn_next.clicked.connect(self.next_page)

        pagination_layout.addWidget(self.btn_prev)
        pagination_layout.addWidget(self.lbl_page_info)
        pagination_layout.addWidget(self.btn_next)
        main_layout.addLayout(pagination_layout)

    def update_header_labels(self):
        """Updates header text labels with ▲ / ▼ direction arrows for active column."""
        headers = []
        for idx, text in enumerate(self.base_headers):
            if idx == self.active_sort_col and idx in self.column_sql_map:
                arrow = " ▲" if self.active_sort_order == "ASC" else " ▼"
                headers.append(f"{text}{arrow}")
            else:
                headers.append(text)
        self.table.setHorizontalHeaderLabels(headers)

    def on_header_clicked(self, logical_index: int):
        """Toggles sort order or changes active sort column upon header click."""
        if logical_index not in self.column_sql_map:
            return  # Column not sortable

        if self.active_sort_col == logical_index:
            # Toggle direction on same header click
            self.active_sort_order = (
                "DESC" if self.active_sort_order == "ASC" else "ASC"
            )
        else:
            # Change active column and default to DESC
            self.active_sort_col = logical_index
            self.active_sort_order = "DESC"

        self.update_header_labels()
        self.execute_search()

    def execute_search(self):  
        criteria = {}

        if self.input_job_id.text().strip():
            criteria["job_id"] = self.input_job_id.text().strip()

        if self.input_company.text().strip():
            criteria["company"] = self.input_company.text().strip()

        if self.input_title.text().strip():
            criteria["title"] = self.input_title.text().strip()

        if self.input_description.text().strip():
            criteria["description"] = self.input_description.text().strip()

        if self.combo_status.currentText() != "All":
            criteria["job_status"] = self.combo_status.currentText()

        if self.input_score.text().strip():
            try:
                criteria["score"] = int(self.input_score.text().strip())
            except ValueError:
                pass

        if self.input_salary.text().strip():
            criteria["salary"] = self.input_salary.text().strip()

        # Pass days_back spinbox value to criteria for created_at filtering
        criteria["days_back"] = self.input_days_back.value()

        # Add custom sorting parameter based on active header selection
        sql_col = self.column_sql_map.get(self.active_sort_col, "j.created_at")
        criteria["order by"] = sql_col
        criteria["direction"] = self.active_sort_order

        # Execute search using the unified method
        self.current_results = self.db_tracker.get_jobs_by_status_and_date(criteria)

        self.current_page = 1
        self.render_table_page()

    def render_table_page(self):
        """Renders 50 records per page into the table widget."""
        total_records = len(self.current_results)
        self.total_pages = max(1, math.ceil(total_records / self.page_size))

        start_idx = (self.current_page - 1) * self.page_size
        end_idx = start_idx + self.page_size
        page_records = self.current_results[start_idx:end_idx]

        self.table.setRowCount(0)
        for row_data in page_records:
            row_idx = self.table.rowCount()
            self.table.insertRow(row_idx)

            job_id = str(row_data.get("job_id", ""))

            col_mapping = {
                0: str(row_data.get("job_id") or ""),         # Job ID
                3: str(row_data.get("company") or ""),    # Company
                4: str(row_data.get("title") or ""),           # Job Title
                5: str(row_data.get("location") or ""),        # Location
                6: str(row_data.get("salary_range") or ""),    # Salary
                7: str(row_data.get("match_score") or ""),     # Score
                8: str(row_data.get("job_status") or ""),      # Status
                9: str(row_data.get("created_at") or ""),  # Date Extracted
            }

            for col_idx, cell_value in col_mapping.items():
                item = QTableWidgetItem(cell_value)
                item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                self.table.setItem(row_idx, col_idx, item)

            # Col 1: XML / PDF Export Button
            btn_pdf = QPushButton("XML")
            btn_pdf.setStyleSheet("padding: 2px; font-size: 11px;")
            self.table.setCellWidget(row_idx, 1, btn_pdf)

            # Col 2: View Job Button
            btn_view = QPushButton("View")
            btn_view.setStyleSheet("padding: 2px; font-size: 11px;")
            btn_view.clicked.connect(
                lambda _, j_id=job_id: self.view_job_requested.emit(j_id)
            )
            self.table.setCellWidget(row_idx, 2, btn_view)

        self.lbl_page_info.setText(
            f"Page {self.current_page} of {self.total_pages} ({total_records} Records)"
        )
        self.btn_prev.setEnabled(self.current_page > 1)
        self.btn_next.setEnabled(self.current_page < self.total_pages)

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.render_table_page()

    def next_page(self):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.render_table_page()

    def reset_filters(self):
        self.input_job_id.clear()
        self.input_company.clear()
        self.input_title.clear()
        self.input_description.clear()
        self.input_score.clear()
        self.input_salary.clear()
        self.combo_status.setCurrentIndex(0)
        self.input_days_back.setValue(0)
        self.combo_status.clear()
        self.combo_status.addItems(self.db_tracker.populate_job_status())
        self.active_sort_col = 0
        self.active_sort_order = "DESC"
        self.update_header_labels()
        self.execute_search()
