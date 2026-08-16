"""
OmniTranslator Pro - Postprocessing Text Cleaner
Removes thinking tags, site ad spam, and cleans format artifacts.
"""

import re
from typing import List

class TextCleaner:
    """Cleans LLM response text using regex patterns and HTML filter rules."""

    @classmethod
    def clean_text(cls, text: str, extra_patterns: List[str] = None) -> str:
        if not text:
            return ""

        cleaned = text.strip()

        # 1. Remove <thinking>...</thinking> process blocks
        cleaned = re.sub(r'<thinking>[\s\S]*?</thinking>', '', cleaned, flags=re.IGNORECASE)

        # 2. Remove language-specific regex patterns (ads, headers)
        if extra_patterns:
            for pattern in extra_patterns:
                cleaned = re.sub(pattern, '', cleaned, flags=re.MULTILINE | re.IGNORECASE)

        # 3. Clean consecutive empty newlines
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

        return cleaned.strip()
