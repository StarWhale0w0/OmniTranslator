"""
OmniTranslator Pro - EPUB File I/O Engine
Ported directly from seamarine-lightnovel-translator.
"""

import copy
from pathlib import Path
from typing import Any, Tuple, List, Optional, Dict
from bs4 import BeautifulSoup
import ebooklib
from ebooklib import epub
from ebooklib.epub import EpubHtml
from common.logger import setup_logger

logger = setup_logger("EpubIO")

class EpubIO:
    """Reads and reconstructs EPUB ebooks using seamarine's verified EpubHtml chapter workflow."""

    @classmethod
    def get_epub_chapters(cls, epub_path: Path) -> Tuple[Any, List[EpubHtml]]:
        """Reads EPUB book and extracts all EpubHtml chapter items."""
        book = epub.read_epub(str(epub_path))
        chapter_items = [item for item in book.get_items() if isinstance(item, EpubHtml)]
        return book, chapter_items

    @classmethod
    def extract_plain_text(cls, epub_path: Path) -> str:
        """Extracts clean stripped plain text from all document chapters in the EPUB."""
        book, chapters = cls.get_epub_chapters(epub_path)
        text_parts = []
        for ch in chapters:
            content = ch.get_content().decode('utf-8', errors='ignore')
            soup = BeautifulSoup(content, 'html.parser')
            cleaned = soup.get_text(separator='\n').strip()
            if cleaned:
                text_parts.append(cleaned)
        return "\n\n".join(text_parts)

    @classmethod
    def rebuild_chapter_html(cls, original_html: str, translated_chunks: List[str]) -> str:
        """Reconstructs chapter HTML DOM preserving head and appending translated body contents."""
        soup = BeautifulSoup(original_html, 'html.parser')
        head = soup.head
        new_soup = BeautifulSoup("", "html.parser")
        html_tag = new_soup.new_tag("html")
        new_soup.append(html_tag)
        if head:
            html_tag.append(copy.copy(head))
        new_body = new_soup.new_tag("body")
        for translated_chunk in translated_chunks:
            chunk_soup = BeautifulSoup(translated_chunk, "html.parser")
            for content in chunk_soup.contents:
                new_body.append(content)
        html_tag.append(new_body)
        return str(new_soup)

    @classmethod
    def save_epub(cls, book: Any, output_epub_path: Path) -> None:
        """Writes reconstructed EPUB book to output path."""
        output_epub_path.parent.mkdir(parents=True, exist_ok=True)
        epub.write_epub(str(output_epub_path), book)
        logger.info(f"EPUB saved successfully to {output_epub_path}")
