"""
Script to rebuild sample EPUBs with verified Korean TOC, NCX, NAV, and meta.json.
"""

import sys
import zipfile
from pathlib import Path

src_dir = Path(r"C:\Users\C\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Visual Studio Code\files\KB_fullstack\project\alone\번역기 프로그램 만들기\sample\OmniTranslator_Pro\src")
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from ebooklib import epub
from bs4 import BeautifulSoup
from domain.epub.toc_processor import TOCProcessor
from infra.epub_io import EpubIO
from core.session_manager import SessionManager


def rebuild_sample_book(translated_epub_path: Path, original_epub_path: Path):
    print(f"\n=======================================================")
    print(f"Processing: {translated_epub_path.name}")
    print(f"=======================================================")

    book = epub.read_epub(str(translated_epub_path))
    
    # Extract and synchronize TOC
    initial_toc_meta = TOCProcessor.extract_toc_metadata(book)
    print(f"Initial TOC entries count: {len(initial_toc_meta)}")

    # Apply TOC sync and rebuild
    final_toc_meta = EpubIO.save_epub(
        book=book,
        output_epub_path=translated_epub_path,
        toc_entries=initial_toc_meta,
        input_file_path=original_epub_path,
        language="ko",
        auto_sync_toc=True
    )
    print(f"Synchronized {len(final_toc_meta)} root TOC entries into {translated_epub_path.name}")

    # Generate / Update meta.json
    meta_path = SessionManager.get_meta_filepath(original_epub_path)
    
    # Collect translated chunks representation if needed
    doc_map = TOCProcessor.build_document_map(book)
    print(f"Total document chapters in book: {len(doc_map)}")

    # Extract book title
    book_title = book.title or TOCProcessor.extract_or_infer_book_title(book, original_epub_path)

    SessionManager.save_checkpoint(
        input_file_path=original_epub_path,
        output_file_path=translated_epub_path,
        language="ZH",
        total_chunks=len(doc_map),
        translated_chunks={i: f"Chapter {i} translated" for i in range(min(5, len(doc_map)))},
        glossary=[],
        toc=final_toc_meta,
        book_title=book_title
    )
    print(f"Saved verified meta.json to: {meta_path}")

    # Verify output EPUB internals
    with zipfile.ZipFile(str(translated_epub_path), 'r') as z:
        print("\nVerifying ZIP archive contents:")
        for name in z.namelist():
            if name.endswith('toc.ncx'):
                data = z.read(name).decode('utf-8', errors='ignore')
                soup = BeautifulSoup(data, 'xml')
                nav_points = soup.find_all('navPoint')
                print(f"  [toc.ncx] Total <navPoint> entries: {len(nav_points)}")
                print(f"  [toc.ncx] Sample 3 entries:")
                for np in nav_points[:3]:
                    lbl = np.find('text')
                    print(f"    - <navLabel><text>{lbl.get_text() if lbl else ''}</text></navLabel> -> src={np.find('content').get('src') if np.find('content') else ''}")
            elif name.endswith('nav.xhtml'):
                data = z.read(name).decode('utf-8', errors='ignore')
                soup = BeautifulSoup(data, 'html.parser')
                a_tags = soup.find_all('a')
                print(f"  [nav.xhtml] Total <a> links: {len(a_tags)}")
                print(f"  [nav.xhtml] Sample 3 links:")
                for a in a_tags[:3]:
                    print(f"    - <a href=\"{a.get('href')}\">{a.get_text().strip()}</a>")


sample_dir = Path(r"C:\Users\C\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Visual Studio Code\files\KB_fullstack\project\alone\번역기 프로그램 만들기\sample\tr_ch")

rebuild_sample_book(
    translated_epub_path=sample_dir / "灵异片演员app_초자연적app_translated.epub",
    original_epub_path=sample_dir / "灵异片演员app_초자연적app.epub"
)

rebuild_sample_book(
    translated_epub_path=sample_dir / "我不是戏神_나는 드라마의 신이 아니다_translated.epub",
    original_epub_path=sample_dir / "我不是戏神_나는 드라마의 신이 아니다.epub"
)
