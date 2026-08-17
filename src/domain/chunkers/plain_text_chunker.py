"""
OmniTranslator Pro - Plain Text Line & Paragraph Chunker
Chunks plain text by paragraph boundaries without any artificial HTML wrapping.
"""

from typing import List
from domain.chunkers.base_chunker import BaseChunker

class PlainTextChunker(BaseChunker):
    """Chunks pure novel text into clean segments preserving paragraph boundaries."""

    def split_into_chunks(self, content: str, max_size: int = 6000) -> List[str]:
        if max_size <= 0:
            raise ValueError("max_size must be > 0")

        chunks: List[str] = []
        current_chunk = ""
        lines = content.splitlines(keepends=True)

        for line in lines:
            if len(current_chunk) + len(line) <= max_size:
                current_chunk += line
            else:
                if current_chunk:
                    chunks.append(current_chunk)

                if len(line) > max_size:
                    for i in range(0, len(line), max_size):
                        chunks.append(line[i:i + max_size])
                    current_chunk = ""
                else:
                    current_chunk = line

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

# Alias for backward compatibility
TxtChunker = PlainTextChunker
