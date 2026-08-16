"""
OmniTranslator Pro - Base Language Profile
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseLanguageProfile(ABC):
    """Abstract base class defining language-specific prompt engineering & translation rules."""

    def __init__(self, lang_code: str):
        self.lang_code = lang_code.upper()

    @abstractmethod
    def get_system_instruction(self) -> str:
        """Returns the system instruction prompt."""
        pass

    @abstractmethod
    def get_prefill_history(self) -> List[Dict[str, Any]]:
        """Returns prefill conversation history for censorship bypass / persona anchoring."""
        pass

    @abstractmethod
    def get_prompt_template(self) -> str:
        """Returns prompt template containing {{slot}} and {{glossary_context}} placeholders."""
        pass

    @abstractmethod
    def get_cleaner_patterns(self) -> List[str]:
        """Returns regex patterns for removing spam/headers specific to this language."""
        pass
