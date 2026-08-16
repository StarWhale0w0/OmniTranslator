"""
OmniTranslator Pro - Base Chunker Interface
"""

import re
from abc import ABC, abstractmethod
from typing import List

class BaseChunker(ABC):
    """Abstract Base Class for text chunkers."""

    @abstractmethod
    def split_into_chunks(self, content: str, max_size: int = 6000) -> List[str]:
        """Splits full content into chunk strings of maximum size."""
        pass

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
