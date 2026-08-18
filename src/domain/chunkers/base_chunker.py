"""
OmniTranslator Pro - Base Chunker Interface
"""

import re
import html
from abc import ABC, abstractmethod
from typing import List
from bs4 import BeautifulSoup

class BaseChunker(ABC):
    """Abstract Base Class for text chunkers with utility methods for content inspection."""

    MEDIA_TAG_PATTERN = re.compile(r'<(?:img|image|svg|picture|video|audio)\b', re.IGNORECASE)

    @abstractmethod
    def split_into_chunks(self, content: str, max_size: int = 6000) -> List[str]:
        """Splits full content into chunk strings of maximum size."""
        pass

    @classmethod
    def extract_pure_text(cls, content: str) -> str:
        """Extracts stripped pure text without HTML tags and entities."""
        if not content:
            return ""
        if '<' in content:
            try:
                text = BeautifulSoup(content, 'html.parser').get_text(separator=' ', strip=True)
                return html.unescape(text).strip()
            except Exception:
                text = re.sub(r'<[^>]+>', ' ', content)
                return html.unescape(text).strip()
        return html.unescape(content).strip()

    @classmethod
    def has_meaningful_text(cls, content: str, min_len: int = 1) -> bool:
        """Returns True if content contains meaningful non-whitespace text of at least min_len chars."""
        return len(cls.extract_pure_text(content)) >= min_len

    @classmethod
    def has_media_tags(cls, content: str) -> bool:
        """Checks if content contains media elements like img, svg, image, picture, video, audio."""
        if not content:
            return False
        return bool(cls.MEDIA_TAG_PATTERN.search(content))

    @classmethod
    def is_media_only_chunk(cls, content: str) -> bool:
        """Returns True if chunk has media tags but no meaningful text."""
        return cls.has_media_tags(content) and not cls.has_meaningful_text(content)

    @classmethod
    def is_empty_chunk(cls, content: str) -> bool:
        """Returns True if chunk has neither text nor media tags."""
        return not cls.has_meaningful_text(content) and not cls.has_media_tags(content)

    def split_chunk_binary(self, chunk_text: str) -> List[str]:
        """Splits a single chunk into two equal halves (for safety retry isolation)."""
        mid = len(chunk_text) // 2
        newline_pos = chunk_text.find('\n', max(0, mid - 200))
        if newline_pos != -1 and abs(newline_pos - mid) < 300:
            mid = newline_pos + 1

        half1 = chunk_text[:mid].strip()
        half2 = chunk_text[mid:].strip()
        return [h for h in [half1, half2] if h]

    def split_chunk_by_sentences(self, chunk_text: str, max_sentences: int = 2) -> List[str]:
        """Splits chunk into small micro-chunks by sentence punctuation."""
        sentence_pattern = r'([.!?。！？]+\s*|\n+)'
        parts = re.split(sentence_pattern, chunk_text)
        
        sentences = []
        for i in range(0, len(parts) - 1, 2):
            sentences.append(parts[i] + parts[i+1])
        if len(parts) % 2 == 1 and parts[-1].strip():
            sentences.append(parts[-1])

        chunks = []
        for i in range(0, len(sentences), max_sentences):
            group = "".join(sentences[i:i + max_sentences]).strip()
            if group:
                chunks.append(group)
        return chunks if chunks else [chunk_text]
