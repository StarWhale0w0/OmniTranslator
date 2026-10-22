"""
OmniTranslator Pro - Tag Masker Module
Masks HTML/XML/Media tags into [TAG_N] placeholders and restores them post-translation.
Provides robust protection against tag mutation, corruption, and fragmentation.
"""

import re
import html
import copy
from typing import Tuple, Dict, Optional, List, Callable, Any
from bs4 import BeautifulSoup, NavigableString, Tag

class TagMasker:
    """Isolates HTML/XML/Media tags as [TAG_N] placeholders to protect them from LLM modification/censorship."""

    TAG_REGEX = re.compile(r'<[^>]+>', re.DOTALL)
    PLACEHOLDER_REGEX = re.compile(
        r'(?:'
        r'[\[［]\s*(?:TAG|태그)\s*[_\-\s]*[0-9][0-9\s]*\s*[\]］]|'
        r'_{1,2}TAG\s*[_\-\s]*[0-9][0-9\s]*_{1,2}|'
        r'(?<![a-zA-Z0-9_])TAG\s*[_\-\s]*[0-9]+\s*[\]］]|'
        r'[\[［]\s*TAG\s*[_\-\s]*[0-9]+'
        r')',
        re.IGNORECASE
    )
    IGNORED_TAGS = {'head', 'title', 'meta', 'link', 'style', 'script'}

    @classmethod
    def normalize_fullwidth_brackets(cls, text: str) -> str:
        """
        전각 괄호(［, ］)를 반각 괄호([, ])로 변환하여
        ［TAG_0］ → [TAG_0] 형태로 정규화한다.
        """
        if not text:
            return text
        return text.replace('［', '[').replace('］', ']')

    @classmethod
    def normalize_placeholders(cls, text: str) -> str:
        """
        Normalizes mutated or space-corrupted placeholders into standardized [TAG_N].
        Examples:
          [TAG_1 3] -> [TAG_13]
          [ TAG _ 0 ] -> [TAG_0]
          ［TAG_0］ -> [TAG_0]
          [tag- 5] -> [TAG_5]
          [TAG 2 0] -> [TAG_20]
          [tag1] -> [TAG_1]
          [태그_27] -> [TAG_27]
          [태그 27] -> [TAG_27]
          __TAG_27__ -> [TAG_27]
          TAG_27] -> [TAG_27]
          [TAG_27 -> [TAG_27]
        """
        if not text:
            return ""

        text = cls.normalize_fullwidth_brackets(text)

        # 1. Korean '태그' mutations: [태그_27], [태그 27] -> [TAG_27]
        text = re.sub(
            r'[\[［]\s*태그\s*[_\-\s]*([0-9][0-9\s]*)\s*[\]］]',
            lambda m: f"[TAG_{re.sub(r'\s+', '', m.group(1))}]",
            text,
            flags=re.IGNORECASE
        )

        # 2. Underscore tokens: __TAG_27__, _TAG_27_ -> [TAG_27]
        text = re.sub(
            r'_{1,2}TAG\s*[_\-\s]*([0-9][0-9\s]*)_{1,2}',
            lambda m: f"[TAG_{re.sub(r'\s+', '', m.group(1))}]",
            text,
            flags=re.IGNORECASE
        )

        # 3. Missing opening bracket: TAG_27], TAG 27] -> [TAG_27]
        text = re.sub(
            r'(?<![a-zA-Z0-9_\[［])TAG\s*[_\-\s]*([0-9][0-9\s]*)\s*[\]］]',
            lambda m: f"[TAG_{re.sub(r'\s+', '', m.group(1))}]",
            text,
            flags=re.IGNORECASE
        )

        # 4. Standard and mutated [TAG_N]
        def replacer(m):
            raw_digits = m.group(1)
            num_clean = re.sub(r'\s+', '', raw_digits)
            if num_clean.isdigit():
                return f"[TAG_{num_clean}]"
            return m.group(0)

        pattern = re.compile(r'[\[［]\s*TAG\s*[_\-\s]*([0-9][0-9\s]*)\s*[\]］]', re.IGNORECASE)
        text = pattern.sub(replacer, text)

        # 5. Missing closing bracket: [TAG_27 -> [TAG_27]
        text = re.sub(
            r'[\[［]\s*TAG\s*[_\-\s]*([0-9]+)(?![a-zA-Z0-9_\]］])',
            r'[TAG_\1]',
            text,
            flags=re.IGNORECASE
        )

        return text

    @classmethod
    def has_unmasked_placeholders(cls, text: str) -> bool:
        """Checks if any residual [TAG_N] placeholders remain in text."""
        if not text:
            return False
        return bool(cls.PLACEHOLDER_REGEX.search(text))

    @classmethod
    def mask_tags(cls, html_content: str) -> Tuple[str, Dict[str, str], str]:
        """
        Extracts all HTML tags and replaces them with [TAG_0], [TAG_1], ...
        Returns: (masked_text, tag_map, pure_text_without_tags)
        """
        if not html_content:
            return "", {}, ""

        # Pre-flatten any remaining ruby tags before masking to prevent word splitting
        if '<ruby' in html_content.lower() or '<rt' in html_content.lower():
            try:
                from domain.epub.ruby_processor import RubyProcessor
                html_content = RubyProcessor.flatten_ruby_html(html_content)
            except Exception:
                pass

        tag_map: Dict[str, str] = {}
        counter = 0

        def replacer(match):
            nonlocal counter
            tag = match.group(0)
            placeholder = f"[TAG_{counter}]"
            tag_map[placeholder] = tag
            counter += 1
            return placeholder

        masked_text = cls.TAG_REGEX.sub(replacer, html_content)
        
        # Calculate pure text without tags and without metadata
        pure_text = cls.extract_pure_text(html_content)

        return masked_text, tag_map, pure_text

    @classmethod
    def extract_pure_text(cls, html_content: str) -> str:
        """Extracts plain text stripping out tags and non-body metadata (title, head, etc.)."""
        if not html_content:
            return ""
        if '<' not in html_content:
            return html_content.strip()

        # Pre-flatten ruby tags so pronunciation is removed/handled cleanly before extracting text
        if '<ruby' in html_content.lower() or '<rt' in html_content.lower():
            try:
                from domain.epub.ruby_processor import RubyProcessor
                html_content = RubyProcessor.flatten_ruby_html(html_content)
            except Exception:
                pass

        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            for tag in soup.find_all(list(cls.IGNORED_TAGS)):
                tag.decompose()
            text = soup.get_text(separator=' ', strip=True)
            return html.unescape(text).strip()
        except Exception:
            clean = re.sub(r'<(?:head|title|meta|link|style|script)[^>]*>.*?</(?:head|title|meta|link|style|script)>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
            clean = re.sub(r'<[^>]+>', ' ', clean)
            return html.unescape(clean).strip()

    @classmethod
    def unmask_tags(cls, translated_masked_text: str, tag_map: Dict[str, str]) -> str:
        """
        Restores [TAG_N] placeholders back to original HTML tags.
        Handles variations produced by LLMs & Machine Translators:
          - Casing:         [tag_0], [Tag_0]
          - Spacing:        [ TAG _ 0 ], [TAG_ 0], [TAG_1 3]
          - Fullwidth:      ［TAG_0］
          - Hyphen:         [TAG-0], [tag-0]
          - No separator:   [TAG0]
          - Korean:         [태그_0], [태그 0]
          - Underscore:     __TAG_0__
          - Corrupted:      TAG_0], [TAG_0, and isolated number fragments (e.g. '27]')
        """
        if not translated_masked_text:
            return translated_masked_text

        # 0. Normalize fullwidth brackets and mutated placeholders first
        text = cls.normalize_placeholders(translated_masked_text)

        # Build direct number-to-tag map for safe fallback
        num_to_tag: Dict[int, str] = {}
        if tag_map:
            for placeholder, original_tag in tag_map.items():
                m = re.search(r'\d+', placeholder)
                if m:
                    num_to_tag[int(m.group(0))] = original_tag

        if not tag_map:
            # No tags to restore — strip any residual [TAG_N] or isolated fragments and return
            text = cls.PLACEHOLDER_REGEX.sub('', text)
            text = re.sub(r'(?<!\d)(?:TAG[_\-\s]*)?\d+\]', '', text)
            return text

        result = text

        # 1. Exact and flexible tag substitution pass
        for placeholder, original_tag in tag_map.items():
            num_match = re.search(r'\d+', placeholder)
            if num_match:
                num = num_match.group(0)
                pattern = re.compile(rf'[\[［]\s*TAG\s*[_\-\s]*{num}\s*[\]］]', re.IGNORECASE)
                result = pattern.sub(lambda m, tag=original_tag: tag, result)

        # 2. Fuzzy fallback pass for any remaining loose placeholder matches
        def fuzzy_sub(m):
            raw_digits = m.group(1)
            clean_num = re.sub(r'\s+', '', raw_digits)
            if clean_num.isdigit():
                val = int(clean_num)
                if val in num_to_tag:
                    return num_to_tag[val]
            return ''

        fuzzy_pattern = re.compile(r'[\[［]\s*TAG\s*[_\-\s]*([0-9][0-9\s]*)\s*[\]］]', re.IGNORECASE)
        result = fuzzy_pattern.sub(fuzzy_sub, result)

        # 3. Critical Fix: Catch broken/isolated number fragments like '27]' or ' 27]'
        # e.g., "아니오! 27] 그때는..." -> restores tag if 27 in num_to_tag, or cleans up
        def broken_num_sub(m):
            prefix = m.group(1)
            num_str = m.group(2)
            if num_str.isdigit():
                val = int(num_str)
                if val in num_to_tag:
                    return f"{prefix}{num_to_tag[val]}"
            return prefix

        broken_pattern = re.compile(r'(^|[\s가-힣!?,.~”"\'\)\]])(\d+)\]')
        result = broken_pattern.sub(broken_num_sub, result)

        # 4. Final cleanup: strip any remaining [TAG_N] placeholders or leftover tag fragments
        result = cls.PLACEHOLDER_REGEX.sub('', result)
        result = re.sub(r'(?<![a-zA-Z0-9_])TAG\s*[_\-\s]*\d+', '', result, flags=re.IGNORECASE)
        result = re.sub(r'(^|[\s가-힣!?,.~”"\'\)\]])\d+\]', r'\1', result)

        return result
