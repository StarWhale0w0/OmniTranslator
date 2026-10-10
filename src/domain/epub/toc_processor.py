"""
OmniTranslator Pro - EPUB Table of Contents (TOC) & Navigation Engine
Handles extraction, DOM-based heading mapping, metadata synchronization,
and full reconstruction of toc.ncx, nav.xhtml, book.toc, and visual TOC HTML pages.
"""

import re
import copy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from bs4 import BeautifulSoup, Tag, NavigableString
import ebooklib
from ebooklib import epub
from ebooklib.epub import EpubHtml, EpubItem, EpubNav, EpubNcx, Link, Section, NAMESPACES

from common.logger import setup_logger

logger = setup_logger("TOCProcessor")


class TOCProcessor:
    """Processes, extracts, maps, and applies translated Table of Contents (TOC) to EPUB books."""

    # Heading detection regular expressions
    CHAPTER_PATTERN = re.compile(
        r'^(?:'
        r'제\s*[\d一二三四五六七八九十百천]+\s*[장화권편부회절막]|'
        r'第\s*[\d一二三四五六七八九十百千万零]+\s*[章节回卷幕部篇折]|'
        r'Chapter\s*\d+|'
        r'Pro?logue|Epilogue|'
        r'서장|종장|프롤로그|에필로그|막간|외전|단편|특별편|후기|차례|목차|'
        r'序章|終章|幕間|番外|後記|あとがき|目次|楔子|尾声'
        r')',
        re.IGNORECASE
    )

    TITLE_CLASS_PATTERN = re.compile(
        r'title|heading|chapter|vol|ch-title|vol-title|ch_title|volume_title|head|subject',
        re.IGNORECASE
    )

    @classmethod
    def extract_heading_from_soup(cls, soup: BeautifulSoup, anchor_id: Optional[str] = None) -> Optional[str]:
        """
        Extracts the most relevant chapter title/heading from a chapter's BeautifulSoup DOM.
        Priority:
        1. Explicit element matching anchor_id (id= or name=)
        2. Standard HTML headings: <h1>, <h2>, <h3>, <h4>, <h5>, <h6>
        3. Elements with title/chapter/heading classes or IDs
        4. Paragraphs/Divs matching chapter number / heading regex
        5. First non-empty text element under 100 characters
        """
        if not soup:
            return None

        # 1. Target anchor matching
        if anchor_id:
            target_el = soup.find(id=anchor_id) or soup.find(attrs={"name": anchor_id})
            if target_el:
                txt = cls._clean_extracted_text(target_el.get_text())
                if txt:
                    return txt

        # 2. Standard HTML headings (h1 -> h6)
        for h_tag in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            txt = cls._clean_extracted_text(h_tag.get_text())
            if txt and len(txt) <= 150:
                return txt

        # 3. Class or ID match for title/chapter (leaf or near-leaf elements)
        for tag in soup.find_all(class_=cls.TITLE_CLASS_PATTERN):
            if not tag.find_all(['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                txt = cls._clean_extracted_text(tag.get_text())
                if txt and len(txt) <= 150:
                    return txt

        # 4. Paragraphs or leaf tags matching chapter number pattern
        for p in soup.find_all(['p', 'span', 'strong', 'em', 'a', 'div']):
            # Skip container tags that contain child paragraphs or block elements
            if p.name == 'div' and p.find_all(['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                continue
            txt = cls._clean_extracted_text(p.get_text())
            if txt and cls.CHAPTER_PATTERN.search(txt) and len(txt) <= 120:
                return txt

        # 5. First short non-empty text node (fallback from first 3 paragraphs)
        for p in soup.find_all(['p', 'span']):
            txt = cls._clean_extracted_text(p.get_text())
            if txt and 2 <= len(txt) <= 80:
                return txt

        return None

    @classmethod
    def _clean_extracted_text(cls, text: Optional[str]) -> Optional[str]:
        """Cleans extracted title text, removing excess whitespace and tag residues."""
        if not text:
            return None
        cleaned = re.sub(r'\[\s*TAG\s*_?\s*\d+\s*\]', '', text, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned if cleaned else None

    @classmethod
    def get_item_content_str(cls, item: Any) -> str:
        """Safely retrieves document content as a decoded utf-8 string."""
        raw = item.get_content()
        if isinstance(raw, bytes):
            return raw.decode('utf-8', errors='ignore')
        return str(raw) if raw is not None else ""

    @classmethod
    def build_document_map(cls, book: epub.EpubBook) -> Dict[str, Tuple[EpubHtml, BeautifulSoup]]:
        """
        Builds a lookup map of document chapters in the EPUB:
        Returns: { normalized_href: (EpubHtml_item, BeautifulSoup_parsed_soup) }
        """
        doc_map: Dict[str, Tuple[EpubHtml, BeautifulSoup]] = {}
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            name = item.get_name()
            content = cls.get_item_content_str(item)
            soup = BeautifulSoup(content, 'html.parser')
            
            # Map full name (e.g. EPUB/ch/v01c0001.xhtml)
            doc_map[name] = (item, soup)
            doc_map[name.lstrip('/')] = (item, soup)
            
            # Map filename only (e.g. v01c0001.xhtml)
            base_name = Path(name).name
            if base_name not in doc_map:
                doc_map[base_name] = (item, soup)

        return doc_map

    @classmethod
    def extract_toc_metadata(cls, book: epub.EpubBook) -> List[Dict[str, Any]]:
        """
        Recursively extracts TOC entries from book.toc into a structured list of dicts.
        Suitable for serialization in meta.json.
        """
        entries: List[Dict[str, Any]] = []

        meta_idx = 0

        def _traverse(entry: Any, level: int = 0) -> Optional[Dict[str, Any]]:
            nonlocal meta_idx
            meta_idx += 1
            if isinstance(entry, Link):
                raw_id = getattr(entry, 'uid', None) or getattr(entry, 'id', None)
                if not raw_id:
                    seed = re.sub(r'[^a-zA-Z0-9_]', '_', entry.href or entry.title or '').strip('_')
                    uid_val = f"link_{seed}_{meta_idx}" if seed else f"link_{meta_idx}"
                else:
                    uid_val = str(raw_id).strip()

                return {
                    "type": "link",
                    "id": uid_val,
                    "original_title": entry.title,
                    "translated_title": None,
                    "href": entry.href,
                    "level": level
                }
            elif isinstance(entry, tuple) and len(entry) == 2:
                parent, subitems = entry
                parent_title = parent.title if hasattr(parent, 'title') else str(parent)
                parent_href = getattr(parent, 'href', '')
                raw_parent_id = getattr(parent, 'uid', None) or getattr(parent, 'id', None)
                if not raw_parent_id:
                    seed = re.sub(r'[^a-zA-Z0-9_]', '_', parent_href or parent_title or '').strip('_')
                    parent_id = f"sec_{seed}_{meta_idx}" if seed else f"sec_{meta_idx}"
                else:
                    parent_id = str(raw_parent_id).strip()

                mapped_subs = []
                for sub in subitems:
                    res = _traverse(sub, level + 1)
                    if res:
                        mapped_subs.append(res)
                return {
                    "type": "section",
                    "id": parent_id,
                    "original_title": parent_title,
                    "translated_title": None,
                    "href": parent_href,
                    "level": level,
                    "subitems": mapped_subs
                }
            elif isinstance(entry, Section):
                raw_id = getattr(entry, 'uid', None) or getattr(entry, 'id', None)
                if not raw_id:
                    seed = re.sub(r'[^a-zA-Z0-9_]', '_', getattr(entry, 'href', '') or entry.title or '').strip('_')
                    uid_val = f"sec_{seed}_{meta_idx}" if seed else f"sec_{meta_idx}"
                else:
                    uid_val = str(raw_id).strip()

                return {
                    "type": "section",
                    "id": uid_val,
                    "original_title": entry.title,
                    "translated_title": None,
                    "href": getattr(entry, 'href', ''),
                    "level": level,
                    "subitems": []
                }
            elif isinstance(entry, EpubHtml):
                raw_id = getattr(entry, 'uid', None) or getattr(entry, 'id', None) or entry.get_id()
                if not raw_id:
                    seed = re.sub(r'[^a-zA-Z0-9_]', '_', entry.file_name or entry.title or '').strip('_')
                    uid_val = f"ch_{seed}_{meta_idx}" if seed else f"ch_{meta_idx}"
                else:
                    uid_val = str(raw_id).strip()

                return {
                    "type": "chapter",
                    "id": uid_val,
                    "original_title": entry.title,
                    "translated_title": None,
                    "href": entry.file_name,
                    "level": level
                }
            return None

        if hasattr(book, 'toc') and book.toc:
            for item in book.toc:
                t = _traverse(item, level=0)
                if t:
                    entries.append(t)

        return entries

    @classmethod
    def sync_toc_with_translated_documents(
        cls,
        book: epub.EpubBook,
        toc_entries_cache: Optional[List[Dict[str, Any]]] = None,
        translated_title_map: Optional[Dict[str, str]] = None
    ) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
        """
        Synchronizes book.toc with translated chapter contents:
        1. Looks up translated headings from chapter HTML DOMs.
        2. Applies cached or explicitly mapped titles.
        3. Updates book.toc Link and Section objects in-place.
        4. Returns (updated_toc_entries, href_to_translated_title_map).
        """
        doc_map = cls.build_document_map(book)
        href_to_title: Dict[str, str] = dict(translated_title_map or {})
        orig_to_trans_map: Dict[str, str] = {}

        # If cache exists, populate initial mappings
        if toc_entries_cache:
            def _build_cache_map(items: List[Dict[str, Any]]):
                for it in items:
                    if it.get("translated_title"):
                        if it.get("href"):
                            href_to_title[it["href"]] = it["translated_title"]
                            href_to_title[Path(it["href"].split('#')[0]).name] = it["translated_title"]
                        if it.get("original_title"):
                            orig_to_trans_map[it["original_title"]] = it["translated_title"]
                    if it.get("subitems"):
                        _build_cache_map(it["subitems"])
            _build_cache_map(toc_entries_cache)

        def _resolve_href_title(href: str) -> Optional[str]:
            if not href:
                return None
            if href in href_to_title:
                return href_to_title[href]
            
            file_part = href.split('#')[0]
            anchor = href.split('#')[1] if '#' in href else None
            
            # Check doc_map
            soup_entry = doc_map.get(file_part) or doc_map.get(Path(file_part).name)
            if soup_entry:
                _, soup = soup_entry
                extracted = cls.extract_heading_from_soup(soup, anchor)
                if extracted:
                    href_to_title[href] = extracted
                    href_to_title[file_part] = extracted
                    href_to_title[Path(file_part).name] = extracted
                    return extracted
            return None

        entry_idx = 0

        # Recursive updater for book.toc
        def _update_entry(entry: Any, level: int = 0) -> Tuple[Any, Dict[str, Any]]:
            nonlocal entry_idx
            entry_idx += 1
            if isinstance(entry, Link):
                orig_title = entry.title
                extracted = _resolve_href_title(entry.href)
                if not extracted and orig_title in orig_to_trans_map:
                    extracted = orig_to_trans_map[orig_title]

                final_title = extracted or orig_title
                entry.title = final_title
                if final_title != orig_title:
                    logger.debug(f"TOC Link Updated: '{orig_title}' -> '{final_title}' ({entry.href})")

                raw_uid = getattr(entry, 'uid', None) or getattr(entry, 'id', None)
                if not raw_uid or not str(raw_uid).strip():
                    seed = re.sub(r'[^a-zA-Z0-9_]', '_', entry.href or final_title or '').strip('_')
                    uid_val = f"link_{seed}_{entry_idx}" if seed else f"link_{entry_idx}"
                else:
                    uid_val = str(raw_uid).strip()

                try:
                    entry.uid = uid_val
                except Exception:
                    pass
                try:
                    entry.id = uid_val
                except Exception:
                    pass

                entry_meta = {
                    "type": "link",
                    "id": uid_val,
                    "original_title": orig_title,
                    "translated_title": final_title,
                    "href": entry.href,
                    "level": level
                }
                return entry, entry_meta

            elif isinstance(entry, tuple) and len(entry) == 2:
                parent, subitems = entry
                parent_title = parent.title if hasattr(parent, 'title') else str(parent)
                parent_href = getattr(parent, 'href', '')
                
                raw_parent_id = getattr(parent, 'uid', None) or getattr(parent, 'id', None)
                if not raw_parent_id or not str(raw_parent_id).strip():
                    seed = re.sub(r'[^a-zA-Z0-9_]', '_', parent_href or parent_title or '').strip('_')
                    parent_id = f"sec_{seed}_{entry_idx}" if seed else f"sec_{entry_idx}"
                else:
                    parent_id = str(raw_parent_id).strip()

                if hasattr(parent, 'uid'):
                    try:
                        parent.uid = parent_id
                    except Exception:
                        pass
                if hasattr(parent, 'id'):
                    try:
                        parent.id = parent_id
                    except Exception:
                        pass
                
                extracted_parent = None
                if parent_href:
                    extracted_parent = _resolve_href_title(parent_href)
                if not extracted_parent and parent_title in orig_to_trans_map:
                    extracted_parent = orig_to_trans_map[parent_title]

                final_parent_title = extracted_parent or parent_title
                if hasattr(parent, 'title'):
                    parent.title = final_parent_title
                if final_parent_title != parent_title:
                    logger.debug(f"TOC Section Header Updated: '{parent_title}' -> '{final_parent_title}'")

                updated_sub_entries = []
                sub_metas = []
                for sub in subitems:
                    up_sub, sub_meta = _update_entry(sub, level + 1)
                    updated_sub_entries.append(up_sub)
                    sub_metas.append(sub_meta)

                section_meta = {
                    "type": "section",
                    "id": parent_id,
                    "original_title": parent_title,
                    "translated_title": final_parent_title,
                    "href": parent_href,
                    "level": level,
                    "subitems": sub_metas
                }
                return (parent, updated_sub_entries), section_meta

            elif isinstance(entry, Section):
                orig_title = entry.title
                extracted = None
                if getattr(entry, 'href', ''):
                    extracted = _resolve_href_title(entry.href)
                if not extracted and orig_title in orig_to_trans_map:
                    extracted = orig_to_trans_map[orig_title]

                final_title = extracted or orig_title
                entry.title = final_title

                raw_uid = getattr(entry, 'uid', None) or getattr(entry, 'id', None)
                if not raw_uid or not str(raw_uid).strip():
                    seed = re.sub(r'[^a-zA-Z0-9_]', '_', getattr(entry, 'href', '') or final_title or '').strip('_')
                    uid_val = f"sec_{seed}_{entry_idx}" if seed else f"sec_{entry_idx}"
                else:
                    uid_val = str(raw_uid).strip()

                try:
                    entry.uid = uid_val
                except Exception:
                    pass
                try:
                    entry.id = uid_val
                except Exception:
                    pass

                entry_meta = {
                    "type": "section",
                    "id": uid_val,
                    "original_title": orig_title,
                    "translated_title": final_title,
                    "href": getattr(entry, 'href', ''),
                    "level": level,
                    "subitems": []
                }
                return entry, entry_meta

            elif isinstance(entry, EpubHtml):
                orig_title = entry.title
                extracted = _resolve_href_title(entry.file_name)
                final_title = extracted or orig_title
                entry.title = final_title

                raw_uid = getattr(entry, 'uid', None) or getattr(entry, 'id', None)
                if not raw_uid or not str(raw_uid).strip():
                    seed = re.sub(r'[^a-zA-Z0-9_]', '_', entry.file_name or final_title or '').strip('_')
                    uid_val = f"ch_{seed}_{entry_idx}" if seed else f"ch_{entry_idx}"
                else:
                    uid_val = str(raw_uid).strip()

                try:
                    entry.uid = uid_val
                except Exception:
                    pass
                try:
                    entry.id = uid_val
                except Exception:
                    pass

                entry_meta = {
                    "type": "chapter",
                    "id": uid_val,
                    "original_title": orig_title,
                    "translated_title": final_title,
                    "href": entry.file_name,
                    "level": level
                }
                return entry, entry_meta

            return entry, {"type": "unknown", "original_title": str(entry), "translated_title": str(entry)}

        updated_toc_tree = []
        updated_meta_list = []
        if hasattr(book, 'toc') and book.toc:
            for item in book.toc:
                up_item, meta_item = _update_entry(item, level=0)
                updated_toc_tree.append(up_item)
                updated_meta_list.append(meta_item)

        book.toc = updated_toc_tree
        logger.info(f"TOC synchronization complete: {len(updated_meta_list)} root entries updated.")
        return updated_meta_list, href_to_title

    @classmethod
    def update_visual_toc_pages(cls, book: epub.EpubBook, href_to_title_map: Dict[str, str]) -> int:
        """
        Finds and updates visual HTML Table of Contents pages (e.g. p-toc-001.xhtml or pages with <nav epub:type="toc">).
        Updates <a> links within these pages to display translated Korean titles.
        Returns the number of updated links.
        """
        updated_links_count = 0
        if not href_to_title_map:
            return 0

        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            name = item.get_name().lower()
            content = cls.get_item_content_str(item)
            soup = BeautifulSoup(content, 'html.parser')
            
            # Check if this document contains navigation TOC or is a TOC page
            has_nav_toc = bool(soup.find('nav', attrs={'epub:type': 'toc'})) or 'toc' in name or 'nav' in name
            a_tags = soup.find_all('a', href=True)
            
            if has_nav_toc and a_tags:
                modified = False
                for a in a_tags:
                    href = a['href']
                    target_title = (
                        href_to_title_map.get(href) or
                        href_to_title_map.get(href.split('#')[0]) or
                        href_to_title_map.get(Path(href.split('#')[0]).name)
                    )
                    if target_title:
                        old_txt = a.get_text().strip()
                        if old_txt and old_txt != target_title:
                            a.string = target_title
                            modified = True
                            updated_links_count += 1
                if modified:
                    item.set_content(str(soup).encode('utf-8'))
                    logger.debug(f"Visual TOC page updated: {item.get_name()}")

        return updated_links_count

    @classmethod
    def ensure_navigation_and_metadata(
        cls,
        book: epub.EpubBook,
        translated_book_title: Optional[str] = None,
        language: str = "ko"
    ) -> None:
        """
        Ensures proper Dublin Core metadata (Title, Language) and navigation files:
        1. Updates DC Title to translated Korean title.
        2. Sets DC Language to 'ko'.
        3. Ensures EpubNcx (toc.ncx) and EpubNav (nav.xhtml) items exist in the book.
        """
        # 1. Update DC Title
        if translated_book_title and translated_book_title.strip():
            book.title = translated_book_title.strip()
            # Replace existing DC:title in metadata dict
            if NAMESPACES['DC'] in book.metadata:
                book.metadata[NAMESPACES['DC']]['title'] = [(translated_book_title.strip(), {})]
            else:
                book.add_metadata('DC', 'title', translated_book_title.strip())

        # 2. Update DC Language
        lang_code = language.lower() if language else "ko"
        book.language = lang_code
        if NAMESPACES['DC'] in book.metadata:
            book.metadata[NAMESPACES['DC']]['language'] = [(lang_code, {})]
        else:
            book.add_metadata('DC', 'language', lang_code)

        # 3. Ensure EpubNcx exists
        existing_ncx = [it for it in book.get_items() if isinstance(it, EpubNcx)]
        if not existing_ncx:
            ncx = EpubNcx(uid="ncx", file_name="toc.ncx")
            book.add_item(ncx)
            logger.debug("Added EpubNcx item to book.")
        else:
            for ncx in existing_ncx:
                if not getattr(ncx, 'uid', None):
                    ncx.uid = "ncx"
                if not getattr(ncx, 'id', None):
                    ncx.id = "ncx"

        # 4. Ensure EpubNav exists
        existing_nav = [it for it in book.get_items() if isinstance(it, EpubNav)]
        if not existing_nav:
            nav = EpubNav(uid="nav", file_name="nav.xhtml")
            book.add_item(nav)
            logger.debug("Added EpubNav item to book.")
        else:
            for nav in existing_nav:
                if not getattr(nav, 'uid', None):
                    nav.uid = "nav"
                if not getattr(nav, 'id', None):
                    nav.id = "nav"

    @classmethod
    def extract_or_infer_book_title(
        cls,
        book: epub.EpubBook,
        input_file_path: Optional[Path] = None
    ) -> Optional[str]:
        """
        Extracts or infers translated book title from document chapters (e.g. intro/titlepage)
        or fallback to filename.
        """
        doc_map = cls.build_document_map(book)
        
        # Check first document items (intro, cover, titlepage, index_split_000)
        intro_names = [
            "titlepage.xhtml", "cover.xhtml", "intro.xhtml",
            "index_split_000.html", "index_split_000.xhtml", "part0000.html",
            "p-cover.xhtml", "p-001.xhtml"
        ]
        for intro_key in intro_names:
            soup_entry = doc_map.get(intro_key)
            if soup_entry:
                _, soup = soup_entry
                extracted = cls.extract_heading_from_soup(soup)
                if extracted and len(extracted) < 100:
                    # Clean title book brackets e.g. 《영이편 배우 앱》 -> 영이편 배우 앱
                    cleaned = re.sub(r'^[《【\[\(](.*?)[》】\]\)]$', r'\1', extracted).strip()
                    if cleaned:
                        return cleaned

        # Fallback from filename (e.g. "我不是戏神_나는 드라마의 신이 아니다.epub" -> "나는 드라마의 신이 아니다")
        if input_file_path:
            stem = input_file_path.stem
            if "_" in stem:
                parts = stem.split("_")
                for p in reversed(parts):
                    if re.search(r'[\uac00-\ud7af]', p):
                        return p.strip()
            return stem

        return None
