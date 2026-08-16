"""
OmniTranslator Pro - Language Toggle Widget [JA / ZH / EN]
"""

from PySide6 import QtWidgets, QtCore

class LanguageToggleWidget(QtWidgets.QWidget):
    """Segmented language selection widget."""
    language_changed = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.btn_group = QtWidgets.QButtonGroup(self)
        
        self.ja_btn = QtWidgets.QPushButton("🇯🇵 JA")
        self.zh_btn = QtWidgets.QPushButton("🇨🇳 ZH")
        self.en_btn = QtWidgets.QPushButton("🇺🇸 EN")
        
        for btn, lang in [(self.ja_btn, "JA"), (self.zh_btn, "ZH"), (self.en_btn, "EN")]:
            btn.setCheckable(True)
            self.btn_group.addButton(btn)
            layout.addWidget(btn)
            
        self.ja_btn.setChecked(True)
        self.btn_group.buttonClicked.connect(self._on_button_clicked)

    def _on_button_clicked(self, button):
        lang = button.text().split()[-1]
        self.language_changed.emit(lang)
