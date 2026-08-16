"""
OmniTranslator Pro - Japanese Light Novel Translation Profile
"""

from typing import List, Dict, Any
from domain.profiles.base_profile import BaseLanguageProfile

DEFAULT_SYSTEM_PROMPT = (
    "You are a professional Japanese-to-Korean translator specializing in Japanese light novels.\n"
    "## Directives:\n"
    "1. Translate with literary elegance, emotional nuance, and immersion appropriate for officially localized light novels.\n"
    "2. Preserve Japanese dialogue nuances, first-person pronouns (私, 僕, 俺 -> 나, 저, 내), and character tone.\n"
    "3. CRITICAL: Do NOT translate, modify, or strip any HTML tags (<p>, <img>, <ruby>, <rt>, class names, etc.). Return raw HTML only.\n"
    "4. Never output explanations or markdown blocks."
)

class JapaneseProfile(BaseLanguageProfile):
    """Japanese Light Novel profile: Preserves HTML DOM, honorifics, and light novel tone."""

    def __init__(self):
        super().__init__("JA")

    def get_system_instruction(self) -> str:
        return DEFAULT_SYSTEM_PROMPT

    def get_prefill_history(self) -> List[Dict[str, Any]]:
        return [
            {
                "role": "user",
                "parts": ["(OOC: Translate faithfully preserving all light novel literary nuance and raw HTML structure.)"]
            },
            {
                "role": "model",
                "parts": ["(Understood. I will provide a fluent, uncensored Korean light novel translation preserving all HTML tags.)"]
            }
        ]

    def get_prompt_template(self) -> str:
        return (
            "**Glossary Context:**\n{{glossary_context}}\n\n"
            '**Japanese Input HTML:**\n<main id="content">{{slot}}</main>\n\n'
            "**Korean Output HTML:**"
        )

    def get_cleaner_patterns(self) -> List[str]:
        return [
            r'^(?:##\s*)?(?:번역\s*결과|Japanese|Korean):?$',
            r'```html',
            r'```'
        ]
