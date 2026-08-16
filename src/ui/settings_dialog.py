"""
OmniTranslator Pro - Quick Settings Modal Dialog
"""

from PySide6 import QtWidgets

class SettingsDialog(QtWidgets.QDialog):
    """Settings modal window."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ 빠른 번역 설정 (Settings)")
        self.resize(500, 400)
        self._init_ui()

    def _init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        form_layout = QtWidgets.QFormLayout()
        
        self.api_key_input = QtWidgets.QLineEdit()
        self.api_key_input.setEchoMode(QtWidgets.QLineEdit.Password)
        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.addItems(["gemini-2.5-flash", "gemini-3-pro-preview", "gemini-2.0-flash"])
        self.workers_spin = QtWidgets.QSpinBox()
        self.workers_spin.setRange(1, 20)
        self.workers_spin.setValue(4)
        
        form_layout.addRow("API Key:", self.api_key_input)
        form_layout.addRow("Model:", self.model_combo)
        form_layout.addRow("Max Workers:", self.workers_spin)
        
        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        
        layout.addLayout(form_layout)
        layout.addWidget(btn_box)
