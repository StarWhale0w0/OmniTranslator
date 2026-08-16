"""
OmniTranslator Pro - EPUB DOM Structure-Preserving Chunker
Ported from seamarine: parses BeautifulSoup HTML tags without breaking DOM tags.
"""

import copy
from typing import List
from bs4 import BeautifulSoup, Tag, NavigableString
from domain.chunkers.base_chunker import BaseChunker

class EpubDomChunker(BaseChunker):
    """Chunks HTML content preserving tag hierarchy and markup attributes."""

    def split_into_chunks(self, content: str, max_size: int = 2000) -> List[str]:
        soup = BeautifulSoup(content, 'html.parser')
        body = soup.body if soup.body else soup
        
        chunks = []
        current_chunk = BeautifulSoup("<div></div>", "html.parser").div

        for element in body.contents:
            element_str = str(element)
            if len(str(current_chunk)) + len(element_str) > max_size:
                if current_chunk.contents:
                    chunks.append(str(current_chunk))
                    current_chunk.clear()

                if len(element_str) > max_size:
                    if isinstance(element, NavigableString):
                        text = str(element)
                        for i in range(0, len(text), max_size):
                            new_tag = BeautifulSoup("<div></div>", "html.parser").div
                            new_tag.append(text[i:i+max_size])
                            chunks.append(str(new_tag))
                    elif isinstance(element, Tag):
                        chunks.append(element_str)
                else:
                    current_chunk.append(copy.copy(element))
            else:
                current_chunk.append(copy.copy(element))

        if current_chunk.contents:
            chunks.append(str(current_chunk))

        return chunks if chunks else [content]
