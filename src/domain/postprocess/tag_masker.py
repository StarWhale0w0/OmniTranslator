"""
OmniTranslator Pro - Tag Masker Module
Masks HTML/XML/Media tags into [TAG_N] placeholders and restores them post-translation.
"""

import re
import html
from typing import Tuple, Dict, Optional
from bs4 import BeautifulSoup

class TagMasker:
    """Isolates HTML/XML/Media tags as [TAG_N] placeholders to protect them from LLM modification/censorship."""

    TAG_REGEX = re.compile(r'<[^>]+>', re.DOTALL)
    PLACEHOLDER_REGEX = re.compile(r'\[\s*TAG\s*_?\s*[0-9][0-9\s]*\s*\]', re.IGNORECASE)
    IGNORED_TAGS = {'head', 'title', 'meta', 'link', 'style', 'script'}

    @classmethod
    def normalize_placeholders(cls, text: str) -> str:
        """
        Normalizes mutated or space-corrupted placeholders into standardized [TAG_N].
        Examples:
          [TAG_1 3] -> [TAG_13]
          [ TAG _ 0 ] -> [TAG_0]
          [tag_ 5] -> [TAG_5]
          [TAG 2 0] -> [TAG_20]
          [tag1] -> [TAG_1]
        """
        if not text:
            return ""

        def replacer(m):
            raw_digits = m.group(1)
            num_clean = re.sub(r'\s+', '', raw_digits)
            if num_clean.isdigit():
                return f"[TAG_{num_clean}]"
            return m.group(0)

        # Matches [TAG_1 3], [ TAG _ 0 ], [tag 5], [TAG10], etc.
        pattern = re.compile(r'\[\s*TAG\s*_?\s*([0-9][0-9\s]*)\s*\]', re.IGNORECASE)
        return pattern.sub(replacer, text)

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
        Handles variations in casing/spacing produced by LLMs and translators (e.g. [tag_0], [ TAG _ 0 ], [TAG_ 0], [TAG_1 3]).
        """
        if not translated_masked_text or not tag_map:
            return translated_masked_text

        # 1. Normalize mutated placeholders first (e.g. [TAG_1 3] -> [TAG_13])
        normalized_text = cls.normalize_placeholders(translated_masked_text)
        result = normalized_text

        # 2. Exact and flexible tag substitution pass
        for placeholder, original_tag in tag_map.items():
            num_match = re.search(r'\d+', placeholder)
            if num_match:
                num = num_match.group(0)
                pattern = re.compile(rf'\[\s*TAG\s*_?\s*{num}\s*\]', re.IGNORECASE)
                result = pattern.sub(lambda m, tag=original_tag: tag, result)

        # 3. Fuzzy fallback pass for any remaining loose placeholder matches
        def fuzzy_sub(m):
            raw_digits = m.group(1)
            clean_num = re.sub(r'\s+', '', raw_digits)
            std_ph = f"[TAG_{clean_num}]"
            if std_ph in tag_map:
                return tag_map[std_ph]
            return m.group(0)

        fuzzy_pattern = re.compile(r'\[\s*TAG\s*_?\s*([0-9][0-9\s]*)\s*\]', re.IGNORECASE)
        result = fuzzy_pattern.sub(fuzzy_sub, result)

        return result
