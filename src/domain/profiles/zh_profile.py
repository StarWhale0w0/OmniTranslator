"""
OmniTranslator Pro - Chinese Web Novel Translation Profile
Simplified and censorship-resistant prompt profile.
"""

from typing import List, Dict, Any
from domain.profiles.base_profile import BaseLanguageProfile, STRICT_META_INSTRUCTION

ZH_GLOSSARY_HARD_CONSTRAINT = (
    "CRITICAL MANDATORY RULE:\n"
    "The provided glossary mappings MUST be applied exactly and strictly as written.\n"
    "NEVER translate, transliterate, or alter these terms into Korean Sino-readings (Hanja-eum), literal semantic translations, or other phonetic variations.\n"
    "Glossary mapping takes absolute precedence over any contextual, stylistic, or linguistic reasoning."
)

DEFAULT_SYSTEM_PROMPT = (
    "You are a professional Chinese-to-Korean web novel translator.\n"
    "1. Translate Chinese text into immersive, fluent Korean web novel prose with past tense narrative (~였다, ~했다).\n"
    "2. Character Names (인명): MUST follow Standard Pinyin transliteration into Korean (e.g. 钟九 -> 종지우, 张小华 -> 장샤오화, 萧炎 -> 샤오옌, 林动 -> 린둥, 顾夜白 -> 구예바이, 楚风 -> 추펑), NEVER Korean Hanja-eum readings (종구, 장소화, 소염, 임동, 고야백 등 X).\n"
    "3. Locations, Sects, Martial Arts, and SF/Fantasy Terms (지명/문파/세력/무공/기술/SF·크툴루 설정): MUST follow Korean Sino-readings (Hanja-eum) (e.g. 少林寺 -> 소림사, 华山派 -> 화산파, 洛阳 -> 낙양, 界域 -> 계역, 天机局 -> 천기국, 黄昏社 -> 황혼사).\n"
    "4. Real-world Brands & Foreign Countries (외래어/브랜드/국가명): Follow Standard Korean Loanword Orthography (e.g. 巴西 -> 브라질, 宝马 -> BMW).\n"
    "5. Interpersonal Titles (호칭): Translate relational titles naturally into Korean based on context (e.g. 师兄 -> 사형, 师妹 -> 사매, 哥/姐 -> 형/누나/오빠/언니).\n"
    "6. Maintain character tone, dialogues, and markdown/tag placeholders (e.g. [TAG_0], [TAG_1]) faithfully.\n"
    "7. Output only the translated text without explanations or markdown blocks."
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
            f"{ZH_GLOSSARY_HARD_CONSTRAINT}\n\n"
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