"""
OmniTranslator Pro - Language Selection Toggle Widget [JA / ZH / EN]
"""

from PySide6 import QtWidgets, QtCore

class LanguageToggleWidget(QtWidgets.QWidget):
    """Segmented language selection button group."""

    language_changed = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.btn_group = QtWidgets.QButtonGroup(self)
        self.ja_btn = QtWidgets.QPushButton("🇯🇵 JA")
        self.zh_btn = QtWidgets.QPushButton("🇨🇳 ZH")
        self.en_btn = QtWidgets.QPushButton("🇺🇸 EN")

        for btn, lang in [(self.ja_btn, "JA"), (self.zh_btn, "ZH"), (self.en_btn, "EN")]:
            btn.setCheckable(True)
            btn.setFixedSize(65, 30)
            self.btn_group.addButton(btn)
            layout.addWidget(btn)

        self.ja_btn.setChecked(True)
        self.btn_group.buttonClicked.connect(self._on_click)

    def _on_click(self, button):
        lang_code = button.text().split()[-1]
        self.language_changed.emit(lang_code)

    def get_selected_language(self) -> str:
        checked = self.btn_group.checkedButton()
        return checked.text().split()[-1] if checked else "JA"

    def set_selected_language(self, lang_code: str):
        target = lang_code.upper()
        if target == "ZH":
            self.zh_btn.setChecked(True)
        elif target == "EN":
            self.en_btn.setChecked(True)
        else:
            self.ja_btn.setChecked(True)
        self.language_changed.emit(target)
