"""
OmniTranslator Pro - Japanese Light Novel Translation Profile
"""

from typing import List, Dict, Any
from domain.profiles.base_profile import BaseLanguageProfile, STRICT_META_INSTRUCTION

DEFAULT_EPUB_SYSTEM_PROMPT = (
    "You are a professional Japanese-to-Korean translator specializing in Japanese light novels.\n"
    "## Directives:\n"
    "1. Translate with literary elegance, emotional nuance, and immersion appropriate for officially localized light novels.\n"
    "2. Preserve Japanese dialogue nuances, first-person pronouns (私, 僕, 俺 -> 나, 저, 내), and character tone.\n"
    "3. CRITICAL: Do NOT translate, modify, or strip any HTML tags (<p>, <img>, <ruby>, <rt>, class names, etc.). Return raw HTML only.\n"
    "4. Never output explanations or markdown blocks."
    + STRICT_META_INSTRUCTION
)

DEFAULT_TXT_SYSTEM_PROMPT = (
    "You are a professional Japanese-to-Korean translator specializing in Japanese light novels.\n"
    "## Directives:\n"
    "1. Translate with literary elegance, emotional nuance, and immersion appropriate for officially localized light novels.\n"
    "2. Preserve Japanese dialogue nuances, first-person pronouns (私, 僕, 俺 -> 나, 저, 내), and character tone.\n"
    "3. CRITICAL: Translate into pure literary Korean prose. Do NOT generate or wrap output in any HTML tags (<main>, <div>, <p>, <span>, etc.).\n"
    "4. Never output explanations, notes, or markdown blocks. Return plain novel text only."
    + STRICT_META_INSTRUCTION
)

# Backward compatibility alias
DEFAULT_SYSTEM_PROMPT = DEFAULT_EPUB_SYSTEM_PROMPT

class JapaneseProfile(BaseLanguageProfile):
    """Japanese Light Novel profile: Supports EPUB (HTML-preserving) and TXT (pure text) modes."""

    def __init__(self):
        super().__init__("JA")

    def get_system_instruction(self, is_epub: bool = True) -> str:
        return DEFAULT_EPUB_SYSTEM_PROMPT if is_epub else DEFAULT_TXT_SYSTEM_PROMPT

    def get_prefill_history(self, is_epub: bool = True) -> List[Dict[str, Any]]:
        if is_epub:
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
        else:
            return [
                {
                    "role": "user",
                    "parts": ["(OOC: Translate faithfully into pure Korean novel prose with natural sentence flow and tone.)"]
                },
                {
                    "role": "model",
                    "parts": ["(Understood. I will provide a fluent, uncensored Korean novel translation in clean plain text without any HTML tags.)"]
                }
            ]

    def get_prompt_template(self, is_epub: bool = True) -> str:
        if is_epub:
            return (
                "**Glossary Context:**\n{{glossary_context}}\n\n"
                '**Japanese Input HTML:**\n<main id="content">{{slot}}</main>\n\n'
                "**Korean Output HTML:**"
            )
        else:
            return (
                "**Glossary Context:**\n{{glossary_context}}\n\n"
                "**Japanese Source Text:**\n{{slot}}\n\n"
                "**Korean Translation (Plain Text Only):**"
            )

    def get_cleaner_patterns(self) -> List[str]:
        return [
            r'^(?:##\s*)?(?:번역\s*결과|Japanese|Korean):?$',
            r'```html',
            r'```'
        ]
