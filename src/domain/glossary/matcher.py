"""
OmniTranslator Pro - Dynamic Glossary Matcher & Prioritized Injector
Features:
- Unicode NFKC normalization for robust Chinese simplified/traditional term matching.
- Longest Match First (긴 단어 우선 정렬): Prioritizes longer proper nouns ('钟九天', 3 chars)
  over shorter sub-terms ('钟九', 2 chars) to prevent substring collisions.
- High-density chunk filtering.
- Strict prompt format with CRITICAL MANDATORY RULE.
"""

import unicodedata
from typing import List, Dict, Any, Optional
from common.logger import setup_logger

logger = setup_logger("GlossaryMatcher")

GLOSSARY_HARD_CONSTRAINT = (
    "CRITICAL MANDATORY RULE:\n"
    "The provided glossary mappings MUST be applied exactly and strictly as written.\n"
    "NEVER translate, transliterate, or alter these terms into Korean Sino-readings (Hanja-eum), literal semantic translations, or other phonetic variations.\n"
    "Glossary mapping takes absolute precedence over any contextual, stylistic, or linguistic reasoning."
)

class GlossaryMatcher:
    """Matches, sorts (longest match first), and formats glossary entries for translation context."""

    @classmethod
    def match_terms(
        cls,
        text: str,
        glossary_entries: List[Dict[str, Any]],
        normalize_nfkc: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Matches glossary entries present in the chunk text.
        Applies Unicode NFKC normalization and sorts entries by Longest Match First.
        """
        if not text or not glossary_entries:
            return []

        norm_text = unicodedata.normalize('NFKC', text) if normalize_nfkc else text
        norm_text_lower = norm_text.lower()

        matched: List[Dict[str, Any]] = []
        seen_keywords = set()

        for entry in glossary_entries:
            raw_kw = str(entry.get("keyword", "")).strip()
            raw_tr = str(entry.get("translated_keyword", "")).strip()
            if not raw_kw or not raw_tr:
                continue

            kw = unicodedata.normalize('NFKC', raw_kw) if normalize_nfkc else raw_kw
            if not kw or kw in seen_keywords:
                continue

            # Check presence in text (case-insensitive where applicable)
            if kw in norm_text or kw.lower() in norm_text_lower:
                matched.append(entry)
                seen_keywords.add(kw)

        # Longest Match First:
        # 1st key: Length of keyword descending (longer terms matched first)
        # 2nd key: Occurrence count descending
        matched.sort(
            key=lambda x: (
                len(unicodedata.normalize('NFKC', str(x.get("keyword", "")))),
                int(x.get("occurrence_count", 1)) if str(x.get("occurrence_count", 1)).isdigit() else 1
            ),
            reverse=True
        )

        return matched

    @classmethod
    def format_glossary_context(
        cls,
        matched_entries: List[Dict[str, Any]],
        max_entries: int = 30,
        max_chars: int = 2000,
        lang_code: str = "ZH"
    ) -> str:
        """
        Formats matched glossary entries into a strict prompt context block.
        """
        if not matched_entries:
            return ""

        header = (
            "[Glossary / 고유명사 사전]\n"
            f"{GLOSSARY_HARD_CONSTRAINT}"
        )
        lines = [header]
        current_len = len(header)

        for item in matched_entries[:max_entries]:
            kw = str(item.get("keyword", "")).strip()
            tr = str(item.get("translated_keyword", "")).strip()
            if not kw or not tr:
                continue

            cat = str(item.get("category", "")).strip()
            cat_str = f" ({cat})" if cat else ""
            line = f"- {kw} -> {tr}{cat_str}"

            if current_len + len(line) + 1 > max_chars:
                break

            lines.append(line)
            current_len += len(line) + 1

        if len(lines) <= 1:
            return ""

        return "\n".join(lines)

    @classmethod
    def inject_glossary(
        cls,
        chunk_text: str,
        glossary_entries: List[Dict[str, Any]],
        max_entries: int = 30,
        max_chars: int = 2000,
        enabled: bool = True,
        lang_code: str = "ZH"
    ) -> str:
        """High-level method to match and format glossary context for a given chunk."""
        if not enabled or not glossary_entries or not chunk_text:
            return ""

        matched = cls.match_terms(chunk_text, glossary_entries)
        if not matched:
            return ""

        return cls.format_glossary_context(
            matched_entries=matched,
            max_entries=max_entries,
            max_chars=max_chars,
            lang_code=lang_code
        )
