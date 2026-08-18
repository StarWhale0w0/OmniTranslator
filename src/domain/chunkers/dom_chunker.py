"""
OmniTranslator Pro - EPUB DOM Structure-Preserving Chunker
Chunks HTML/EPUB DOM hierarchy recursively while preserving tags and media elements.
"""

import copy
from typing import Any, List
from bs4 import BeautifulSoup, Tag, NavigableString
from domain.chunkers.base_chunker import BaseChunker

class DomChunker(BaseChunker):
    """Chunks HTML content preserving tag hierarchy, attributes, and media tags."""

    @classmethod
    def _is_empty_node(cls, node: Any) -> bool:
        """Checks if a DOM node has neither meaningful text nor media tags."""
        if isinstance(node, NavigableString):
            return len(str(node).strip()) == 0
        if isinstance(node, Tag):
            return cls.is_empty_chunk(str(node))
        return True

    @classmethod
    def _split_oversized_tag(cls, tag: Tag, max_chars: int) -> List[Tag]:
        """
        Recursively splits an oversized Tag into smaller Tags of the same type/structure,
        ensuring child tags or strings are properly distributed without exceeding max_chars.
        """
        tag_str = str(tag)
        if len(tag_str) <= max_chars:
            return [tag]

        # If tag has no children
        if not tag.contents:
            return [tag]

        result_chunks: List[Tag] = []
        current_wrapper = tag.__copy__()
        current_wrapper.clear()

        for child in list(tag.contents):
            # Skip pure whitespace strings
            if isinstance(child, NavigableString) and not str(child).strip():
                continue

            child_str = str(child)

            # If a single child tag is itself oversized, split it recursively
            if len(child_str) > max_chars:
                if current_wrapper.contents:
                    result_chunks.append(copy.copy(current_wrapper))
                    current_wrapper.clear()

                if isinstance(child, Tag):
                    child_subtags = cls._split_oversized_tag(child, max_chars)
                    for c_sub in child_subtags:
                        wrapper_for_child = tag.__copy__()
                        wrapper_for_child.clear()
                        wrapper_for_child.append(c_sub)
                        result_chunks.append(wrapper_for_child)
                elif isinstance(child, NavigableString):
                    text = str(child)
                    for i in range(0, len(text), max_chars):
                        wrapper_for_text = tag.__copy__()
                        wrapper_for_text.clear()
                        wrapper_for_text.append(text[i:i + max_chars])
                        result_chunks.append(wrapper_for_text)
                else:
                    wrapper_for_other = tag.__copy__()
                    wrapper_for_other.clear()
                    wrapper_for_other.append(child)
                    result_chunks.append(wrapper_for_other)
            else:
                # Child fits in a chunk
                if len(str(current_wrapper)) + len(child_str) > max_chars:
                    if current_wrapper.contents:
                        result_chunks.append(copy.copy(current_wrapper))
                        current_wrapper.clear()
                current_wrapper.append(child)

        if current_wrapper.contents:
            result_chunks.append(copy.copy(current_wrapper))

        # Filter out empty wrapper chunks that have 0 text and 0 media
        filtered = [c for c in result_chunks if not cls.is_empty_chunk(str(c)) or cls.has_media_tags(str(c))]
        return filtered if filtered else [tag]

    @classmethod
    def chunk_body_preserving_structure(cls, body: BeautifulSoup, max_chars: int = 2000) -> List[Any]:
        """
        Chunks EPUB/HTML body elements while preserving tag structure.
        Recursively splits deeply nested elements to avoid oversized chunks or empty wrapper tags.
        """
        if not body:
            return []

        chunks: List[Any] = []
        current_chunk = BeautifulSoup("<div></div>", "html.parser").div

        elements = list(body.contents) if hasattr(body, 'contents') else [body]

        for element in elements:
            # Skip empty whitespace strings outside tags
            if isinstance(element, NavigableString) and not str(element).strip():
                continue

            element_str = str(element)

            # If element is oversized, process with recursive splitting
            if len(element_str) > max_chars:
                if current_chunk.contents:
                    chunks.append(copy.copy(current_chunk))
                    current_chunk.clear()

                if isinstance(element, Tag):
                    subtags = cls._split_oversized_tag(element, max_chars)
                    for sub in subtags:
                        if not cls.is_empty_chunk(str(sub)) or cls.has_media_tags(str(sub)):
                            chunks.append(sub)
                elif isinstance(element, NavigableString):
                    text = str(element)
                    for i in range(0, len(text), max_chars):
                        new_tag = BeautifulSoup("<div></div>", "html.parser").div
                        new_tag.append(text[i:i + max_chars])
                        chunks.append(new_tag)
                else:
                    chunks.append(element)
            else:
                # Element fits
                if len(str(current_chunk)) + len(element_str) > max_chars:
                    if current_chunk.contents:
                        chunks.append(copy.copy(current_chunk))
                        current_chunk.clear()
                current_chunk.append(element)

        if current_chunk.contents:
            chunks.append(copy.copy(current_chunk))

        # Filter chunks that are completely empty (no text and no media)
        valid_chunks = []
        for c in chunks:
            c_str = str(c)
            if cls.has_meaningful_text(c_str) or cls.has_media_tags(c_str):
                valid_chunks.append(c)

        return valid_chunks

    def split_into_chunks(self, content: str, max_size: int = 2000) -> List[str]:
        if not content:
            return []
        soup = BeautifulSoup(content, 'html.parser')
        body = soup.body if soup.body else soup
        parsed_chunks = self.chunk_body_preserving_structure(body, max_chars=max_size)
        return [str(c) for c in parsed_chunks]

# Backwards compatibility alias
EpubDomChunker = DomChunker
