"""
OmniTranslator Pro - English Novel Translation Profile
Tuned for natural Korean web novel / fiction prose and natural conversational register.
"""

from typing import List, Dict, Any
from domain.profiles.base_profile import BaseLanguageProfile, STRICT_META_INSTRUCTION

DEFAULT_SYSTEM_PROMPT = (
    "당신은 영미 문학 및 웹소설 전문 번역 작가입니다.\n"
    "원문의 내용과 맥락을 1:1로 충실히 전달하되, 직역투를 벗어나 한국 독자가 몰입할 수 있는 매끄럽고 유려한 한국어 문장으로 번역하십시오.\n\n"
    "1. [웹소설 맞춤형 구어체 & 서술 톤앤매너]:\n"
    "   - 인물의 성격과 상황에 어울리는 생생한 한국어 구어체와 대화 호흡을 살리십시오.\n"
    "   - 친구, 동료, 연소자 간 대화에서 딱딱한 극존칭(~하지 않습니까?, ~그렇습니다, ~했습니까?) 대신 자연스러운 반말 및 구어체(~야?, ~거든, ~잖아, ~했어?, ~지)를 구사하십시오.\n"
    "   - 영어 3인칭 대명사(He, She, His, Her)의 기계적 직역('그는', '그녀는') 남발을 피하고, 문맥상 자연스러운 주어 생략 또는 인명/직책으로 전환하십시오.\n"
    "   - 서술문은 한국어 소설의 표준 과거형 시제(~했다, ~였다)로 매끄럽게 연결하십시오.\n"
    "2. [외래어 및 고유명사 일관성]: 표준 외래어 표기법을 준수하여 자연스럽게 음역하십시오.\n"
    "3. [태그 보존]: [TAG_0], [TAG_1] 등의 플레이스홀더를 정확히 보존하십시오.\n"
    "4. [순수 본문 출력]: 부가 설명 없이 최종 번역 텍스트만을 출력하십시오."
    + STRICT_META_INSTRUCTION
)

class EnglishProfile(BaseLanguageProfile):
    """English Novel profile tuned for natural web novel prose and dialogue."""

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
            r'^(?:##\s*)?(?:Translation|Korean):?$',
            r'```'
        ]
