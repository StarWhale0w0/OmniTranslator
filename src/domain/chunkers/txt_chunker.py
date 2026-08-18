"""
OmniTranslator Pro - TXT Line & Paragraph Chunker
Alias and compatibility layer for PlainTextChunker.
"""

from domain.chunkers.plain_text_chunker import PlainTextChunker

class TxtChunker(PlainTextChunker):
    """Chunks plain text using line breaks while keeping paragraph bounds."""
    pass
