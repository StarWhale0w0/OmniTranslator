"""
OmniTranslator Pro - Interactive Glossary Management Table
"""

import json
from pathlib import Path
from PySide6 import QtWidgets, QtCore
from typing import List, Dict, Any

class GlossaryTableWidget(QtWidgets.QWidget):
    """Table widget for viewing, adding, editing, searching, and saving glossary entries."""

    extract_requested = QtCore.Signal()  # Signal to trigger AI Glossary Extraction

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)

        # Top Action Toolbar
        toolbar = QtWidgets.QHBoxLayout()

        self.extract_btn = QtWidgets.QPushButton("🔍 AI 용어집 추출")
        self.extract_btn.setStyleSheet("background-color: #8E75FF; color: white; font-weight: bold;")
        self.extract_btn.clicked.connect(self.extract_requested.emit)

        add_btn = QtWidgets.QPushButton("➕ 행 추가")
        del_btn = QtWidgets.QPushButton("➖ 선택 삭제")
        clear_btn = QtWidgets.QPushButton("🗑️ 전체 비우기")
        save_btn = QtWidgets.QPushButton("💾 JSON으로 저장")
        load_btn = QtWidgets.QPushButton("📂 JSON 불러오기")

        add_btn.clicked.connect(self.add_row)
        del_btn.clicked.connect(self.delete_selected)
        clear_btn.clicked.connect(self.clear_entries)
        save_btn.clicked.connect(self._export_json)
        load_btn.clicked.connect(self._import_json)

        toolbar.addWidget(self.extract_btn)
        toolbar.addWidget(add_btn)
        toolbar.addWidget(del_btn)
        toolbar.addWidget(clear_btn)
        toolbar.addStretch()
        toolbar.addWidget(save_btn)
        toolbar.addWidget(load_btn)

        # Progress / Status Bar for Extraction
        self.status_layout = QtWidgets.QHBoxLayout()
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate spinner
        self.progress_bar.setMaximumHeight(14)
        self.progress_bar.setVisible(False)

        self.status_label = QtWidgets.QLabel("준비됨")
        self.status_label.setStyleSheet("color: #A0A0AA; font-size: 12px;")

        self.status_layout.addWidget(self.progress_bar)
        self.status_layout.addWidget(self.status_label)
        self.status_layout.addStretch()

        # Main Table
        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["원문 (Keyword)", "번역어 (Target)", "구분 (Category)", "등장 횟수"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)

        layout.addLayout(toolbar)
        layout.addLayout(self.status_layout)
        layout.addWidget(self.table)

    def set_loading(self, is_loading: bool, msg: str = ""):
        self.progress_bar.setVisible(is_loading)
        self.extract_btn.setEnabled(not is_loading)
        self.status_label.setText(msg if msg else ("용어 추출 중..." if is_loading else "준비됨"))

    def add_row(self, keyword: str = "", target: str = "", category: str = "고유명사", count: int = 1):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(keyword or "Keyword"))
        self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(target or "TargetWord"))
        self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(category or "고유명사"))
        self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(str(count)))

    def delete_selected(self):
        selected_rows = sorted(set(index.row() for index in self.table.selectedIndexes()), reverse=True)
        for r in selected_rows:
            self.table.removeRow(r)

    def clear_entries(self):
        self.table.setRowCount(0)

    def set_entries(self, entries: List[Dict[str, Any]]):
        self.clear_entries()
        for item in entries:
            self.add_row(
                keyword=item.get("keyword", ""),
                target=item.get("translated_keyword", ""),
                category=item.get("category", "고유명사"),
                count=item.get("occurrence_count", 1)
            )

    def get_entries(self) -> List[Dict[str, Any]]:
        entries = []
        for r in range(self.table.rowCount()):
            kw = self.table.item(r, 0)
            tr = self.table.item(r, 1)
            cat = self.table.item(r, 2)
            cnt = self.table.item(r, 3)
            if kw and tr and kw.text().strip():
                entries.append({
                    "keyword": kw.text().strip(),
                    "translated_keyword": tr.text().strip(),
                    "category": cat.text().strip() if cat else "고유명사",
                    "occurrence_count": int(cnt.text()) if cnt and cnt.text().isdigit() else 1
                })
        return entries

    def _export_json(self):
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "용어집 JSON 내보내기", "glossary.json", "JSON Files (*.json)"
        )
        if file_path:
            entries = self.get_entries()
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(entries, f, ensure_ascii=False, indent=2)
            QtWidgets.QMessageBox.information(self, "완료", f"용어집 {len(entries)}개 항목을 저장했습니다.")

    def _import_json(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "용어집 JSON 불러오기", "", "JSON Files (*.json)"
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.set_entries(data)
                        QtWidgets.QMessageBox.information(self, "완료", f"용어집 {len(data)}개 항목을 로드했습니다.")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "오류", f"JSON 불러오기 실패: {e}")
