"""
OmniTranslator Pro - Fallback Translator Engine
Provides secondary machine translation (GoogleTranslator via deep-translator and direct HTTP endpoint)
when Gemini encounters safety blocks (PROMPT_BLOCKED) or empty responses.
Never returns raw source text on failure; returns None if translation fails.
"""

import asyncio
import json
import re
import urllib.parse
import urllib.request
from typing import Optional, List
from common.logger import setup_logger

logger = setup_logger("FallbackTranslator")

class FallbackTranslator:
    """Secondary fallback translator with multi-stage Google Translate recovery."""

    LANG_MAP = {
        "JA": "ja",
        "ZH": "zh-CN",
        "EN": "en",
        "KO": "ko",
    }

    @classmethod
    def _translate_gtx_sync(cls, text: str, src: str, tgt: str) -> Optional[str]:
        """Translates text using direct Google Translate endpoint with paragraph splitting."""
        if not text or not text.strip():
            return None

        # Split into smaller blocks if text exceeds ~3000 chars to avoid URL length issues
        max_block = 2000
        paragraphs = text.split("\n")
        chunks: List[str] = []
        current = []
        current_len = 0

        for p in paragraphs:
            p_len = len(p) + 1
            if current_len + p_len > max_block and current:
                chunks.append("\n".join(current))
                current = [p]
                current_len = p_len
            else:
                current.append(p)
                current_len += p_len
        if current:
            chunks.append("\n".join(current))

        translated_blocks: List[str] = []
        for block in chunks:
            if not block.strip():
                translated_blocks.append(block)
                continue
            
            encoded_q = urllib.parse.quote(block)
            url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={src}&tl={tgt}&dt=t&q={encoded_q}"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    trans = "".join(part[0] for part in data[0] if part and part[0])
                    translated_blocks.append(trans)
            except Exception as e:
                logger.warning(f"Fallback direct GTX translation failed for block: {e}")
                return None

        full_trans = "\n".join(translated_blocks)
        return full_trans

    @classmethod
    async def translate_async(cls, text: str, source_lang: str = "JA", target_lang: str = "KO") -> Optional[str]:
        """
        Translates text asynchronously using GoogleTranslator and direct GTX fallback.
        Returns:
            translated_text: Clean translated string if successful.
            None: If all translation methods fail (NEVER returns raw source text).
        """
        if not text or not text.strip():
            return text

        src = cls.LANG_MAP.get(source_lang.upper(), "auto")
        tgt = cls.LANG_MAP.get(target_lang.upper(), "ko")

        loop = asyncio.get_running_loop()

        # 1. Attempt deep_translator GoogleTranslator
        try:
            from deep_translator import GoogleTranslator
            def _dt_run():
                translator = GoogleTranslator(source=src, target=tgt)
                return translator.translate(text)

            result = await loop.run_in_executor(None, _dt_run)
            if result and result.strip() and result.strip() != text.strip():
                # Verify that translation actually contains Korean characters
                hangul_count = len(re.findall(r'[\uac00-\ud7af]', result))
                if hangul_count >= 5 or len(result) < 15:
                    logger.info(f"Fallback GoogleTranslator (deep-translator) succeeded: {len(text)} -> {len(result)} chars.")
                    return result
        except Exception as e:
            logger.warning(f"deep_translator GoogleTranslator failed ({e}). Proceeding to direct GTX endpoint...")

        # 2. Attempt direct GTX endpoint as robust secondary channel
        try:
            gtx_result = await loop.run_in_executor(None, lambda: cls._translate_gtx_sync(text, src, tgt))
            if gtx_result and gtx_result.strip() and gtx_result.strip() != text.strip():
                hangul_count = len(re.findall(r'[\uac00-\ud7af]', gtx_result))
                if hangul_count >= 5 or len(gtx_result) < 15:
                    logger.info(f"Fallback GoogleTranslator (direct GTX) succeeded: {len(text)} -> {len(gtx_result)} chars.")
                    return gtx_result
        except Exception as e:
            logger.error(f"Fallback direct GTX endpoint failed: {e}")

        # Translation completely failed - return None to explicitly signal failure
        logger.error(f"All FallbackTranslator channels failed for {len(text)} chars.")
        return None
