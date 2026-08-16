"""
OmniTranslator Pro - Main Dashboard Window
"""

import json
import asyncio
from pathlib import Path
from PySide6 import QtWidgets, QtCore

from common.paths import get_app_data_path
from common.logger import setup_logger
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

    def __init__(self, loop=None, parent=None):
        super().__init__(parent)
        self.loop = loop
        self.signals = TranslationSignals()
        self.config = self._load_config()
        self.orchestrator = TranslationOrchestrator(self.signals, self.config)

        self.setWindowTitle("OmniTranslator Pro - 통합 배치 번역 시스템")
        self.resize(1150, 850)
        self._init_ui()
        self._wire_signals()

    def _load_config(self) -> dict:
        config_path = get_app_data_path("config.json")
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "api_keys": [],
            "translation_model": "gemini-2.5-flash",
            "glossary_model": "gemini-2.5-flash",
            "max_workers": 4,
            "chunk_size": 4000,
            "request_delay": 0.5,
            "use_dynamic_glossary": True
        }

    def _init_ui(self):
        main_widget = QtWidgets.QWidget()
        self.setCentralWidget(main_widget)
        layout = QtWidgets.QVBoxLayout(main_widget)

        # 1. Header Row
        header = QtWidgets.QHBoxLayout()
        app_title = QtWidgets.QLabel("OmniTranslator Pro")
        app_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #8E75FF;")
        
        self.lang_toggle = LanguageToggleWidget()
        settings_btn = QtWidgets.QPushButton("⚙️ 설정")
        settings_btn.clicked.connect(self._open_settings)

        header.addWidget(app_title)
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
        self.status_label = QtWidgets.QLabel("대기 중")

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

    def _browse_file(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "번역 파일 선택", "", "Supported Files (*.epub *.txt);;EPUB (*.epub);;TXT (*.txt)"
        )
        if file_path:
            p = Path(file_path)
            self.input_edit.setText(str(p))
            out_p = p.parent / f"{p.stem}_translated{p.suffix}"
            self.output_edit.setText(str(out_p))

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

    def _open_settings(self):
        dialog = SettingsDialog(self)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.config = self._load_config()
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

        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)

        lang = self.lang_toggle.get_selected_language()
        
        if self.loop:
            asyncio.run_coroutine_threadsafe(
                self.orchestrator.run_pipeline_async(Path(in_path), Path(out_path), lang),
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
