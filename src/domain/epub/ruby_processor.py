"""
OmniTranslator Pro - Ruby Tag Processor
Cleans and flattens EPUB ruby tags (<ruby>, <rt>, <rp>) for Korean reading optimization.
Prevents text splitting, vertical misalignment, and irregular line-spacing in Korean e-readers.
"""

import re
from typing import Optional, List, Tuple, Any
from bs4 import BeautifulSoup, Tag, NavigableString
import ebooklib
from common.logger import setup_logger

logger = setup_logger("RubyProcessor")


class RubyProcessor:
    """
    Handles preprocessing and postprocessing of <ruby> tags:
    1. Flattens simple phonetic pronunciation furigana/pinyin to base text.
    2. Converts meaningful annotation/special readings into 'Base(Ruby)' inline text.
    3. Eliminates orphan <rt> and <rp> tags.
    4. Injects reset CSS styles into EPUB stylesheets.
    """

    # Kanji character range (CJK Unified Ideographs & Extension A/Compatibility)
    KANJI_PATTERN = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]')

    # Pure Hiragana pattern
    HIRAGANA_PATTERN = re.compile(r'^[\u3040-\u309f\s]+$')

    # Pure Katakana pattern
    KATAKANA_PATTERN = re.compile(r'^[\u30a0-\u30ff\s]+$')

    # Pinyin / Latin reading pattern (with tone marks and common punctuation)
    PINYIN_PATTERN = re.compile(r'^[a-zA-Z\u00c0-\u024F0-9\s\.,\'"\-~`·]+$')

    # Hangul pattern (Korean)
    HANGUL_PATTERN = re.compile(r'[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f]')

    # CSS reset injection string for Korean EPUB viewers
    RUBY_CSS_RESET = (
        "\n/* OmniTranslator Ruby Tag Reset for Korean EPUB */\n"
        "ruby {\n"
        "    font-size: inherit;\n"
        "}\n"
        "rt {\n"
        "    font-size: 0.8em;\n"
        "    margin-left: 2px;\n"
        "}\n"
    )

    @classmethod
    def is_simple_pronunciation(cls, base_text: str, rt_text: str) -> bool:
        """
        Determines whether the <rt> ruby text is merely a phonetic reading guide
        (which should be removed for Korean translation/reading), or a meaningful
        annotation/special reading (which should be preserved as 'Base(Ruby)').

        Rules:
        - If rt is empty or identical to base -> True (redundant, drop rt)
        - If base has Kanji and rt is pure Hiragana -> True (standard Japanese furigana, drop rt)
        - If base has Kanji and rt is Latin/Pinyin -> True (standard Chinese pinyin, drop rt)
        - If rt is Katakana (e.g. 長距離拡散式女神の慈悲 -> パナケイア・ブレス, 地球 -> テラ) -> False (special reading, preserve as Base(Ruby))
        - If rt contains English words / special notation -> False (preserve as Base(Ruby))
        - If text is already in Korean / Hangul -> False (preserve as Base(Ruby) or inline)
        """
        b = base_text.strip()
        r = rt_text.strip()

        if not r:
            return True

        if b == r:
            return True

        # Check if base contains CJK Kanji characters
        has_kanji = bool(cls.KANJI_PATTERN.search(b))

        # Japanese standard furigana: Kanji base + pure Hiragana rt
        if has_kanji and cls.HIRAGANA_PATTERN.match(r):
            return True

        # Chinese standard pinyin: Kanji base + Latin pinyin rt
        if has_kanji and cls.PINYIN_PATTERN.match(r):
            # If it's a short pinyin string without meaning
            return True

        # If rt is pure Katakana while base is Kanji or different, often a special reading (e.g., テラ, スキル)
        if cls.KATAKANA_PATTERN.match(r):
            return False

        # If rt contains Hangul (already translated or Korean commentary)
        if cls.HANGUL_PATTERN.search(r):
            return False

        # If base is not Kanji (e.g. Kana, English) and rt is Hiragana, usually pronunciation or annotation
        if not has_kanji and cls.HIRAGANA_PATTERN.match(r):
            return True

        return False

    @classmethod
    def _parse_ruby_element(cls, ruby_tag: Tag) -> str:
        """
        Extracts base text and rt annotations from a <ruby> DOM node.
        Handles paired <rb>/<rt>, multiple <rt> tags, and nested markup.
        """
        # 1. Remove all <rp> tags completely
        for rp in ruby_tag.find_all('rp'):
            rp.decompose()

        # 2. Check for structured <rb> and <rt> pairs
        rbs = ruby_tag.find_all('rb')
        rts = ruby_tag.find_all('rt')

        # Case A: Explicit 1-to-1 matching <rb> and <rt> pairs
        if rbs and len(rbs) == len(rts) and len(rbs) > 0:
            result_parts = []
            for rb, rt in zip(rbs, rts):
                rb_text = rb.get_text()
                rt_text = rt.get_text()
                if cls.is_simple_pronunciation(rb_text, rt_text):
                    result_parts.append(rb_text)
                else:
                    result_parts.append(f"{rb_text}({rt_text})" if rt_text else rb_text)
            return "".join(result_parts)

        # Case B: Multiple <rt> tags without explicit <rb>
        # e.g., <ruby>焦<rt>こげ</rt>茶<rt>ちや</rt>色<rt>いろ</rt></ruby>
        # or <ruby>漢<rt>かん</rt>字<rt>じ</rt></ruby>
        # Iterate over child contents in sequential order
        child_elements = list(ruby_tag.contents)
        has_interleaved_rt = any(isinstance(c, Tag) and c.name == 'rt' for c in child_elements)

        if has_interleaved_rt and len(rts) > 0:
            paired_segments: List[Tuple[str, str]] = []
            curr_base = []
            for child in child_elements:
                if isinstance(child, Tag) and child.name == 'rt':
                    rt_val = child.get_text()
                    base_val = "".join(curr_base)
                    paired_segments.append((base_val, rt_val))
                    curr_base = []
                elif isinstance(child, Tag) and child.name == 'rb':
                    curr_base.append(child.get_text())
                elif isinstance(child, Tag):
                    curr_base.append(child.get_text())
                elif isinstance(child, NavigableString):
                    curr_base.append(str(child))

            trailing_base = "".join(curr_base)

            # If we successfully parsed interleaved segments
            if paired_segments:
                seg_results = []
                for b_seg, r_seg in paired_segments:
                    # Clean newline/whitespace artifacts between characters in ruby
                    b_seg_clean = re.sub(r'\s+', '', b_seg) if cls.KANJI_PATTERN.search(b_seg) else b_seg.strip()
                    r_seg_clean = r_seg.strip()
                    if cls.is_simple_pronunciation(b_seg_clean, r_seg_clean):
                        seg_results.append(b_seg_clean)
                    else:
                        seg_results.append(f"{b_seg_clean}({r_seg_clean})" if r_seg_clean else b_seg_clean)
                if trailing_base:
                    seg_results.append(trailing_base)
                return "".join(seg_results)

        # Case C: Standard single <ruby>Base<rt>Reading</rt></ruby>
        rt_text_all = "".join(rt.get_text() for rt in rts).strip()
        # Remove rt tags temporarily to extract pure base text
        for rt in rts:
            rt.decompose()

        base_text = ruby_tag.get_text()
        # Clean intra-ruby line breaks (e.g. <ruby>焦\n 茶\n 色</ruby>)
        if cls.KANJI_PATTERN.search(base_text):
            base_text = re.sub(r'[\r\n\t]+', '', base_text)

        if cls.is_simple_pronunciation(base_text, rt_text_all):
            return base_text
        else:
            return f"{base_text}({rt_text_all})" if rt_text_all else base_text

    @classmethod
    def flatten_ruby_html(cls, html_content: str) -> str:
        """
        Parses HTML and flattens all <ruby>, <rt>, and <rp> tags into clean inline text.
        Also removes orphan <rt> and <rp> tags.
        """
        if not html_content or '<ruby' not in html_content.lower() and '<rt' not in html_content.lower():
            return html_content

        try:
            soup = BeautifulSoup(html_content, 'html.parser')

            # 1. Process all <ruby> tags
            rubies = soup.find_all('ruby')
            for ruby in rubies:
                replacement_text = cls._parse_ruby_element(ruby)
                ruby.replace_with(NavigableString(replacement_text))

            # 2. Cleanup orphan <rp> tags
            for orphan_rp in soup.find_all('rp'):
                orphan_rp.decompose()

            # 3. Cleanup orphan <rt> tags
            for orphan_rt in soup.find_all('rt'):
                rt_text = orphan_rt.get_text().strip()
                if rt_text:
                    orphan_rt.replace_with(NavigableString(f"({rt_text})"))
                else:
                    orphan_rt.decompose()

            return str(soup)

        except Exception as e:
            logger.warning(f"flatten_ruby_html BeautifulSoup error: {e}. Falling back to regex.")
            return cls._flatten_ruby_regex(html_content)

    @classmethod
    def _flatten_ruby_regex(cls, html_content: str) -> str:
        """Fallback regex-based ruby flattener if BeautifulSoup fails."""
        # 1. Remove all <rp>...</rp> tags
        text = re.sub(r'<rp[^>]*>.*?</rp>', '', html_content, flags=re.DOTALL | re.IGNORECASE)

        # 2. Match standard <ruby>(base)<rt>(reading)</rt></ruby>
        def ruby_replace(m):
            inner = m.group(1)
            # Find all <rt> tags in inner
            rts = re.findall(r'<rt[^>]*>(.*?)</rt>', inner, flags=re.DOTALL | re.IGNORECASE)
            base = re.sub(r'<rt[^>]*>.*?</rt>', '', inner, flags=re.DOTALL | re.IGNORECASE)
            base_clean = re.sub(r'<[^>]+>', '', base).strip()
            rt_clean = "".join(re.sub(r'<[^>]+>', '', r) for r in rts).strip()
            if cls.is_simple_pronunciation(base_clean, rt_clean):
                return base_clean
            return f"{base_clean}({rt_clean})" if rt_clean else base_clean

        text = re.sub(r'<ruby[^>]*>(.*?)</ruby>', ruby_replace, text, flags=re.DOTALL | re.IGNORECASE)

        # 3. Remove orphan <rt> and <rp> tags
        text = re.sub(r'</?rp[^>]*>', '', text, flags=re.IGNORECASE)
        text = re.sub(r'<rt[^>]*>(.*?)</rt>', r'(\1)', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'</?rt[^>]*>', '', text, flags=re.IGNORECASE)

        return text

    @classmethod
    def inject_ruby_css_to_book(cls, book: Any) -> bool:
        """
        Injects ruby reset styles into all CSS stylesheets in the EPUB book.
        If no CSS stylesheet exists, creates a new one and attaches it to the book.
        """
        if not book:
            return False

        injected_count = 0
        try:
            # 1. Find all stylesheet items in book
            css_items = [
                item for item in book.get_items()
                if getattr(item, 'media_type', '') == 'text/css'
                or (getattr(item, 'file_name', '') and item.file_name.lower().endswith('.css'))
            ]

            marker = "/* OmniTranslator Ruby Tag Reset for Korean EPUB */"

            for item in css_items:
                raw = item.get_content()
                content_str = raw.decode('utf-8', errors='ignore') if isinstance(raw, bytes) else str(raw)
                if marker not in content_str:
                    updated_css = content_str + cls.RUBY_CSS_RESET
                    item.set_content(updated_css.encode('utf-8'))
                    injected_count += 1
                    logger.info(f"Injected ruby CSS reset into existing stylesheet: {item.file_name}")

            # 2. If no existing stylesheet was found, create a new fallback stylesheet
            if not css_items:
                style_item = ebooklib.epub.EpubItem(
                    uid="omni_ruby_reset_css",
                    file_name="Styles/ruby_reset.css",
                    media_type="text/css",
                    content=cls.RUBY_CSS_RESET.strip().encode('utf-8')
                )
                book.add_item(style_item)
                logger.info("Created new stylesheet 'Styles/ruby_reset.css' with ruby reset styles.")
                injected_count += 1

            return injected_count > 0

        except Exception as e:
            logger.warning(f"Failed to inject ruby CSS styles: {e}")
            return False
