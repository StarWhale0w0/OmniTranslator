"""
OmniTranslator Pro - AI Glossary Extractor
Extracts terms (characters, places, items) into JSON format with language rules.
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from google.genai import types as genai_types
from common.logger import setup_logger

logger = setup_logger("GlossaryExtractor")

class GlossaryExtractor:
    """Extracts terms from raw novel text into JSON format using Gemini AI."""

    PROMPT_TEMPLATE = (
        "Analyze the input novel text and extract a glossary for translating to Korean.\n"
        "Target Language Mode: {lang_code}\n"
        "Categories: Character Names (인명), Place Names (지명), Proper Nouns (고유명사), Organizations (단체).\n\n"
        "## Rules for {lang_code}:\n"
        "{rules}\n\n"
        "Input Novel Text:\n```\n{text}\n```\n\n"
        "Output ONLY a valid JSON list of objects format without markdown code blocks:\n"
        '[\n  {{"keyword": "원문", "translated_keyword": "번역어", "category": "인명/지명/고유명사", "occurrence_count": 1}}\n]'
    )

    LANG_RULES = {
        "ZH": "Default Rule: Use Sino-Korean Hanja reading for Chinese names/places (e.g. 北京 -> 북경, 侯龙涛 -> 후룡도).\n"
              "Critical Exception: Use standard Korean transliteration for foreign brands/names (e.g. 宝马(BMW) -> BMW, 巴西 -> 브라질).",
        "JA": "Translate Japanese light novel names, ruby titles, and honorifics into standard Korean light novel rendering.",
        "EN": "Transliterate English proper nouns according to Korean loanword orthography rules."
    }

    @classmethod
    async def extract_glossary_async(
        cls,
        gemini_client: Any,
        text_content: str,
        lang_code: str = "JA",
        model_name: str = "gemini-2.5-flash"
    ) -> List[Dict[str, Any]]:
        """Extracts terms asynchronously using Gemini API."""
        rules = cls.LANG_RULES.get(lang_code.upper(), cls.LANG_RULES["JA"])
        sample_text = text_content[:15000]  # First 15,000 chars for extraction

        prompt_str = cls.PROMPT_TEMPLATE.format(
            lang_code=lang_code,
            rules=rules,
            text=sample_text
        )

        prompt_contents = [
            genai_types.Content(
                role="user",
                parts=[genai_types.Part.from_text(text=prompt_str)]
            )
        ]

        try:
            logger.info(f"Extracting glossary using model '{model_name}' for language '{lang_code}'...")
            result_raw = await gemini_client.generate_text_async(
                prompt_contents=prompt_contents,
                model_name=model_name,
                temperature=0.2,
                top_p=0.8
            )

            # Clean json fences if present
            cleaned_json = re.sub(r'^```(?:json)?\s*', '', result_raw.strip(), flags=re.MULTILINE)
            cleaned_json = re.sub(r'```$', '', cleaned_json.strip(), flags=re.MULTILINE).strip()

            parsed = json.loads(cleaned_json)
            if isinstance(parsed, list):
                logger.info(f"Successfully extracted {len(parsed)} terms.")
                return parsed
            logger.warning("Extracted output was not a list.")
            return []

        except Exception as e:
            logger.error(f"Glossary extraction failed: {e}")
            return []

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
