"""
OmniTranslator Pro - Fallback Translator Engine
Provides secondary machine translation (GoogleTranslator via deep-translator)
when Gemini encounters safety blocks (PROMPT_BLOCKED) or empty responses.
"""

import asyncio
from typing import Optional
from deep_translator import GoogleTranslator
from common.logger import setup_logger

logger = setup_logger("FallbackTranslator")

class FallbackTranslator:
    """Secondary fallback translator using GoogleTranslator to guarantee zero content drop."""

    LANG_MAP = {
        "JA": "ja",
        "ZH": "zh-CN",
        "EN": "en",
        "KO": "ko",
    }

    @classmethod
    async def translate_async(cls, text: str, source_lang: str = "JA", target_lang: str = "KO") -> str:
        """Translates text asynchronously using GoogleTranslator."""
        if not text or not text.strip():
            return text

        src = cls.LANG_MAP.get(source_lang.upper(), "auto")
        tgt = cls.LANG_MAP.get(target_lang.upper(), "ko")

        loop = asyncio.get_running_loop()
        try:
            translator = GoogleTranslator(source=src, target=tgt)
            result = await loop.run_in_executor(None, lambda: translator.translate(text))
            if result:
                logger.info(f"Fallback GoogleTranslator translated {len(text)} -> {len(result)} chars successfully.")
                return result
            return text
        except Exception as e:
            logger.error(f"Fallback GoogleTranslator failed: {e}")
            return text
