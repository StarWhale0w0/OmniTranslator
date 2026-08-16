"""
OmniTranslator Pro - Realtime Console Log View
"""

from PySide6 import QtWidgets, QtGui, QtCore

class LogConsoleWidget(QtWidgets.QPlainTextEdit):
    """Console view with colored log output."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(1000)
        self.setStyleSheet("background-color: #0D0D0F; font-family: Consolas, monospace;")

    def append_log(self, level: str, text: str):
        color = "#A0A0AA"
        if level == "WARNING":
            color = "#FFB74D"
        elif level == "ERROR":
            color = "#E57373"

        html_str = f'<span style="color: {color};">[{level}] {text}</span>'
        self.appendHtml(html_str)
