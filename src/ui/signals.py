"""
OmniTranslator Pro - Qt Signal Definitions
"""

from PySide6 import QtCore

class TranslationSignals(QtCore.QObject):
    """Qt Signals for communicating progress and events to UI."""
    progress = QtCore.Signal(int, int, str)  # processed, total, message
    status_changed = QtCore.Signal(str)
    log_emitted = QtCore.Signal(str, str)     # level, text
    completed = QtCore.Signal(bool, str)       # success, info
