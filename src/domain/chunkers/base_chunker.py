"""Base Chunker Interface."""

class BaseChunker:
    def split_into_chunks(self, content: str, max_size: int):
        raise NotImplementedError
