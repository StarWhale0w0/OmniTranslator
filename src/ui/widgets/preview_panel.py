"""
OmniTranslator Pro - Dual Split Text Preview Panel
Displays cleaned, readable novel text in side-by-side comparison without ugly raw HTML tags.
"""

from PySide6 import QtWidgets, QtCore, QtGui
from domain.chunkers.base_chunker import BaseChunker
from domain.postprocess.cleaner import TextCleaner

class DualPreviewPanel(QtWidgets.QWidget):
    """Side-by-side comparison view for raw vs translated text with clean formatting."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # 1. Raw Input Group
        raw_group = QtWidgets.QGroupBox("원문 미리보기 (Raw Input)")
        raw_box = QtWidgets.QVBoxLayout(raw_group)
        self.raw_view = QtWidgets.QPlainTextEdit()
        self.raw_view.setReadOnly(True)
        self.raw_view.setLineWrapMode(QtWidgets.QPlainTextEdit.WidgetWidth)
        self.raw_view.setFont(QtGui.QFont("Malgun Gothic", 10))
        raw_box.addWidget(self.raw_view)

        # 2. Translated Output Group
        trans_group = QtWidgets.QGroupBox("번역문 미리보기 (Translated Output)")
        trans_box = QtWidgets.QVBoxLayout(trans_group)
        self.trans_view = QtWidgets.QPlainTextEdit()
        self.trans_view.setReadOnly(True)
        self.trans_view.setLineWrapMode(QtWidgets.QPlainTextEdit.WidgetWidth)
        self.trans_view.setFont(QtGui.QFont("Malgun Gothic", 10))
        trans_box.addWidget(self.trans_view)

        layout.addWidget(raw_group)
        layout.addWidget(trans_group)

    @classmethod
    def _format_preview_text(cls, text: str, max_chars: int = 800) -> str:
        """Cleans and formats HTML or raw text into readable preview prose."""
        if not text:
            return ""

        # Check for media tag presence
        if BaseChunker.is_media_only_chunk(text):
            return f"[🖼️ 이미지/삽화 미디어 태그]\n{text.strip()[:max_chars]}"

        # If text contains HTML tags, strip them cleanly into readable paragraphs
        if '<' in text and '>' in text:
            cleaned = TextCleaner.strip_html_tags(text)
            if not cleaned:
                # If stripped is empty but was not media-only
                return text.strip()[:max_chars]
            return cleaned[:max_chars]

        return text.strip()[:max_chars]

    def update_preview(self, raw_text: str, trans_text: str):
        """Updates preview panels with cleaned, readable text."""
        # Check for bypass notification markers
        if "[표지/삽화 이미지 구간" in trans_text or "[BYPASS_MEDIA]" in trans_text or "[미디어 바이패스]" in trans_text:
            self.raw_view.setPlainText(f"[🖼️ 이미지/미디어 태그]\n{raw_text.strip()[:400]}")
            self.trans_view.setPlainText("[🖼️ 미디어 태그 - 원본 구조 바이패스 유지]")
            return

        cleaned_raw = self._format_preview_text(raw_text)
        cleaned_trans = self._format_preview_text(trans_text)

        self.raw_view.setPlainText(cleaned_raw if cleaned_raw else "(내용 없음)")
        self.trans_view.setPlainText(cleaned_trans if cleaned_trans else "(번역 내용 없음)")
