"""
OmniTranslator Pro - TXT Line & Paragraph Chunker
Ported from batch_translator: splits text by paragraph lines up to max_size.
"""

from typing import List
from domain.chunkers.base_chunker import BaseChunker

class TxtChunker(BaseChunker):
    """Chunks plain text using line breaks while keeping paragraph bounds."""

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
