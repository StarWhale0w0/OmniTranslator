"""
OmniTranslator Pro - EPUB File I/O Engine
Handles EPUB reading, chapter extraction, DOM reconstruction,
and automated Table of Contents (TOC), NCX, NAV, and metadata synchronization.

[v2 패치] get_epub_chapters: ebooklib이 인식하지 못하는 EPUB 표준 외부 경로
(루트 레벨 JUAN*.html, 별도 OEBPS 경로 chapter*.html 등)를 ZIP에서 직접
스캔하여 누락 없이 EpubHtml 객체로 변환하는 폴백 로직 추가.
포괄적 정규식으로 chapter_N, JUAN_N, preface, part, volume, intro, \\d+.html 등
모든 본문 HTML 패턴을 커버.
"""

import copy
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Tuple, List, Optional, Dict, Set
from bs4 import BeautifulSoup
import ebooklib
from ebooklib import epub
from ebooklib.epub import EpubHtml
from domain.epub.toc_processor import TOCProcessor
from common.logger import setup_logger

logger = setup_logger("EpubIO")

# ---------------------------------------------------------------------------
# 포괄적 본문 HTML 파일명 패턴 (대소문자 무관)
# 커버: chapter_NNN, JUAN_N, cha_NNN, vol_NNN, preface, epilogue, prologue,
#        part_NNN, volume_NNN, intro, NNN.html(숫자전용), etc.
# ---------------------------------------------------------------------------
_BODY_HTML_PATTERN = re.compile(
    r"""
    (?:
        chapter_?\d+         |   # chapter_1464, chapter1464
        cha_?\d+             |   # Cha_1001, cha1001
        juan_?\d+            |   # JUAN1, juan_01
        vol(?:ume)?_?\d+     |   # vol_01, volume_01
        part_?\d+            |   # part_01, part1
        \d+                  |   # 순수 숫자 파일명
        preface              |   # 머리말
        foreword             |
        afterword            |
        epilogue             |
        prologue             |
        intro                |
        appendix_?\d*        |
        extra_?\d*           |   # extra, extra_01
        fanwai_?\d*          |   # 번외 (번역 전 원문 표기)
        bonus_?\d*
    )
    \.(?:html?|xhtml)$
    """,
    re.IGNORECASE | re.VERBOSE,
)


class EpubIO:
    """Reads and reconstructs EPUB ebooks with complete TOC and Navigation synchronization."""

    @classmethod
    def get_epub_chapters(cls, epub_path: Path) -> Tuple[Any, List[EpubHtml]]:
        """
        Reads EPUB book and extracts all EpubHtml chapter items.

        [v2] 두 단계로 동작:
        1. ebooklib 표준 파싱으로 ITEM_DOCUMENT 항목 전체 수집.
        2. ZIP을 직접 스캔하여 ebooklib이 놓친 HTML 파일(루트 레벨 JUAN*.html,
           별도 OEBPS 경로 등)을 _BODY_HTML_PATTERN으로 필터 후 폴백 EpubHtml 보충.
           이미 수집된 항목은 중복 추가하지 않음.
        """
        book = epub.read_epub(str(epub_path))

        # 1단계: ebooklib 표준 수집
        chapter_items: List[EpubHtml] = [
            item for item in book.get_items() if isinstance(item, EpubHtml)
        ]
        known_names: Set[str] = {item.get_name() for item in chapter_items}

        # 2단계: ZIP 직접 스캔으로 누락 파일 보충
        try:
            with zipfile.ZipFile(str(epub_path), "r") as zf:
                all_zip_entries = zf.namelist()

                for zip_name in all_zip_entries:
                    base = PurePosixPath(zip_name).name  # 파일명만 추출
                    if not _BODY_HTML_PATTERN.match(base):
                        continue  # 본문 HTML 패턴과 불일치 → 건너뜀

                    if zip_name in known_names:
                        continue  # 이미 ebooklib이 수집한 항목 → 중복 방지

                    # ZIP에서 직접 내용 읽기
                    try:
                        raw_bytes = zf.read(zip_name)
                    except Exception as e:
                        logger.warning(f"ZIP fallback read failed for '{zip_name}': {e}")
                        continue

                    # EpubHtml 객체 수동 생성
                    item = EpubHtml(
                        uid=f"fallback_{re.sub(r'[^a-zA-Z0-9_]', '_', zip_name)}",
                        file_name=zip_name,
                        media_type="application/xhtml+xml",
                    )
                    item.set_content(raw_bytes)
                    chapter_items.append(item)
                    known_names.add(zip_name)
                    logger.info(
                        f"[ZIP Fallback] 누락 HTML 보충: '{zip_name}' "
                        f"({len(raw_bytes)} bytes)"
                    )

        except Exception as e:
            logger.warning(f"ZIP fallback scan failed: {e}")

        logger.info(
            f"get_epub_chapters: 총 {len(chapter_items)}개 챕터 항목 "
            f"(ebooklib + ZIP fallback 포함)"
        )
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
