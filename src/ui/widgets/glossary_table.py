"""
OmniTranslator Pro - Interactive Glossary Management Table
"""

from PySide6 import QtWidgets, QtCore
from typing import List, Dict, Any

class GlossaryTableWidget(QtWidgets.QWidget):
    """Table widget for viewing, adding, editing, and deleting glossary entries."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)

        toolbar = QtWidgets.QHBoxLayout()
        add_btn = QtWidgets.QPushButton("➕ 항목 추가")
        del_btn = QtWidgets.QPushButton("🗑️ 삭제")
        add_btn.clicked.connect(self.add_row)
        del_btn.clicked.connect(self.delete_selected)
        toolbar.addWidget(add_btn)
        toolbar.addWidget(del_btn)
        toolbar.addStretch()

        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["원문 (Keyword)", "번역어 (Target)", "목표 언어", "등장 횟수"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)

        layout.addLayout(toolbar)
        layout.addWidget(self.table)

    def add_row(self):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QtWidgets.QTableWidgetItem("Keyword"))
        self.table.setItem(r, 1, QtWidgets.QTableWidgetItem("TargetWord"))
        self.table.setItem(r, 2, QtWidgets.QTableWidgetItem("ko"))
        self.table.setItem(r, 3, QtWidgets.QTableWidgetItem("1"))

    def delete_selected(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def get_entries(self) -> List[Dict[str, Any]]:
        entries = []
        for r in range(self.table.rowCount()):
            kw = self.table.item(r, 0)
            tr = self.table.item(r, 1)
            tl = self.table.item(r, 2)
            cnt = self.table.item(r, 3)
            if kw and tr:
                entries.append({
                    "keyword": kw.text().strip(),
                    "translated_keyword": tr.text().strip(),
                    "target_language": tl.text().strip() if tl else "ko",
                    "occurrence_count": int(cnt.text()) if cnt and cnt.text().isdigit() else 1
                })
        return entries
