"""
OmniTranslator Pro - Qt Signal Definitions
"""

from PySide6 import QtCore

class TranslationSignals(QtCore.QObject):
    """Qt Signals for communicating progress and events to UI thread safely."""
    progress = QtCore.Signal(int, int, str)          # processed_chunks, total_chunks, status_text
    status_changed = QtCore.Signal(str)              # status message
    log_emitted = QtCore.Signal(str, str)             # level (INFO/WARNING/ERROR), text
    preview_updated = QtCore.Signal(str, str)         # raw_snippet, trans_snippet
    completed = QtCore.Signal(bool, str)              # success, message/error_details
    glossary_extracted = QtCore.Signal(list)          # extracted entries list
    glossary_loading = QtCore.Signal(bool, str)       # is_loading, message
