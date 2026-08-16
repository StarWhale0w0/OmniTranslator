"""
OmniTranslator Pro - Main Window (PySide6)
"""

from PySide6 import QtWidgets, QtCore
from ui.widgets.language_toggle import LanguageToggleWidget
from ui.settings_dialog import SettingsDialog
from ui.signals import TranslationSignals

class MainWindow(QtWidgets.QMainWindow):
    """Main dashboard window."""
    def __init__(self, loop=None, parent=None):
        super().__init__(parent)
        self.loop = loop
        self.signals = TranslationSignals()
        self.setWindowTitle("OmniTranslator Pro")
        self.resize(1100, 800)
        self._init_ui()

    def _init_ui(self):
        main_widget = QtWidgets.QWidget()
        self.setCentralWidget(main_widget)
        layout = QtWidgets.QVBoxLayout(main_widget)
        
        # Header bar
        header_layout = QtWidgets.QHBoxLayout()
        title_label = QtWidgets.QLabel("OmniTranslator Pro")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #8E75FF;")
        
        self.lang_toggle = LanguageToggleWidget()
        settings_btn = QtWidgets.QPushButton("⚙️ 설정")
        settings_btn.clicked.connect(self._open_settings)
        
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.lang_toggle)
        header_layout.addWidget(settings_btn)
        
        layout.addLayout(header_layout)
        
    def _open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()
