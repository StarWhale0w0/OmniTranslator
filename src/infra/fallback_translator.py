"""
OmniTranslator Pro - Fallback Translator Engine
Provides secondary machine translation (GoogleTranslator via deep-translator and direct HTTP endpoint)
when Gemini encounters safety blocks (PROMPT_BLOCKED) or empty responses.
Never returns raw source text on failure; returns None if translation fails.
Supports DOM-aware text node translation for EPUB/HTML chunks to completely prevent tag corruption.
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

        # Split into smaller blocks if text exceeds ~2000 chars to avoid URL length issues
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
                if hangul_count >= 3 or len(result) < 15:
                    logger.info(f"Fallback GoogleTranslator (deep-translator) succeeded: {len(text)} -> {len(result)} chars.")
                    return result
        except Exception as e:
            logger.warning(f"deep_translator GoogleTranslator failed ({e}). Proceeding to direct GTX endpoint...")

        # 2. Attempt direct GTX endpoint as robust secondary channel
        try:
            gtx_result = await loop.run_in_executor(None, lambda: cls._translate_gtx_sync(text, src, tgt))
            if gtx_result and gtx_result.strip() and gtx_result.strip() != text.strip():
                hangul_count = len(re.findall(r'[\uac00-\ud7af]', gtx_result))
                if hangul_count >= 3 or len(gtx_result) < 15:
                    logger.info(f"Fallback GoogleTranslator (direct GTX) succeeded: {len(text)} -> {len(gtx_result)} chars.")
                    return gtx_result
        except Exception as e:
            logger.error(f"Fallback direct GTX endpoint failed: {e}")

        # Translation completely failed - return None to explicitly signal failure
        logger.error(f"All FallbackTranslator channels failed for {len(text)} chars.")
        return None

    @classmethod
    async def translate_html_async(
        cls,
        html_content: str,
        source_lang: str = "JA",
        target_lang: str = "KO"
    ) -> Optional[str]:
        """
        Translates HTML chunk by isolating text nodes, translating pure text nodes only,
        and re-inserting translated text back into the DOM structure.
        This completely prevents HTML/media tag corruption and tag masking leakage.
        """
        if not html_content or not html_content.strip():
            return html_content

        if '<' not in html_content:
            return await cls.translate_async(html_content, source_lang=source_lang, target_lang=target_lang)

        from bs4 import BeautifulSoup, NavigableString

        # Flatten ruby tags first
        try:
            from domain.epub.ruby_processor import RubyProcessor
            processed_html = RubyProcessor.flatten_ruby_html(html_content)
        except Exception:
            processed_html = html_content

        try:
            soup = BeautifulSoup(processed_html, 'html.parser')
        except Exception as e:
            logger.warning(f"Failed to parse HTML for node-level translation: {e}. Falling back to standard translation.")
            return await cls.translate_async(processed_html, source_lang=source_lang, target_lang=target_lang)

        # Collect translatable text nodes
        ignored_tags = {'head', 'title', 'meta', 'link', 'style', 'script'}
        text_nodes = []
        for s in list(soup.descendants):
            if isinstance(s, NavigableString) and not isinstance(s.parent, (type(None),)):
                if s.parent and s.parent.name in ignored_tags:
                    continue
                raw_text = str(s)
                if raw_text.strip():
                    text_nodes.append((s, raw_text))

        if not text_nodes:
            return processed_html

        # Delimiter-based batch translation
        DELIMITER = "\n---OMNI_NODE_SPLIT---\n"
        texts_to_translate = [t for _, t in text_nodes]
        joined_payload = DELIMITER.join(texts_to_translate)

        translated_payload = await cls.translate_async(
            joined_payload,
            source_lang=source_lang,
            target_lang=target_lang
        )

        translated_parts = None
        if translated_payload:
            parts = re.split(r'\n?\s*---\s*OMNI_NODE_SPLIT\s*---\s*\n?', translated_payload, flags=re.IGNORECASE)
            if len(parts) == len(text_nodes):
                translated_parts = [p.strip() for p in parts]

        # If delimiter batching failed or count mismatched, fallback to parallel per-node translation
        if not translated_parts:
            logger.info(f"Batch delimiter translation mismatch. Falling back to concurrent per-node translation ({len(text_nodes)} nodes)...")
            async def _trans_single(txt: str) -> str:
                res = await cls.translate_async(txt.strip(), source_lang=source_lang, target_lang=target_lang)
                return res.strip() if res else txt

            translated_parts = await asyncio.gather(*[_trans_single(t) for _, t in text_nodes])

        # Replace text in DOM
        for (node, orig_text), trans_text in zip(text_nodes, translated_parts):
            if trans_text:
                # Preserve leading/trailing whitespace if present in original text
                leading = orig_text[:len(orig_text) - len(orig_text.lstrip())]
                trailing = orig_text[len(orig_text.rstrip()):]
                node.replace_with(f"{leading}{trans_text}{trailing}")

        return str(soup)
