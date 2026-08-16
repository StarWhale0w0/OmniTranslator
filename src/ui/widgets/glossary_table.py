"""
OmniTranslator Pro - Glossary Management Table Widget
"""

from PySide6 import QtWidgets

class GlossaryTableWidget(QtWidgets.QTableWidget):
    """Table widget for managing terms."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(4)
        self.setHorizontalHeaderLabels(["Original Term", "Translated Term", "Target Lang", "Count"])
