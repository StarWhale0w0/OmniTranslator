"""
OmniTranslator Pro - Dynamic Glossary Context Injector
"""

from typing import List, Dict, Any
from common.logger import setup_logger

logger = setup_logger("GlossaryInjector")

class GlossaryInjector:
    """Filters JSON glossary entries present in chunk text and formats strict context string."""

    @classmethod
    def inject_glossary_context(
        cls,
        chunk_text: str,
        glossary_entries: List[Dict[str, Any]],
        max_entries: int = 8,
        max_chars: int = 600,
        enabled: bool = True
    ) -> str:
        if not enabled or not glossary_entries:
            return ""

        chunk_lower = chunk_text.lower()
        matched = []

        for entry in glossary_entries:
            keyword = entry.get("keyword", "")
            if keyword and keyword.lower() in chunk_lower:
                matched.append(entry)

        if not matched:
            return ""

        # Sort by occurrence_count descending
        matched.sort(key=lambda x: int(x.get("occurrence_count", 0)), reverse=True)

        lines = ["[필수 고유명사 용어집 (Strict Glossary - Must follow consistently)]"]
        current_len = len(lines[0])

        for item in matched[:max_entries]:
            line = f"- {item['keyword']} -> {item['translated_keyword']}"
            cat = item.get("category", "")
            if cat:
                line += f" ({cat})"

            if current_len + len(line) > max_chars:
                break

            lines.append(line)
            current_len += len(line)

        return "\n".join(lines) if len(lines) > 1 else ""
