"""
OmniTranslator Pro - Postprocessing Text Cleaner
Removes thinking tags, site ad spam, and cleans format artifacts.
"""

import re
from typing import List

class TextCleaner:
    """Cleans LLM response text using regex patterns and HTML filter rules."""

    @classmethod
    def clean_html_response(cls, text: str) -> str:
        """Ported directly from seamarine: strips markdown codeblocks."""
        if not text:
            return ""
        cleaned = text.strip()
        if cleaned.startswith("```html"):
            cleaned = cleaned[7:].strip()
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:].strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
        return cleaned

    @classmethod
    def clean_text(cls, text: str, extra_patterns: List[str] = None) -> str:
        if not text:
            return ""

        cleaned = cls.clean_html_response(text)

        # 1. Remove <thinking>...</thinking> process blocks
        cleaned = re.sub(r'<thinking>[\s\S]*?</thinking>', '', cleaned, flags=re.IGNORECASE)

        # 2. Remove language-specific regex patterns (ads, headers)
        if extra_patterns:
            for pattern in extra_patterns:
                cleaned = re.sub(pattern, '', cleaned, flags=re.MULTILINE | re.IGNORECASE)

        # 3. Clean consecutive empty newlines
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

        return cleaned.strip()
