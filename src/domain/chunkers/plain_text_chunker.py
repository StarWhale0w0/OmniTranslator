"""
OmniTranslator Pro - Plain Text Line & Paragraph Chunker
Chunks plain text by paragraph boundaries without artificial HTML wrapping.
Ensures sentence boundary safety so trailing sentences never get truncated.
"""

from typing import List
from domain.chunkers.base_chunker import BaseChunker
from domain.chunkers.dom_chunker import DomChunker

class PlainTextChunker(BaseChunker):
    """Chunks pure novel text into clean segments preserving paragraph and sentence boundaries."""

    def split_into_chunks(self, content: str, max_size: int = 6000) -> List[str]:
        if max_size <= 0:
            raise ValueError("max_size must be > 0")

        if not content:
            return []

        chunks: List[str] = []
        current_chunk = ""
        lines = content.splitlines(keepends=True)

        for line in lines:
            if len(current_chunk) + len(line) <= max_size:
                current_chunk += line
            else:
                if current_chunk:
                    if current_chunk.strip():
                        chunks.append(current_chunk)

                if len(line) > max_size:
                    sub_chunks = DomChunker.split_text_by_sentence_boundary(line, max_size)
                    for sub in sub_chunks:
                        if sub.strip():
                            chunks.append(sub)
                    current_chunk = ""
                else:
                    current_chunk = line

        if current_chunk and current_chunk.strip():
            chunks.append(current_chunk)

        # Filter out purely empty chunks
        return [c for c in chunks if self.has_meaningful_text(c) or self.has_media_tags(c)]

# Alias for backward compatibility
TxtChunker = PlainTextChunker
