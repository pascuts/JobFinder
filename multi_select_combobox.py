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

from PySide6.QtCore import Qt, QEvent, Signal
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtWidgets import QComboBox, QLineEdit, QListView

class MultiSelectComboBox(QComboBox):
    selectionChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.lineEdit().setReadOnly(True)
        self.lineEdit().setPlaceholderText("Select Contract Types...")

        self.model = QStandardItemModel(self)
        self.setModel(self.model)

        # Ensure the popup list stays open while checking items
        self.setView(QListView())
        self.view().viewport().installEventFilter(self)

        self.model.itemChanged.connect(self._update_text)

    def eventFilter(self, widget, event):
        # Keep popup open when toggling checkboxes inside the view
        if widget == self.view().viewport() and event.type() == QEvent.Type.MouseButtonRelease:
            index = self.view().indexAt(event.pos())
            if index.isValid():
                item = self.model.itemFromIndex(index)
                if item.isCheckable():
                    item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)
                    return True
        return super().eventFilter(widget, event)

    def addItemWithData(self, text: str, key: str, checked: bool = False):
        item = QStandardItem(text)
        item.setData(key, Qt.ItemDataRole.UserRole)
        item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.model.appendRow(item)
        self._update_text()

    def addItemsWithData(self, items: list[tuple[str, str]]):
        for text, key in items:
            self.addItemWithData(text, key)

    def selected_keys(self) -> list[str]:
        keys = []
        for row in range(self.model.rowCount()):
            item = self.model.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                keys.append(item.data(Qt.ItemDataRole.UserRole))
        return keys

    def selected_keys_param(self) -> str:
        return "%2C".join(self.selected_keys())

    def selected_texts(self) -> list[str]:
        texts = []
        for row in range(self.model.rowCount()):
            item = self.model.item(row)
            if item.checkState() == Qt.CheckState.Checked:
                texts.append(item.text())
        return texts

    def _update_text(self):
        selected = self.selected_texts()
        if not selected:
            self.lineEdit().setText("All Types / Unfiltered")
        else:
            self.lineEdit().setText(", ".join(selected))
        self.selectionChanged.emit()