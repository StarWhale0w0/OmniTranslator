"""
OmniTranslator Pro - Dual Split Text Preview Panel
"""

from PySide6 import QtWidgets, QtCore

class DualPreviewPanel(QtWidgets.QWidget):
    """Side-by-side comparison view for raw vs translated text."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        raw_group = QtWidgets.QGroupBox("원문 미리보기 (Raw Input)")
        raw_box = QtWidgets.QVBoxLayout(raw_group)
        self.raw_view = QtWidgets.QPlainTextEdit()
        self.raw_view.setReadOnly(True)
        raw_box.addWidget(self.raw_view)

        trans_group = QtWidgets.QGroupBox("번역문 미리보기 (Translated Output)")
        trans_box = QtWidgets.QVBoxLayout(trans_group)
        self.trans_view = QtWidgets.QPlainTextEdit()
        self.trans_view.setReadOnly(True)
        trans_box.addWidget(self.trans_view)

        layout.addWidget(raw_group)
        layout.addWidget(trans_group)

    def update_preview(self, raw_text: str, trans_text: str):
        self.raw_view.setPlainText(raw_text)
        self.trans_view.setPlainText(trans_text)
