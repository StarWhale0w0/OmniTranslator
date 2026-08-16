"""
OmniTranslator Pro - Realtime Console Log Widget
"""

from PySide6 import QtWidgets

class LogConsoleWidget(QtWidgets.QPlainTextEdit):
    """Console widget for displaying system logs."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
