"""
OmniTranslator Pro - Main Dashboard Window
"""

import json
import asyncio
from pathlib import Path
from PySide6 import QtWidgets, QtCore, QtGui

from common.paths import get_app_data_path, get_resource_path
from common.config_loader import ConfigLoader
from common.logger import setup_logger
from domain.glossary.extractor import GlossaryExtractor
from ui.signals import TranslationSignals
from ui.settings_dialog import SettingsDialog
from ui.widgets.language_toggle import LanguageToggleWidget
from ui.widgets.preview_panel import DualPreviewPanel
from ui.widgets.glossary_table import GlossaryTableWidget
from ui.widgets.log_view import LogConsoleWidget
from core.orchestrator import TranslationOrchestrator
from core.session_manager import SessionManager

logger = setup_logger("MainWindow")

class MainWindow(QtWidgets.QMainWindow):
    """OmniTranslator Pro Main Dashboard Window."""

    LANG_BADGES = {
        "JA": "🇯🇵 일본어 (JA)",
        "ZH": "🇨🇳 중국어 (ZH)",
        "EN": "🇺🇸 영어 (EN)"
    }

    def __init__(self, loop=None, parent=None):
        super().__init__(parent)
        self.loop = loop
        self.signals = TranslationSignals()
        self.config = ConfigLoader.load_or_init_config()
        self.orchestrator = TranslationOrchestrator(self.signals, self.config)

        self.setWindowTitle("OmniTranslator Pro - 통합 배치 번역 시스템")
        self.resize(1150, 850)

        # Set application / window icon
        icon_path = get_resource_path("assets/icons/app_icon.png")
        if icon_path.exists():
            self.setWindowIcon(QtGui.QIcon(str(icon_path)))

        self._init_ui()
        self._wire_signals()
        
        # Initialize title badge with configured default language
        default_lang = self.config.get("default_language", "JA")
        self.lang_toggle.set_selected_language(default_lang)
        self._update_title_badge(default_lang)

        # Check API Keys on startup
        QtCore.QTimer.singleShot(500, self._check_initial_api_keys)

    def _check_initial_api_keys(self):
        """Displays startup warning if API keys are missing."""
        if not self.config.get("api_keys"):
            self.status_label.setText("⚠️ API 키가 등록되지 않았습니다. [⚙️ 설정]에서 키를 등록해주세요.")
            res = QtWidgets.QMessageBox.warning(
                self,
                "API 키 등록 필요",
                "API 키가 등록되지 않았습니다.\n지금 [⚙️ 설정] 창을 열어 Gemini API 키를 등록하시겠습니까?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
            if res == QtWidgets.QMessageBox.Yes:
                self._open_settings()

    def _update_title_badge(self, lang_code: str):
        """Updates the header title label in real-time with country/language badge and accent color."""
        badge = self.LANG_BADGES.get(lang_code.upper(), f"🌐 {lang_code}")
        self.app_title.setText(
            f"<span style='color: #8E75FF;'>OmniTranslator Pro</span>&nbsp;&nbsp;"
            f"<span style='color: #38BDF8; font-size: 15px; font-weight: bold;'>[{badge}]</span>"
        )

    def _init_ui(self):
        main_widget = QtWidgets.QWidget()
        self.setCentralWidget(main_widget)
        layout = QtWidgets.QVBoxLayout(main_widget)

        # 1. Header Row
        header = QtWidgets.QHBoxLayout()
        self.app_title = QtWidgets.QLabel("OmniTranslator Pro")
        self.app_title.setStyleSheet("font-size: 20px; font-weight: bold;")
        
        self.lang_toggle = LanguageToggleWidget()
        settings_btn = QtWidgets.QPushButton("⚙️ 설정")
        settings_btn.clicked.connect(self._open_settings)

        header.addWidget(self.app_title)
        header.addStretch()
        header.addWidget(self.lang_toggle)
        header.addWidget(settings_btn)

        # 2. File Selection Row
        file_box = QtWidgets.QGroupBox("번역 대상 파일 선택")
        file_layout = QtWidgets.QFormLayout(file_box)

        self.input_edit = QtWidgets.QLineEdit()
        self.output_edit = QtWidgets.QLineEdit()
        browse_btn = QtWidgets.QPushButton("📂 파일 선택 (EPUB/TXT)")
        browse_btn.clicked.connect(self._browse_file)

        in_row = QtWidgets.QHBoxLayout()
        in_row.addWidget(self.input_edit)
        in_row.addWidget(browse_btn)

        file_layout.addRow("입력 파일:", in_row)
        file_layout.addRow("출력 파일:", self.output_edit)

        # 3. Dashboard Progress Group
        dash_box = QtWidgets.QGroupBox("진행 현황 대시보드")
        dash_layout = QtWidgets.QVBoxLayout(dash_box)

        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setFormat("%p% (%v/%m Chunks)")
        self.progress_bar.setAlignment(QtCore.Qt.AlignCenter)
        self.status_label = QtWidgets.QLabel("준비됨")

        dash_layout.addWidget(self.progress_bar)
        dash_layout.addWidget(self.status_label)

        # 4. Central Tabs
        self.tabs = QtWidgets.QTabWidget()
        self.preview_panel = DualPreviewPanel()
        self.glossary_table = GlossaryTableWidget()
        self.log_console = LogConsoleWidget()

        self.tabs.addTab(self.preview_panel, "🟢 대시보드 & 검토")
        self.tabs.addTab(self.glossary_table, "📖 용어집 관리")
        self.tabs.addTab(self.log_console, "📜 실시간 로그")

        # 5. Bottom Action Controls
        action_layout = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton("▶ 번역 시작")
        self.pause_btn = QtWidgets.QPushButton("⏸️ 일시 정지")
        self.cancel_btn = QtWidgets.QPushButton("⏹️ 작업 취소")

        self.start_btn.clicked.connect(self._start_translation)
        self.pause_btn.clicked.connect(self._pause_translation)
        self.cancel_btn.clicked.connect(self._cancel_translation)

        self.pause_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)

        action_layout.addWidget(self.start_btn)
        action_layout.addWidget(self.pause_btn)
        action_layout.addWidget(self.cancel_btn)

        # Main Assembly
        layout.addLayout(header)
        layout.addWidget(file_box)
        layout.addWidget(dash_box)
        layout.addWidget(self.tabs)
        layout.addLayout(action_layout)

    def _wire_signals(self):
        self.signals.progress.connect(self._on_progress)
        self.signals.status_changed.connect(self._on_status)
        self.signals.log_emitted.connect(self.log_console.append_log)
        self.signals.preview_updated.connect(self.preview_panel.update_preview)
        self.signals.completed.connect(self._on_completed)
        self.signals.glossary_extracted.connect(self.glossary_table.set_entries)
        self.signals.glossary_loading.connect(self.glossary_table.set_loading)
        self.glossary_table.extract_requested.connect(self._trigger_glossary_extraction)
        self.lang_toggle.language_changed.connect(self._update_title_badge)

    def _browse_file(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "번역 파일 선택", "", "Supported Files (*.epub *.txt);;EPUB (*.epub);;TXT (*.txt)"
        )
        if file_path:
            p = Path(file_path)
            self.input_edit.setText(str(p))
            out_p = p.parent / f"{p.stem}_translated{p.suffix}"
            self.output_edit.setText(str(out_p))

            # 1. Clear previous glossary entries immediately to isolate per-file
            self.glossary_table.clear_entries()

            # 2. Check for per-file glossary json (e.g. A_novel.epub.glossary.json)
            glossary_file = p.parent / f"{p.name}.glossary.json"
            if glossary_file.exists():
                entries = GlossaryExtractor.load_glossary_json(glossary_file)
                self.glossary_table.set_entries(entries)
                logger.info(f"Loaded isolated glossary ({len(entries)} items) for {p.name}")
                self.status_label.setText(f"작품 용어집 로드됨 ({len(entries)}개 용어)")
            else:
                self.status_label.setText("작품 용어집 없음. [📖 용어집 관리] 탭에서 [🔍 AI 용어집 추출]을 눌러 생성할 수 있습니다.")

            # Check checkpoint
            ckpt = SessionManager.load_checkpoint(p)
            if ckpt:
                done_cnt = len(ckpt.get("translated_chunks", {}))
                tot_cnt = ckpt.get("total_chunks", 0)
                msg_text = f"이전에 중단된 작업이 있습니다. ({done_cnt}/{tot_cnt} 청크 완료)\n이어서 진행하시겠습니까?"
                res = QtWidgets.QMessageBox.question(
                    self, "이어서 번역하기", msg_text,
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
                )
                if res == QtWidgets.QMessageBox.No:
                    SessionManager.remove_checkpoint(p)

    def _trigger_glossary_extraction(self):
        in_path = self.input_edit.text().strip()
        if not in_path or not Path(in_path).exists():
            QtWidgets.QMessageBox.warning(self, "경고", "용어를 추출할 입력 파일을 먼저 선택해주세요.")
            return

        if not self.config.get("api_keys"):
            QtWidgets.QMessageBox.warning(self, "경고", "용어 추출을 위해 설정 메뉴에서 API 키를 먼저 등록해주세요.")
            self._open_settings()
            return

        lang = self.lang_toggle.get_selected_language()
        self.tabs.setCurrentIndex(1)  # Switch to Glossary Tab

        if self.loop:
            asyncio.run_coroutine_threadsafe(
                self.orchestrator.extract_glossary_async(Path(in_path), lang),
                self.loop
            )

    def _open_settings(self):
        dialog = SettingsDialog(self)
        dialog.load_settings()
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.config = ConfigLoader.load_or_init_config()
            self.orchestrator.key_manager.set_api_keys(self.config.get("api_keys", []))
            self.orchestrator.key_manager.set_request_delay(self.config.get("request_delay", 0.5))
            self.orchestrator.config = self.config
            logger.info("Settings updated and applied runtime.")

    def _start_translation(self):
        in_path = self.input_edit.text().strip()
        out_path = self.output_edit.text().strip()

        if not in_path or not Path(in_path).exists():
            QtWidgets.QMessageBox.warning(self, "경고", "유효한 입력 파일을 선택해주세요.")
            return

        if not self.config.get("api_keys"):
            QtWidgets.QMessageBox.warning(self, "경고", "설정 메뉴에서 최소 1개 이상의 API 키를 등록해주세요.")
            self._open_settings()
            return

        # Save current glossary UI table state to per-file json
        p_in = Path(in_path)
        glossary_entries = self.glossary_table.get_entries()
        if glossary_entries:
            glossary_file = p_in.parent / f"{p_in.name}.glossary.json"
            GlossaryExtractor.save_glossary_json(glossary_entries, glossary_file)

        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)

        lang = self.lang_toggle.get_selected_language()
        
        if self.loop:
            asyncio.run_coroutine_threadsafe(
                self.orchestrator.run_pipeline_async(
                    input_path=p_in,
                    output_path=Path(out_path),
                    language=lang,
                    active_glossary=glossary_entries
                ),
                self.loop
            )

    def _pause_translation(self):
        if self.orchestrator.is_paused:
            self.orchestrator.resume()
            self.pause_btn.setText("⏸️ 일시 정지")
        else:
            self.orchestrator.pause()
            self.pause_btn.setText("▶️ 번역 재개")

    def _cancel_translation(self):
        self.orchestrator.cancel()
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)

    def _on_progress(self, processed: int, total: int, msg: str):
        self.progress_bar.setRange(0, total if total > 0 else 100)
        self.progress_bar.setValue(processed)
        self.status_label.setText(msg)

    def _on_status(self, msg: str):
        self.status_label.setText(msg)

    def _on_completed(self, success: bool, info: str):
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        if success:
            QtWidgets.QMessageBox.information(self, "완료", info)
        else:
            QtWidgets.QMessageBox.warning(self, "알림", info)
