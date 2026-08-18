"""
OmniTranslator Pro - Chinese Web Novel Translation Profile
Simplified and censorship-resistant prompt profile.
"""

from typing import List, Dict, Any
from domain.profiles.base_profile import BaseLanguageProfile, STRICT_META_INSTRUCTION

DEFAULT_SYSTEM_PROMPT = (
    "You are a professional Chinese-to-Korean web novel translator.\n"
    "Translate the following novel text into natural Korean with past tense narrative (~였다, ~했다). "
    "Maintain the character tone and markdown/tag placeholders (e.g. [TAG_0], [TAG_1]). "
    "Output only the translated text without explanations or markdown blocks."
    + STRICT_META_INSTRUCTION
)

class ChineseProfile(BaseLanguageProfile):
    """Chinese Web Novel profile with simplified, tag-placeholder aware prompts."""

    def __init__(self):
        super().__init__("ZH")

    def get_system_instruction(self, is_epub: bool = True) -> str:
        return DEFAULT_SYSTEM_PROMPT

    def get_prefill_history(self, is_epub: bool = True) -> List[Dict[str, Any]]:
        return [
            {
                "role": "user",
                "parts": ["Translate the web novel text preserving all tag placeholders faithfully."]
            },
            {
                "role": "model",
                "parts": ["Understood. I will provide a fluent Korean web novel translation with past tense narrative preserving tag placeholders."]
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
            r'^.*네티즌이?\s*업로드.*$',
            r'^.*전자책.*(?:무료|다운로드|완결본|사이트).*$',
            r'^.*독자들의?\s*(?:보물창고|천국).*$',
            r'\([^)]*www\.[^)]*\)',
            r'^(?:##\s*)?(?:번역\s*결과|Translation|Korean):?$',
            r'```'
        ]
