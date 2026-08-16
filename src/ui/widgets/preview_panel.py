"""
OmniTranslator Pro - Dual Preview Panel (Raw vs Translated)
"""

from PySide6 import QtWidgets

class DualPreviewPanel(QtWidgets.QWidget):
    """Side-by-side or stacked text preview panel."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        
        self.raw_view = QtWidgets.QPlainTextEdit()
        self.raw_view.setPlaceholderText("원문 미리보기 (Raw Content)...")
        
        self.trans_view = QtWidgets.QPlainTextEdit()
        self.trans_view.setPlaceholderText("번역문 미리보기 (Translated Content)...")
        
        layout.addWidget(self.raw_view)
        layout.addWidget(self.trans_view)
