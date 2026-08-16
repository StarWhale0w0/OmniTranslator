"""
OmniTranslator Pro - Seamarine-Style Quick Settings Modal Dialog
Supports General Settings and Prompt Management tabs.
"""

import json
from pathlib import Path
from PySide6 import QtWidgets, QtCore
from common.paths import get_app_data_path
from domain.profiles.ja_profile import DEFAULT_SYSTEM_PROMPT as JA_DEFAULT
from domain.profiles.zh_profile import DEFAULT_SYSTEM_PROMPT as ZH_DEFAULT
from domain.profiles.en_profile import DEFAULT_SYSTEM_PROMPT as EN_DEFAULT

class SettingsDialog(QtWidgets.QDialog):
    """Quick settings modal popup window with TabWidget."""

    DEFAULTS = {
        "JA": JA_DEFAULT,
        "ZH": ZH_DEFAULT,
        "EN": EN_DEFAULT
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ 빠른 번역 설정 (Quick Settings)")
        self.resize(580, 560)
        self.config_path = get_app_data_path("config.json")
        
        self.prompts_data = {
            "JA": {"system_prompt": JA_DEFAULT, "custom_rules": ""},
            "ZH": {"system_prompt": ZH_DEFAULT, "custom_rules": ""},
            "EN": {"system_prompt": EN_DEFAULT, "custom_rules": ""}
        }
        self.current_prompt_lang = "JA"

        self._init_ui()
        self._load_config()

    def _init_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        self.tab_widget = QtWidgets.QTabWidget()

        # --------------------------------------------------------------------
        # TAB 1: General Settings
        # --------------------------------------------------------------------
        general_tab = QtWidgets.QWidget()
        gen_layout = QtWidgets.QFormLayout(general_tab)

        self.api_keys_text = QtWidgets.QPlainTextEdit()
        self.api_keys_text.setPlaceholderText("API 키를 줄바꿈으로 구분하여 입력")
        self.api_keys_text.setMaximumHeight(90)

        self.model_combo = QtWidgets.QComboBox()
        self.model_combo.addItems([
            "gemini-2.5-flash",
            "gemini-3-pro-preview",
            "gemini-2.0-flash",
            "gemini-2.0-pro"
        ])

        self.workers_spin = QtWidgets.QSpinBox()
        self.workers_spin.setRange(1, 20)
        self.workers_spin.setValue(4)

        self.temp_spin = QtWidgets.QDoubleSpinBox()
        self.temp_spin.setRange(0.0, 2.0)
        self.temp_spin.setSingleStep(0.1)
        self.temp_spin.setValue(0.7)

        self.thinking_combo = QtWidgets.QComboBox()
        self.thinking_combo.addItems(["low", "high"])
        self.thinking_combo.setCurrentText("high")

        self.prefill_check = QtWidgets.QCheckBox("검열 우회 Prefill 가상 대화 활성화")
        self.prefill_check.setChecked(True)

        gen_layout.addRow("API Key 목록:", self.api_keys_text)
        gen_layout.addRow("번역 모델:", self.model_combo)
        gen_layout.addRow("동시 작업 수 (Workers):", self.workers_spin)
        gen_layout.addRow("Temperature:", self.temp_spin)
        gen_layout.addRow("Thinking Level:", self.thinking_combo)
        gen_layout.addRow("Prefill 모드:", self.prefill_check)

        # --------------------------------------------------------------------
        # TAB 2: Prompt Management
        # --------------------------------------------------------------------
        prompt_tab = QtWidgets.QWidget()
        prompt_layout = QtWidgets.QVBoxLayout(prompt_tab)

        # Language Selector for Prompts
        lang_row = QtWidgets.QHBoxLayout()
        lang_label = QtWidgets.QLabel("언어 선택:")
        self.prompt_lang_combo = QtWidgets.QComboBox()
        self.prompt_lang_combo.addItem("🇯🇵 일본어 (JA)", "JA")
        self.prompt_lang_combo.addItem("🇨🇳 중국어 (ZH)", "ZH")
        self.prompt_lang_combo.addItem("🇺🇸 영어 (EN)", "EN")
        self.prompt_lang_combo.currentIndexChanged.connect(self._on_prompt_lang_changed)

        self.reset_btn = QtWidgets.QPushButton("🔄 기본값으로 복원")
        self.reset_btn.clicked.connect(self._reset_current_prompt)

        lang_row.addWidget(lang_label)
        lang_row.addWidget(self.prompt_lang_combo)
        lang_row.addStretch()
        lang_row.addWidget(self.reset_btn)

        # System Prompt Editor
        sys_label = QtWidgets.QLabel("시스템 프롬프트 (System Instruction):")
        self.sys_prompt_edit = QtWidgets.QPlainTextEdit()
        self.sys_prompt_edit.setMinimumHeight(130)

        # Custom Rules Editor
        custom_label = QtWidgets.QLabel("사용자 추가 지침 (Custom Rules):")
        self.custom_rules_edit = QtWidgets.QPlainTextEdit()
        self.custom_rules_edit.setPlaceholderText("예: 주인공 서술 시 경어체 사용, 특정 캐릭터 말끝에 '~냥' 추가 등")
        self.custom_rules_edit.setMinimumHeight(80)

        # Helper Tooltip Guide
        guide_label = QtWidgets.QLabel("💡 슬롯 안내: {{glossary_context}} (동적 용어집), {{slot}} (원문 청크)")
        guide_label.setStyleSheet("color: #8E75FF; font-size: 11px;")

        prompt_layout.addLayout(lang_row)
        prompt_layout.addWidget(sys_label)
        prompt_layout.addWidget(self.sys_prompt_edit)
        prompt_layout.addWidget(custom_label)
        prompt_layout.addWidget(self.custom_rules_edit)
        prompt_layout.addWidget(guide_label)

        # Add tabs
        self.tab_widget.addTab(general_tab, "⚙️ 일반 설정")
        self.tab_widget.addTab(prompt_tab, "📝 프롬프트 관리")

        # Dialog Action Buttons
        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._save_config)
        btn_box.rejected.connect(self.reject)

        main_layout.addWidget(self.tab_widget)
        main_layout.addWidget(btn_box)

    def _on_prompt_lang_changed(self, index: int):
        # Save current memory before switching
        self._sync_current_prompt_ui_to_memory()
        
        # Switch language
        self.current_prompt_lang = self.prompt_lang_combo.currentData()
        self._load_prompt_memory_to_ui()

    def _sync_current_prompt_ui_to_memory(self):
        lang = self.current_prompt_lang
        self.prompts_data[lang] = {
            "system_prompt": self.sys_prompt_edit.toPlainText().strip(),
            "custom_rules": self.custom_rules_edit.toPlainText().strip()
        }

    def _load_prompt_memory_to_ui(self):
        lang = self.current_prompt_lang
        data = self.prompts_data.get(lang, {})
        self.sys_prompt_edit.setPlainText(data.get("system_prompt", self.DEFAULTS.get(lang, "")))
        self.custom_rules_edit.setPlainText(data.get("custom_rules", ""))

    def _reset_current_prompt(self):
        lang = self.current_prompt_lang
        default_prompt = self.DEFAULTS.get(lang, "")
        self.sys_prompt_edit.setPlainText(default_prompt)
        self.custom_rules_edit.clear()
        self._sync_current_prompt_ui_to_memory()

    def _load_config(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    keys = cfg.get("api_keys", [])
                    self.api_keys_text.setPlainText("\n".join(keys))
                    self.model_combo.setCurrentText(cfg.get("current_model", "gemini-2.5-flash"))
                    self.workers_spin.setValue(cfg.get("max_workers", 4))
                    self.temp_spin.setValue(cfg.get("temperature", 0.7))
                    self.thinking_combo.setCurrentText(cfg.get("thinking_level", "high"))
                    self.prefill_check.setChecked(cfg.get("enable_prefill", True))

                    # Load prompts schema
                    saved_prompts = cfg.get("prompts", {})
                    for l_code in ["JA", "ZH", "EN"]:
                        if l_code in saved_prompts:
                            self.prompts_data[l_code] = {
                                "system_prompt": saved_prompts[l_code].get("system_prompt", self.DEFAULTS[l_code]),
                                "custom_rules": saved_prompts[l_code].get("custom_rules", "")
                            }
            except Exception:
                pass
        self._load_prompt_memory_to_ui()

    def _save_config(self):
        self._sync_current_prompt_ui_to_memory()
        keys = [k.strip() for k in self.api_keys_text.toPlainText().splitlines() if k.strip()]
        
        cfg = {
            "api_keys": keys,
            "current_model": self.model_combo.currentText(),
            "max_workers": self.workers_spin.value(),
            "temperature": self.temp_spin.value(),
            "thinking_level": self.thinking_combo.currentText(),
            "enable_prefill": self.prefill_check.isChecked(),
            "prompts": self.prompts_data
        }
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        self.accept()
