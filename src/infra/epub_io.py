"""
OmniTranslator Pro - EPUB File I/O Engine
"""

from pathlib import Path
from typing import List
from bs4 import BeautifulSoup
import ebooklib
from ebooklib import epub
from common.logger import setup_logger

logger = setup_logger("EpubIO")

class EpubIO:
    """Reads and reconstructs EPUB ebooks preserving TOC and CSS resources."""

    @classmethod
    def extract_epub_html_content(cls, epub_path: Path) -> str:
        book = epub.read_epub(str(epub_path))
        html_contents = []
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                html_contents.append(item.get_content().decode('utf-8', errors='ignore'))
        return "\n".join(html_contents)

    @classmethod
    def rebuild_epub(cls, source_epub_path: Path, output_epub_path: Path, translated_chunks: List[str]) -> None:
        book = epub.read_epub(str(source_epub_path))
        doc_items = [item for item in book.get_items() if item.get_type() == ebooklib.ITEM_DOCUMENT]

        chunk_idx = 0
        for item in doc_items:
            if chunk_idx < len(translated_chunks):
                item.set_content(translated_chunks[chunk_idx].encode('utf-8'))
                chunk_idx += 1

        output_epub_path.parent.mkdir(parents=True, exist_ok=True)
        epub.write_epub(str(output_epub_path), book)
        logger.info(f"Rebuilt EPUB saved to {output_epub_path}")
