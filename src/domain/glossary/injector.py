"""
OmniTranslator Pro - Dynamic Glossary Context Injector
"""

from typing import List, Dict, Any, Optional
from common.logger import setup_logger
from domain.glossary.matcher import GlossaryMatcher

logger = setup_logger("GlossaryInjector")

class GlossaryInjector:
    """Filters JSON glossary entries present in chunk text and formats strict context string."""

    @classmethod
    def inject_glossary_context(
        cls,
        chunk_text: str,
        glossary_entries: List[Dict[str, Any]],
        max_entries: int = 30,
        max_chars: int = 2000,
        enabled: bool = True,
        lang_code: str = "ZH"
    ) -> str:
        """Injects strict glossary context using GlossaryMatcher."""
        return GlossaryMatcher.inject_glossary(
            chunk_text=chunk_text,
            glossary_entries=glossary_entries,
            max_entries=max_entries,
            max_chars=max_chars,
            enabled=enabled,
            lang_code=lang_code
        )

