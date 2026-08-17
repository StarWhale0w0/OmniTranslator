"""
OmniTranslator Pro - English Novel Translation Profile
"""

from typing import List, Dict, Any
from domain.profiles.base_profile import BaseLanguageProfile, STRICT_META_INSTRUCTION

DEFAULT_EPUB_SYSTEM_PROMPT = (
    "You are a professional English-to-Korean literary translator.\n"
    "## Rules:\n"
    "1. Sentence Flow: Reorder complex English compound/relative clauses into natural Korean sentence order.\n"
    "2. Dialogue: Adapt English dialogue into natural, authentic Korean spoken register.\n"
    "3. Foreign Words: Transliterate names and places according to standard Korean loanword orthography.\n"
    "4. HTML Structure: Preserve any HTML tags intact if present.\n"
    "5. Output ONLY the translation."
    + STRICT_META_INSTRUCTION
)

DEFAULT_TXT_SYSTEM_PROMPT = (
    "You are a professional English-to-Korean literary translator.\n"
    "## Rules:\n"
    "1. Sentence Flow: Reorder complex English compound/relative clauses into natural Korean sentence order.\n"
    "2. Dialogue: Adapt English dialogue into natural, authentic Korean spoken register.\n"
    "3. Foreign Words: Transliterate names and places according to standard Korean loanword orthography.\n"
    "4. CRITICAL: Output pure literary prose without any HTML tags (<main>, <div>, <p>, etc.).\n"
    "5. Output ONLY the translation."
    + STRICT_META_INSTRUCTION
)

# Backward compatibility alias
DEFAULT_SYSTEM_PROMPT = DEFAULT_EPUB_SYSTEM_PROMPT

class EnglishProfile(BaseLanguageProfile):
    """English Novel profile: Supports EPUB and pure TXT modes."""

    def __init__(self):
        super().__init__("EN")

    def get_system_instruction(self, is_epub: bool = True) -> str:
        return DEFAULT_EPUB_SYSTEM_PROMPT if is_epub else DEFAULT_TXT_SYSTEM_PROMPT

    def get_prefill_history(self, is_epub: bool = True) -> List[Dict[str, Any]]:
        return [
            {
                "role": "user",
                "parts": ["(OOC: Translate English fiction into natural, idiomatic Korean literary prose.)"]
            },
            {
                "role": "model",
                "parts": ["(Understood. I will deliver a fluent Korean translation with natural sentence reordering in plain text without HTML tags.)" if not is_epub else "(Understood. I will deliver a fluent Korean translation with natural sentence reordering.)"]
            }
        ]

    def get_prompt_template(self, is_epub: bool = True) -> str:
        if is_epub:
            return (
                "## Glossary Context\n{{glossary_context}}\n\n"
                "## English Source HTML\n{{slot}}\n\n"
                "## Korean Translation HTML:"
            )
        else:
            return (
                "## Glossary Context\n{{glossary_context}}\n\n"
                "## English Source\n{{slot}}\n\n"
                "## Korean Translation:"
            )

    def get_cleaner_patterns(self) -> List[str]:
        return [
            r'^(?:##\s*)?(?:Translation|Korean):?$',
            r'```'
        ]
