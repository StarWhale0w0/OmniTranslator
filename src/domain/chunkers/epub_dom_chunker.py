"""
OmniTranslator Pro - EPUB DOM Structure-Preserving Chunker
Ported verbatim from seamarine-lightnovel-translator: chunk_body_preserving_structure
"""

import copy
from typing import Any, Tuple, List, Optional, Dict
from bs4 import BeautifulSoup, Tag, NavigableString
from domain.chunkers.base_chunker import BaseChunker

class EpubDomChunker(BaseChunker):
    """Chunks HTML content preserving tag hierarchy and markup attributes."""

    @classmethod
    def chunk_body_preserving_structure(cls, body: BeautifulSoup, max_chars: int = 2000) -> List[Any]:
        """Ported directly from seamarine_lightnovel_translator.py."""
        chunks = []
        current_chunk = BeautifulSoup("<div></div>", "html.parser").div
        for element in body.contents:
            element_str = str(element)
            if len(str(current_chunk)) + len(element_str) > max_chars:
                if current_chunk.contents:
                    chunks.append(copy.copy(current_chunk))
                    current_chunk.clear()
                if len(element_str) > max_chars:
                    if isinstance(element, NavigableString):
                        text = str(element)
                        for i in range(0, len(text), max_chars):
                            new_tag = BeautifulSoup("<div></div>", "html.parser").div
                            new_tag.append(text[i:i+max_chars])
                            chunks.append(new_tag)
                    elif isinstance(element, Tag):
                        temp_tag = element.__copy__()
                        temp_tag.clear()
                        for child in element.contents:
                            child_str = str(child)
                            if len(str(temp_tag)) + len(child_str) > max_chars:
                                if temp_tag.contents:
                                    chunks.append(temp_tag)
                                    temp_tag = element.__copy__()
                                    temp_tag.clear()
                            temp_tag.append(child)
                        if temp_tag.contents:
                            chunks.append(temp_tag)
                    else:
                        chunks.append(element)
                else:
                    current_chunk.append(element)
            else:
                current_chunk.append(element)
        if current_chunk.contents:
            chunks.append(copy.copy(current_chunk))
        return chunks

    def split_into_chunks(self, content: str, max_size: int = 2000) -> List[str]:
        soup = BeautifulSoup(content, 'html.parser')
        body = soup.body if soup.body else soup
        parsed_chunks = self.chunk_body_preserving_structure(body, max_chars=max_size)
        return [str(c) for c in parsed_chunks]
