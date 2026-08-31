"""
OmniTranslator Pro - EPUB File I/O Engine
Handles EPUB reading, chapter extraction, DOM reconstruction,
and automated Table of Contents (TOC), NCX, NAV, and metadata synchronization.
"""

import copy
from pathlib import Path
from typing import Any, Tuple, List, Optional, Dict
from bs4 import BeautifulSoup
import ebooklib
from ebooklib import epub
from ebooklib.epub import EpubHtml
from domain.epub.toc_processor import TOCProcessor
from common.logger import setup_logger

logger = setup_logger("EpubIO")


class EpubIO:
    """Reads and reconstructs EPUB ebooks with complete TOC and Navigation synchronization."""

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
            content = TOCProcessor.get_item_content_str(ch)
            soup = BeautifulSoup(content, 'html.parser')
            cleaned = soup.get_text(separator='\n').strip()
            if cleaned:
                text_parts.append(cleaned)
        return "\n\n".join(text_parts)

    @classmethod
    def extract_toc_metadata(cls, book: Any) -> List[Dict[str, Any]]:
        """Extracts initial TOC structure from book."""
        return TOCProcessor.extract_toc_metadata(book)

    @classmethod
    def apply_translated_toc(
        cls,
        book: Any,
        toc_entries_cache: Optional[List[Dict[str, Any]]] = None,
        translated_title_map: Optional[Dict[str, str]] = None,
        book_title: Optional[str] = None,
        input_file_path: Optional[Path] = None,
        language: str = "ko"
    ) -> List[Dict[str, Any]]:
        """
        Synchronizes book.toc, visual TOC pages, toc.ncx, nav.xhtml, and DC metadata
        with translated chapter titles.
        """
        # 1. Sync book.toc Links & Sections with translated HTML DOMs
        updated_toc_meta, href_map = TOCProcessor.sync_toc_with_translated_documents(
            book=book,
            toc_entries_cache=toc_entries_cache,
            translated_title_map=translated_title_map
        )

        # 2. Infer or apply book title
        final_book_title = book_title
        if not final_book_title:
            final_book_title = TOCProcessor.extract_or_infer_book_title(book, input_file_path)

        # 3. Ensure Dublin Core metadata & navigation items (toc.ncx, nav.xhtml)
        TOCProcessor.ensure_navigation_and_metadata(
            book=book,
            translated_book_title=final_book_title,
            language=language
        )

        # 4. Update visual HTML TOC pages if present
        TOCProcessor.update_visual_toc_pages(book, href_map)

        return updated_toc_meta

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
    def save_epub(
        cls,
        book: Any,
        output_epub_path: Path,
        toc_entries: Optional[List[Dict[str, Any]]] = None,
        translated_title_map: Optional[Dict[str, str]] = None,
        book_title: Optional[str] = None,
        input_file_path: Optional[Path] = None,
        language: str = "ko",
        auto_sync_toc: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Applies translated TOC and writes reconstructed EPUB book to output path.
        Returns the finalized TOC metadata entries list.
        """
        output_epub_path.parent.mkdir(parents=True, exist_ok=True)
        
        final_toc_meta = []
        if auto_sync_toc:
            final_toc_meta = cls.apply_translated_toc(
                book=book,
                toc_entries_cache=toc_entries,
                translated_title_map=translated_title_map,
                book_title=book_title,
                input_file_path=input_file_path,
                language=language
            )

        epub.write_epub(str(output_epub_path), book)
        logger.info(f"EPUB with synchronized Korean TOC saved successfully to {output_epub_path}")
        return final_toc_meta
