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
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut, QTextCharFormat, QSyntaxHighlighter
from PySide6.QtWidgets import QApplication, QInputDialog, QMainWindow, QTextEdit

class LogHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.search_pattern = ""

        # Define custom format: Yellow background, red text
        self.highlight_format = QTextCharFormat()
        self.highlight_format.setBackground(QColor("#FFFF00"))
        self.highlight_format.setForeground(QColor("#FF0000"))

    def set_search_pattern(self, pattern: str):
        self.search_pattern = pattern
        self.rehighlight()

    def highlightBlock(self, text: str):
        if not self.search_pattern:
            return

        pattern_length = len(self.search_pattern)
        index = text.lower().find(self.search_pattern.lower())

        # Find and format all occurrences within the current block
        while index >= 0:
            self.setFormat(index, pattern_length, self.highlight_format)
            index = text.lower().find(self.search_pattern.lower(), index + pattern_length)

class SearchableLogEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.highlighter = LogHighlighter(self.document())

        # Ctrl+F to trigger search input
        self.search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.search_shortcut.activated.connect(self.open_search_dialog)

        # Esc to clear existing highlights
        self.clear_shortcut = QShortcut(QKeySequence("Esc"), self)
        self.clear_shortcut.activated.connect(self.clear_highlights)

    def open_search_dialog(self):
        query, ok = QInputDialog.getText(self, "Find in Logs", "Search text:")
        if ok and query.strip():
            self.highlighter.set_search_pattern(query.strip())
            # Jump cursor to the first occurrence if found
            if not self.find(query.strip()):
                self.moveCursor(self.textCursor().MoveOperation.Start)
                self.find(query.strip())
        elif ok and not query.strip():
            self.clear_highlights()

    def clear_highlights(self):
        self.highlighter.set_search_pattern("")