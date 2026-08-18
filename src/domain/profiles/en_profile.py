"""
OmniTranslator Pro - English Novel Translation Profile
Simplified and censorship-resistant prompt profile.
"""

from typing import List, Dict, Any
from domain.profiles.base_profile import BaseLanguageProfile, STRICT_META_INSTRUCTION

DEFAULT_SYSTEM_PROMPT = (
    "You are a professional English-to-Korean novel translator.\n"
    "Translate the following novel text into natural Korean. "
    "Maintain the character tone and markdown/tag placeholders (e.g. [TAG_0], [TAG_1]). "
    "Output only the translated text without explanations or markdown blocks."
    + STRICT_META_INSTRUCTION
)

class EnglishProfile(BaseLanguageProfile):
    """English Novel profile with simplified, tag-placeholder aware prompts."""

    def __init__(self):
        super().__init__("EN")

    def get_system_instruction(self, is_epub: bool = True) -> str:
        return DEFAULT_SYSTEM_PROMPT

    def get_prefill_history(self, is_epub: bool = True) -> List[Dict[str, Any]]:
        return [
            {
                "role": "user",
                "parts": ["Translate English fiction into natural Korean literary prose preserving tag placeholders."]
            },
            {
                "role": "model",
                "parts": ["Understood. I will provide a fluent Korean novel translation preserving tag placeholders."]
            }
        ]

    def get_prompt_template(self, is_epub: bool = True) -> str:
        return (
            "{{glossary_context}}\n\n"
            "Text to translate:\n"
            "{{slot}}\n\n"
            "Translation:"
        )

    def get_cleaner_patterns(self) -> List[str]:
        return [
            r'^(?:##\s*)?(?:Translation|Korean):?$',
            r'```'
        ]
