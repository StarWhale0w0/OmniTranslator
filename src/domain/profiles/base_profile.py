"""
OmniTranslator Pro - Base Language Profile
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any

STRICT_META_INSTRUCTION = (
    "\n\n[출력 절대 규칙]\n"
    "절대로 번역 과정, 검토 메모, 체크리스트, 'Final check' 등의 메타 텍스트를 출력하지 마십시오. "
    "오직 최종 번역된 본문 HTML/텍스트만을 출력하십시오."
)

class BaseLanguageProfile(ABC):
    """Abstract base class defining language-specific prompt engineering & translation rules."""

    def __init__(self, lang_code: str):
        self.lang_code = lang_code.upper()

    @abstractmethod
    def get_system_instruction(self, is_epub: bool = True) -> str:
        """Returns the system instruction prompt with strict meta rules appended."""
        pass

    @abstractmethod
    def get_prefill_history(self, is_epub: bool = True) -> List[Dict[str, Any]]:
        """Returns prefill conversation history for censorship bypass / persona anchoring."""
        pass

    @abstractmethod
    def get_prompt_template(self, is_epub: bool = True) -> str:
        """Returns prompt template containing {{slot}} and {{glossary_context}} placeholders."""
        pass

    @abstractmethod
    def get_cleaner_patterns(self) -> List[str]:
        """Returns regex patterns for removing spam/headers specific to this language."""
        pass
