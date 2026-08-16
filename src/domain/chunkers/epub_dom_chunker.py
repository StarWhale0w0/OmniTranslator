"""EPUB DOM Structure Preserving Chunker (From Seamarine)."""
from domain.chunkers.base_chunker import BaseChunker

class EpubDomChunker(BaseChunker):
    def split_into_chunks(self, content: str, max_size: int = 2000):
        pass
