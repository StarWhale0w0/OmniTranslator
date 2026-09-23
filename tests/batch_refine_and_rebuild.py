"""
Batch post-processing and EPUB rebuilder script to refine dialogue tone & endings across all chapters.
"""

import sys
import json
import zipfile
from pathlib import Path

src_dir = Path(r"C:\Users\C\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Visual Studio Code\files\KB_fullstack\project\alone\번역기 프로그램 만들기\sample\OmniTranslator_Pro\src")
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from domain.postprocess.dialogue_tone_corrector import DialogueToneCorrector
from domain.postprocess.cleaner import TextCleaner
from domain.epub.toc_processor import TOCProcessor
from infra.epub_io import EpubIO
from core.session_manager import SessionManager


def refine_and_rebuild_book(translated_epub_path: Path, original_epub_path: Path):
    print("\n" + "=" * 70)
    print(f"Processing Book: {translated_epub_path.name}")
    print("=" * 70)

    # 1. Update meta.json if present
    meta_path = SessionManager.get_meta_filepath(original_epub_path)
    if meta_path.exists():
        with open(meta_path, 'r', encoding='utf-8') as f:
            meta_data = json.load(f)

        translated_chunks = meta_data.get("translated_chunks", {})
        refined_chunks_count = 0
        for chunk_id, chunk_text in translated_chunks.items():
            if chunk_text:
                refined_text = DialogueToneCorrector.refine_dialogue_text(chunk_text)
                if refined_text != chunk_text:
                    translated_chunks[chunk_id] = refined_text
                    refined_chunks_count += 1

        meta_data["translated_chunks"] = translated_chunks
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta_data, f, ensure_ascii=False, indent=2)
        print(f"Updated meta.json: {refined_chunks_count} chunks modified.")

    # 2. Load and refine all documents in EPUB
    book = epub.read_epub(str(translated_epub_path))
    doc_items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    total_docs = len(doc_items)
    modified_docs_count = 0
    total_dialogues_refined = 0

    for idx, item in enumerate(doc_items, start=1):
        raw_content = item.get_content()
        content_str = raw_content.decode('utf-8', errors='ignore') if isinstance(raw_content, bytes) else str(raw_content)

        # Apply dialogue tone corrector to HTML content
        refined_content = DialogueToneCorrector.refine_dialogue_text(content_str)
        # Also clean any stray currency '첸' or artifacts
        refined_content = TextCleaner.clean_text(refined_content)

        if refined_content != content_str:
            item.set_content(refined_content.encode('utf-8'))
            modified_docs_count += 1

    print(f"Refined dialogues across {modified_docs_count}/{total_docs} chapters.")

    # 3. Save / Rebuild EPUB with TOC synchronization
    final_toc_meta = EpubIO.save_epub(
        book=book,
        output_epub_path=translated_epub_path,
        input_file_path=original_epub_path,
        language="ko",
        auto_sync_toc=True
    )
    print(f"Rebuilt and saved EPUB to: {translated_epub_path.name}")

    # 4. Verify inside ZIP
    with zipfile.ZipFile(str(translated_epub_path), 'r') as z:
        for name in z.namelist():
            if name.endswith('toc.ncx'):
                data = z.read(name).decode('utf-8', errors='ignore')
                soup = BeautifulSoup(data, 'xml')
                print(f"Verified {name}: {len(soup.find_all('navPoint'))} <navPoint> entries in NCX.")
            elif name.endswith('nav.xhtml'):
                data = z.read(name).decode('utf-8', errors='ignore')
                soup = BeautifulSoup(data, 'html.parser')
                print(f"Verified {name}: {len(soup.find_all('a'))} links in NAV.")


sample_dir = Path(r"C:\Users\C\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Visual Studio Code\files\KB_fullstack\project\alone\번역기 프로그램 만들기\sample\tr_ch")

refine_and_rebuild_book(
    translated_epub_path=sample_dir / "灵异片演员app_초자연적app_translated.epub",
    original_epub_path=sample_dir / "灵异片演员app_초자연적app.epub"
)

refine_and_rebuild_book(
    translated_epub_path=sample_dir / "我不是戏神_나는 드라마의 신이 아니다_translated.epub",
    original_epub_path=sample_dir / "我不是戏神_나는 드라마의 신이 아니다.epub"
)

print("\n🎉 ALL BOOKS DIALOGUE REFINED AND REBUILT SUCCESSFULLY!")
