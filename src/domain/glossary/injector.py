"""
OmniTranslator Pro - Dynamic Glossary Context Injector
"""

from typing import List, Dict, Any
from common.logger import setup_logger

logger = setup_logger("GlossaryInjector")

class GlossaryInjector:
    """Filters JSON glossary entries present in chunk text and formats context string."""

    @classmethod
    def inject_glossary_context(
        cls,
        chunk_text: str,
        glossary_entries: List[Dict[str, Any]],
        max_entries: int = 5,
        max_chars: int = 500
    ) -> str:
        if not glossary_entries:
            return "용어집 컨텍스트 없음"

        chunk_lower = chunk_text.lower()
        matched = []

        for entry in glossary_entries:
            keyword = entry.get("keyword", "")
            if keyword and keyword.lower() in chunk_lower:
                matched.append(entry)

        if not matched:
            return "용어집 컨텍스트 없음 (매칭 항목 없음)"

        matched.sort(key=lambda x: int(x.get("occurrence_count", 0)), reverse=True)

        lines = []
        current_len = 0
        for item in matched[:max_entries]:
            line = f"- {item['keyword']} -> {item['translated_keyword']}"
            if current_len + len(line) > max_chars:
                break
            lines.append(line)
            current_len += len(line)

        return "\n".join(lines) if lines else "용어집 컨텍스트 없음"
