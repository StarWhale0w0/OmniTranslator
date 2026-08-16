"""
OmniTranslator Pro - AI Glossary Extractor
Extracts terms (characters, places, items) into JSON format with language rules.
"""

import json
from pathlib import Path
from typing import List, Dict, Any
from common.logger import setup_logger

logger = setup_logger("GlossaryExtractor")

class GlossaryExtractor:
    """Extracts terms from raw novel text into JSON format using Gemini AI."""

    PROMPT_TEMPLATE = (
        "Analyze the input text and extract a JSON glossary for translating to Korean.\n"
        "Language Mode: {lang_code}\n"
        "Categories: Character Names, Place Names, Proper Nouns (Skills/Items), Organizations.\n\n"
        "## Rules for {lang_code}:\n"
        "{rules}\n\n"
        "Input Text:\n```\n{text}\n```\n\n"
        'Output ONLY a valid JSON list of objects: [{"keyword": "...", "translated_keyword": "...", "target_language": "ko", "occurrence_count": 1}]'
    )

    LANG_RULES = {
        "ZH": "Default Rule: Use Sino-Korean Hanja reading for Chinese names/places (e.g. 北京 -> 북경, 侯龙涛 -> 후룡도).\n"
              "Critical Exception: Use standard Korean transliteration for foreign brands/names (e.g. 宝马(BMW) -> BMW, 巴西 -> 브라질).",
        "JA": "Translate Japanese light novel names, ruby titles, and honorifics into standard Korean light novel rendering.",
        "EN": "Transliterate English proper nouns according to Korean loanword orthography rules."
    }

    @classmethod
    def save_glossary_json(cls, entries: List[Dict[str, Any]], filepath: Path) -> None:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(entries)} glossary entries to {filepath}")

    @classmethod
    def load_glossary_json(cls, filepath: Path) -> List[Dict[str, Any]]:
        if not filepath.exists():
            return []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"Failed to load glossary JSON ({filepath}): {e}")
            return []
