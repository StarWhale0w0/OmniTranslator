"""
OmniTranslator Pro - EPUB DOM Structure-Preserving Chunker
Alias and compatibility layer for DomChunker.
"""

from domain.chunkers.dom_chunker import DomChunker

class EpubDomChunker(DomChunker):
    """EPUB DOM Chunker extending DomChunker for backward compatibility."""
    pass
