"""
OmniTranslator Pro - Japanese Light Novel Translation Profile
Tuned for natural Korean light novel / web novel prose and natural conversational register.
"""

from typing import List, Dict, Any
from domain.profiles.base_profile import BaseLanguageProfile, STRICT_META_INSTRUCTION

DEFAULT_SYSTEM_PROMPT = (
    "당신은 일본 라이트노벨/웹소설의 최고 전문 번역 작가입니다.\n"
    "원문의 사건과 뉘앙스를 1:1로 충실히 반영하되, 한국 웹소설/라이트노벨 독자에게 자연스럽고 몰입감 높은 유려한 문체로 번역하십시오.\n\n"
    "1. [웹소설 맞춤형 구어체 & 서술 톤앤매너]:\n"
    "   - 인물의 연령, 성격, 관계에 따라 생생하고 자연스러운 대화체를 구사하십시오.\n"
    "   - 동료, 청소년, 친구 간 대화에서 어색한 극존칭(~하지 않습니까?, ~그렇습니다, ~했습니까?)을 배제하고 자연스러운 반말/구어체(~야?, ~거든, ~잖아, ~했어?, ~냐?, ~라고?, ~지)를 적용하십시오.\n"
    "   - 3인칭 대명사('그는', '그녀는')의 기계적 직역 남발을 자제하고, 문맥에 따라 주어를 생략하거나 인명/직책/호칭으로 자연스럽게 전환하십시오.\n"
    "   - 서술문은 속도감 있는 과거형 문장(~했다, ~였다)으로 일관성 있게 표현하십시오.\n"
    "2. [호칭 및 고유명사 일관성]: 1인칭(私, 僕, 俺 -> 저, 나, 내), 2인칭, 캐릭터 말투 및 공식 라이트노벨 번역 관례를 충실히 반영하십시오.\n"
    "3. [태그 보존]: [TAG_0], [TAG_1] 등의 플레이스홀더를 누락 없이 원문 위치에 보존하십시오.\n"
    "4. [순수 본문 출력]: 부가 설명이나 마크다운 코드블록 없이 최종 번역 텍스트만을 출력하십시오."
    + STRICT_META_INSTRUCTION
)

class JapaneseProfile(BaseLanguageProfile):
    """Japanese Light Novel profile tuned for natural web novel prose and dialogue."""

    def __init__(self):
        super().__init__("JA")

    def get_system_instruction(self, is_epub: bool = True) -> str:
        return DEFAULT_SYSTEM_PROMPT

    def get_prefill_history(self, is_epub: bool = True) -> List[Dict[str, Any]]:
        return [
            {
                "role": "user",
                "parts": ["Translate the Japanese novel text into engaging, fluent Korean prose preserving tag placeholders."]
            },
            {
                "role": "model",
                "parts": ["Understood. I will provide a fluent, character-driven Korean novel translation with natural dialogue and past tense narrative preserving tag placeholders."]
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
            r'^(?:##\s*)?(?:번역\s*결과|Translation|Korean):?$',
            r'```html',
            r'```'
        ]
