import os
"""
Tests for Table of Contents (TOC) extraction, translation mapping,
metadata synchronization, and EPUB packaging in OmniTranslator Pro.
"""

import sys
import zipfile
import tempfile
import json
from pathlib import Path

# Add src to sys.path
src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

from domain.epub.toc_processor import TOCProcessor
from infra.epub_io import EpubIO
from core.session_manager import SessionManager


def test_heading_extraction():
    """Test heading extraction across various HTML structures."""
    # 1. Standard H2
    soup1 = BeautifulSoup("<html><body><div><h2 class='ch-title'>제1장 새로운 시작</h2><p>본문...</p></div></body></html>", "html.parser")
    assert TOCProcessor.extract_heading_from_soup(soup1) == "제1장 새로운 시작"

    # 2. Anchor target
    soup2 = BeautifulSoup("<html><body><div><p id='calibre_toc_5' class='title'>제5장 위기</p><p>내용...</p></div></body></html>", "html.parser")
    assert TOCProcessor.extract_heading_from_soup(soup2, anchor_id="calibre_toc_5") == "제5장 위기"

    # 3. Class-based title
    soup3 = BeautifulSoup("<html><body><div><div class='volume_title'>제1권 귀환</div></div></body></html>", "html.parser")
    assert TOCProcessor.extract_heading_from_soup(soup3) == "제1권 귀환"

    # 4. Paragraph with chapter pattern
    soup4 = BeautifulSoup("<html><body><div><p>제12화 운명의 날</p><p>그날은 유난히 추웠다.</p></div></body></html>", "html.parser")
    assert TOCProcessor.extract_heading_from_soup(soup4) == "제12화 운명의 날"

    print("✅ test_heading_extraction passed!")


def test_toc_sync_and_epub_rebuild():
    """Test TOC synchronization and EPUB packaging on sample translated book."""
    sample_path = Path(os.getenv("SAMPLE_EPUB_PATH", Path(__file__).resolve().parent.parent.parent / "tr_ch" / "灵异片演员app_초자연적app_translated.epub"))
    if not sample_path.exists():
        print(f"Skipping sample test (file not found: {sample_path})")
        return

    book = epub.read_epub(str(sample_path))
    
    # 1. Initial TOC extraction
    initial_toc_meta = TOCProcessor.extract_toc_metadata(book)
    assert len(initial_toc_meta) > 0
    print(f"Extracted {len(initial_toc_meta)} initial TOC items.")

    # 2. Apply TOC sync
    with tempfile.TemporaryDirectory() as tmpdir:
        out_epub = Path(tmpdir) / "output_korean_toc.epub"
        
        final_toc = EpubIO.save_epub(
            book=book,
            output_epub_path=out_epub,
            toc_entries=initial_toc_meta,
            input_file_path=sample_path,
            language="ko",
            auto_sync_toc=True
        )

        assert out_epub.exists()
        assert len(final_toc) > 0
        
        # Verify book.toc has Korean titles
        assert "제1장" in final_toc[0]["translated_title"]

        # Inspect generated ZIP contents (toc.ncx and nav.xhtml)
        with zipfile.ZipFile(str(out_epub), 'r') as z:
            namelist = z.namelist()
            ncx_files = [f for f in namelist if f.endswith('toc.ncx')]
            nav_files = [f for f in namelist if f.endswith('nav.xhtml')]
            
            assert len(ncx_files) > 0, "toc.ncx must be present in output EPUB"
            assert len(nav_files) > 0, "nav.xhtml must be present in output EPUB"
            
            ncx_content = z.read(ncx_files[0]).decode('utf-8', errors='ignore')
            assert "<text>제1장 앱 오픈</text>" in ncx_content or "제1장" in ncx_content
            
            nav_content = z.read(nav_files[0]).decode('utf-8', errors='ignore')
            assert "제1장" in nav_content

        print("✅ test_toc_sync_and_epub_rebuild passed!")


def test_session_manager_checkpoint_toc():
    """Test saving and loading checkpoint with TOC and book_title in SessionManager."""
    with tempfile.TemporaryDirectory() as tmpdir:
        input_f = Path(tmpdir) / "novel.epub"
        input_f.write_text("dummy", encoding="utf-8")
        output_f = Path(tmpdir) / "novel_translated.epub"

        sample_toc = [
            {"id": "c1", "type": "link", "original_title": "第1章", "translated_title": "제1장", "href": "ch1.xhtml", "level": 0},
            {"id": "c2", "type": "link", "original_title": "第2章", "translated_title": "제2장", "href": "ch2.xhtml", "level": 0}
        ]

        meta_path = SessionManager.save_checkpoint(
            input_file_path=input_f,
            output_file_path=output_f,
            language="ZH",
            total_chunks=10,
            translated_chunks={0: "<div>제1장 번역문</div>", 1: "<div>제2장 번역문</div>"},
            glossary=[{"source": "陈伶", "target": "천링"}],
            toc=sample_toc,
            book_title="테스트 소설"
        )

        assert meta_path.exists()

        loaded = SessionManager.load_checkpoint(input_f)
        assert loaded is not None
        assert loaded["book_title"] == "테스트 소설"
        assert len(loaded["toc"]) == 2
        assert loaded["toc"][0]["translated_title"] == "제1장"

        # Test updating TOC only
        sample_toc[0]["translated_title"] = "제1장 (수정됨)"
        SessionManager.update_toc_in_checkpoint(input_f, sample_toc, book_title="수정된 제목")
        
        reloaded = SessionManager.load_checkpoint(input_f)
        assert reloaded["book_title"] == "수정된 제목"
        assert reloaded["toc"][0]["translated_title"] == "제1장 (수정됨)"

        print("✅ test_session_manager_checkpoint_toc passed!")


if __name__ == "__main__":
    test_heading_extraction()
    test_session_manager_checkpoint_toc()
    test_toc_sync_and_epub_rebuild()
    print("\n🎉 ALL UNIT & INTEGRATION TESTS PASSED SUCCESSFULLY!")
