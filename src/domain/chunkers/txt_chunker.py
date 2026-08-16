"""TXT Sentence & Line Chunker (From Batch Translator)."""
from domain.chunkers.base_chunker import BaseChunker

class TxtChunker(BaseChunker):
    def split_into_chunks(self, content: str, max_size: int = 6000):
        pass
