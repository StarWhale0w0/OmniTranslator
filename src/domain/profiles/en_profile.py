"""
OmniTranslator Pro - English Novel Translation Profile
"""

from typing import List, Dict, Any
from domain.profiles.base_profile import BaseLanguageProfile

DEFAULT_SYSTEM_PROMPT = (
    "You are a professional English-to-Korean literary translator.\n"
    "## Rules:\n"
    "1. Sentence Flow: Reorder complex English compound/relative clauses into natural Korean sentence order.\n"
    "2. Dialogue: Adapt English dialogue into natural, authentic Korean spoken register.\n"
    "3. Foreign Words: Transliterate names and places according to standard Korean loanword orthography.\n"
    "4. Output ONLY the translation."
)

class EnglishProfile(BaseLanguageProfile):
    """English Novel profile: Reorders compound sentences into idiomatic Korean flow."""

    def __init__(self):
        super().__init__("EN")

    def get_system_instruction(self) -> str:
        return DEFAULT_SYSTEM_PROMPT

    def get_prefill_history(self) -> List[Dict[str, Any]]:
        return [
            {
                "role": "user",
                "parts": ["(OOC: Translate English fiction into natural, idiomatic Korean literary prose.)"]
            },
            {
                "role": "model",
                "parts": ["(Understood. I will deliver a fluent Korean translation with natural sentence reordering.)"]
            }
        ]

    def get_prompt_template(self) -> str:
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
