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

# job_view_panel.py
from datetime import datetime
import os
import re
import xml.dom.minidom as minidom
import xml.etree.ElementTree as ET

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextDocument, QFont
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from config_manager import ConfigManager

class JobViewPanel(QWidget):
    """Panel component embedded in the 'View Job' tab.
    Displays detailed job meta-information, XML scoring/CV outputs,
    and provides clipboard copying capabilities.
    """

    def __init__(self, db_tracker=None):
        super().__init__()
        self.config_mgr = ConfigManager()
        self.db_tracker = db_tracker
        self.current_job_id = None
        self.cover_letter = ""
        self.evaluation_xml = ""
        self.cv_xml = ""
        self.job_description = ""
        self.job_url = ""
        self.active_tab_type = "score"
        self.init_ui()

    def init_ui(self):
        # Main layout for the entire panel
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # 1. Fixed Header Container (Title, Meta, URL, Action Bar) so they never scroll away or expand out
        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)

        # Line 1: Job Title
        self.lbl_title = QLabel("No Job Selected")
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #0077B5;")
        self.lbl_title.setWordWrap(True)
        header_layout.addWidget(self.lbl_title)

        # Line 2: Company Name, Score, Salary, Location
        self.lbl_meta = QLabel("Company: - | Score: - | Salary: - | Location: -")
        self.lbl_meta.setStyleSheet("font-size: 13px; font-weight: 500; color: #333333;")
        self.lbl_meta.setWordWrap(True)
        header_layout.addWidget(self.lbl_meta)

        self.lbl_url = QLabel("URL: -")
        self.lbl_url.setStyleSheet("font-size: 12px; color: #0d6efd;")
        self.lbl_url.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        self.lbl_url.setOpenExternalLinks(True)
        self.lbl_url.setWordWrap(True)
        header_layout.addWidget(self.lbl_url)

        # Action Bar: "View:" label + 3 buttons (Score, CV, Copy) + Status Change combo box + Change button
        action_layout = QHBoxLayout()
        lbl_view = QLabel("View:")
        lbl_view.setStyleSheet("font-weight: bold;")

        self.btn_desc = QPushButton("Description")
        self.btn_desc.clicked.connect(self.show_job_description)

        self.btn_score = QPushButton("Score")
        self.btn_score.clicked.connect(self.show_score_xml)

        self.btn_cv = QPushButton("CV Changes")
        self.btn_cv.clicked.connect(self.show_cv_xml)

        self.btn_generate_cv = QPushButton("Generate CV")
        self.btn_generate_cv.clicked.connect(self.generate_and_show_tailored_cv)

        self.btn_cover_letter = QPushButton("Cover Letter")
        self.btn_cover_letter.clicked.connect(self.show_cover_letter)

        self.btn_copy = QPushButton("Copy")
        self.btn_copy.clicked.connect(self.copy_content_to_clipboard)

        self.btn_to_pdf = QPushButton("To Pdf")
        self.btn_to_pdf.clicked.connect(self.export_content_to_pdf)

        action_layout.addWidget(lbl_view)
        action_layout.addWidget(self.btn_desc)
        action_layout.addWidget(self.btn_score)
        action_layout.addWidget(self.btn_cv)
        action_layout.addWidget(self.btn_generate_cv)
        action_layout.addWidget(self.btn_cover_letter)
        action_layout.addWidget(self.btn_copy)
        action_layout.addWidget(self.btn_to_pdf)
        action_layout.addStretch()

        # Status Change selection box and Change button
        self.lbl_status_change = QLabel("Status Change:")
        self.lbl_status_change.setStyleSheet("font-weight: bold;")
        self.combo_status_change = QComboBox()
        
        self.btn_change_status = QPushButton("Change")
        self.btn_change_status.clicked.connect(self.apply_status_change)

        action_layout.addWidget(self.lbl_status_change)
        action_layout.addWidget(self.combo_status_change)
        action_layout.addWidget(self.btn_change_status)

        header_layout.addLayout(action_layout)
        main_layout.addWidget(header_widget)

        # 2. Large text box filling all remaining vertical space natively with its own internal scroll bars
        self.text_display = QTextEdit()
        self.text_display.setStyleSheet(
            "font-size: 14px; background-color: #ffffd0; color: #000080; font-weight: 500;"
        )
        main_layout.addWidget(self.text_display, stretch=1)

    def load_job_data(self, job_id: str):
        """Fetches full job meta-information and evaluation XML payloads from SQLite database using getJobRecord."""
        self.current_job_id = str(job_id).strip()
        if not self.db_tracker:
            return

        record = self.db_tracker.getJobRecord(self.current_job_id)

        if record:
            title = record.get("Job Title", "")
            company = record.get("Company", "Unknown Company")
            score = record.get("Match Score", -1000)
            salary = str(record.get("Salary", "N/A"))[:20]
            location = record.get("Location", "N/A")
            description = record.get("Job Description", "")
            job_url = record.get("job_url", "")
            eval_xml = record.get("EvaluationXML", "")
            cv_xml = record.get("CV4Job", "")
            cover_letter = record.get("CoverLetter", "")
            status_rec = record.get("job_status", "")
            
            # Line 1: Job Title
            self.lbl_title.setText(f"📌 {title}")
            
            # Line 2: Company Name, Score, Salary, Location
            self.lbl_meta.setText(
                f"🏢 Company: {company}  |  ⭐ Score: {score}%  |  💰 Salary: {salary}  |  📍 Location: {location}"
            )
            self.job_url = job_url
            if job_url:
                self.lbl_url.setText(f'URL: <a href="{job_url}">{job_url}</a>')
            else:
                self.lbl_url.setText("URL: N/A")

            self.evaluation_xml = eval_xml or "No evaluation XML response recorded."
            self.cv_xml = cv_xml or "No CV XML response recorded."
            self.job_description = self._format_description(description) 
            self.cover_letter = cover_letter or "empty"

            self.combo_status_change.clear()
            self.combo_status_change.addItems(self.db_tracker.populate_job_status())
            
            # Set combo box to current job status by default if present (case-insensitive search)
            if status_rec:
                index = -1
                for i in range(self.combo_status_change.count()):
                    if self.combo_status_change.itemText(i).strip().lower() == status_rec.strip().lower():
                        index = i
                        break
                if index >= 0:
                    self.combo_status_change.blockSignals(True)
                    self.combo_status_change.setCurrentIndex(index)
                    self.combo_status_change.blockSignals(False)
            # Initially populate text box with evaluation_xml_response content
            self.show_score_xml()
        else:
            self.lbl_title.setText("Job Record Not Found")
            self.lbl_meta.setText("Company: - | Score: - | Salary: - | Location: -")
            self.text_display.clear()

    @staticmethod
    def _format_description(raw_desc: str) -> str:
        """Formats unformatted job description blocks:
        - Breaks sentences/points onto new lines (. ! ? : or | boundaries)
        - Capitalizes the first letter of each line/sentence
        - Prepends 4 spaces (tab) to the beginning of each line
        """
        if not raw_desc:
            return ""
    
        # Split by typical sentence boundaries or delimiters
        parts = re.split(r'(?<=[.!?:]|\n|\|)\s+', raw_desc)
    
        formatted_lines = []
        for part in parts:
            clean_part = part.strip()
            if clean_part:
                # Capitalize the first letter of the line/sentence
                capitalized_part = clean_part[0].upper() + clean_part[1:]
                formatted_lines.append(f"    {capitalized_part}")
            
        return "\n".join(formatted_lines)

    def show_score_xml(self):
        """Displays evaluation_xml_response in the main text box."""
        self.active_tab_type = "score"
        self.text_display.setPlainText(self.evaluation_xml)

    def show_cv_xml(self):
        """Displays cv_xml_response in the main text box."""
        self.active_tab_type = "cv_changes"
        self.text_display.setPlainText(self.cv_xml)

    def show_job_description(self):
        """Displays the job description text in the main text box."""
        self.active_tab_type = "description"
        self.text_display.setPlainText(self.job_description)

    def copy_content_to_clipboard(self):
        """Copies current text box content to system clipboard."""
        content = self.text_display.toPlainText()
        if content:
            if content == self.job_description and self.job_url:
                content = f"{self.job_url} | {content}"
            QApplication.clipboard().setText(content)
            QMessageBox.information(self, "Clipboard", "Content copied to clipboard!")

    @staticmethod
    def _append_xml_or_text(parent_node: ET.Element, xml_string: str) -> None:
        """Parses raw XML text into child elements, or falls back to plain text."""
        try:
            parsed_element = ET.fromstring(xml_string.strip())
            parent_node.append(parsed_element)
        except Exception:
            parent_node.text = xml_string

    def apply_status_change(self):
        """Updates the job status recommendation in the database when the 'Change' button is clicked."""
        if not self.current_job_id or not self.db_tracker:
            QMessageBox.warning(self, "Warning", "No active job selected to update status.")
            return

        

        # 3. Build fields_to_update dynamically based on what tab/view is active and whether it changed
        fields_to_update = set()
        if self.active_tab_type == "cover_letter":
            self.cover_letter = self.text_display.toHtml()
            fields_to_update.add(("cover_letter", self.cover_letter))
        if self.active_tab_type == "cv_changes":
            self.cv_xml = self.text_display.toPlainText()
            fields_to_update.add(("cv_xml_response", self.cv_xml))

        if len(fields_to_update)>0:
            self.db_tracker.update_job_evaluation_fields(self.current_job_id, fields_to_update)

        new_status = self.combo_status_change.currentText()
        if not new_status:
            return
        
        try:
            self.db_tracker.update_status(self.current_job_id, new_status)
            QMessageBox.information(self, "Success", f"Job status updated to '{new_status}'.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update status: {e}")

    def export_content_to_pdf(self):
        """Exports current text box content to a PDF file formatted in Arial, 14pt, with visible text and preserved HTML styling."""
        html_content = self.text_display.toHtml()
        if not html_content.strip():
            QMessageBox.warning(self, "Warning", "No content available to export to PDF.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export to PDF", "", "PDF Files (*.pdf);;All Files (*)"
        )
        if not file_path:
            return

        if not file_path.lower().endswith(".pdf"):
            file_path += ".pdf"

        try:
            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(file_path)

            doc = QTextDocument()
        
            # Enforce explicit Arial 14pt styling and dark text color via CSS wrapper 
            # to prevent invisible text or overridden font sizes in PDF print engine
            styled_html = f"""
                <html>
                    <head>
                        <style>
                            body {{
                                font-family: 'Arial';
                                font-size: 14pt;
                                color: #000000;
                            }}
                        </style>
                    </head>
                    <body>
                        {html_content}
                    </body>
                </html>
            """
        
            doc.setHtml(styled_html)
        
            # Set default font fallback as well
            font = QFont("Arial", 14)
            doc.setDefaultFont(font)
        
            doc.print_(printer)
            QMessageBox.information(self, "Success", f"Successfully exported to PDF:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export PDF: {e}")

    def show_cover_letter(self):
        """Displays cover_letter in the main text box, supporting HTML rich text formatting."""
        self.active_tab_type = "cover_letter"
        # Check if the stored cover letter contains HTML tags; if so, load as HTML, otherwise plain text
        if "<" in self.cover_letter and ">" in self.cover_letter:
            self.text_display.setHtml(self.cover_letter)
        else:
            self.text_display.setPlainText(self.cover_letter)

    def generate_and_show_tailored_cv(self):
        """Generates the tailored CV by loading CVTemplate_x.xml, merging common fields from CommonCVTemplate.xml,
        and applying change sets specified in the cv_xml_response payload.
        """
        self.active_tab_type = "generated_cv"
        try:
            if not self.cv_xml or "<JobResult>" not in self.cv_xml:
                self.text_display.setPlainText("No valid JobResult changes payload found to generate tailored CV.")
                return

            # 1. Parse JobResult/changes payload
            job_result_root = ET.fromstring(self.cv_xml.strip())
            cv_template_no = job_result_root.findtext("cvTemplateNo", "1")
            
            # 2. Determine paths based on profile directory structure
            profile_dir = self.config_mgr.get_constant(ConfigManager.KEY_MY_PROF_PROFILE)
            template_path = os.path.join(profile_dir, "cvtmpl", f"CVTemplate_{cv_template_no}.xml")
            common_template_path = os.path.join(profile_dir, "scoring", "CommonCVTemplate.xml")

            if not os.path.exists(template_path):
                self.text_display.setPlainText(f"Error: Template file not found at {template_path}")
                return

            # 3. Parse specific CVTemplate and CommonCVTemplate
            template_tree = ET.parse(template_path)
            template_root = template_tree.getroot()
            
            common_root = None
            if os.path.exists(common_template_path):
                common_tree = ET.parse(common_template_path)
                common_root = common_tree.getroot()

            # 4. Merge common template sections where template points to CommonCVTemplate.xml
            # Handles top-level tags as well as nested elements like individual <Job> nodes
            if common_root is not None:
                # Check top-level elements
                for child in list(template_root):
                    if child.text and "CommonCVTemplate.xml" in child.text.strip():
                        tag_name = child.tag
                        common_match = common_root.find(tag_name)
                        if common_match is not None:
                            template_root.remove(child)
                            template_root.append(common_match)

                # Check inside containers like EmploymentHistory for <Job> elements pointing to CommonCVTemplate.xml
                for parent_elem in template_root.iter():
                    for child in list(parent_elem):
                        if child.text and "CommonCVTemplate.xml" in child.text.strip():
                            employer_attr = child.get("employer")
                            if employer_attr:
                                # Find matching job in CommonCVTemplate by employer attribute
                                common_job = common_root.find(f".//Job[@employer='{employer_attr}']")
                                if common_job is not None:
                                    parent_elem.remove(child)
                                    parent_elem.append(common_job)

            # 5. Apply changes from job result payload
            for change in job_result_root.findall(".//change"):
                section_name = change.findtext("changeSectionName")
                replaces = change.findtext("replaces")
                change_content = change.findtext("changeContent")
                
                if section_name == "Profile Summary":
                    profile_elem = template_root.find("ProfileSummary")
                    if profile_elem is not None and profile_elem.text and replaces in profile_elem.text:
                        profile_elem.text = profile_elem.text.replace(replaces, change_content)
                elif section_name == "EmploymentHistory":
                    for detail_elem in template_root.findall(".//Detail"):
                        if detail_elem.text and replaces and replaces in detail_elem.text:
                            detail_elem.text = change_content
                elif section_name == "TechnicalSkills":
                    skills_elem = template_root.find("TechnicalSkills")
                    if skills_elem is not None:
                        # Split changeContent by commas to handle multiple skills cleanly
                        new_skills = [s.strip() for s in change_content.split(",") if s.strip()]
                        existing_skills = {node.text.strip() for node in skills_elem.findall("skill") if node.text}
                        
                        for skill_text in new_skills:
                            if skill_text and skill_text not in existing_skills:
                                skill_node = ET.Element("skill")
                                skill_node.text = skill_text
                                skills_elem.append(skill_node)
                                existing_skills.add(skill_text)

            # 6. Convert final merged XML tree to a formatted string and render in text display
            rough_string = ET.tostring(template_root, encoding="utf-8")
            parsed_dom = minidom.parseString(rough_string)
            pretty_xml = parsed_dom.toprettyxml(indent="  ")
            
            # Clean up extra blank lines from minidom pretty print
            cleaned_xml = "\n".join([line for line in pretty_xml.splitlines() if line.strip()])
            
            self.text_display.setPlainText(cleaned_xml)
        except Exception as e:
            self.text_display.setPlainText(f"Error - Failed to generate and merge tailored CV: {e}")
