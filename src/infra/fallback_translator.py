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
    def is_valid_translation(cls, candidate: Optional[str], original: str, source_lang: str = "JA") -> bool:
        """
        Validates that fallback translation is clean, non-empty, not a raw echo of original text,
        and contains no residual untranslated Japanese characters (Hiragana/Katakana).
        Returns False (rejecting translation) if validation fails.
        """
        if not candidate or not str(candidate).strip():
            return False

        cand_str = str(candidate).strip()
        orig_str = str(original).strip()

        # Clean tags & placeholders for content comparison
        cand_clean = re.sub(r'<[^>]+>', '', cand_str)
        orig_clean = re.sub(r'<[^>]+>', '', orig_str)
        cand_clean = re.sub(r'\[\s*TAG\s*_?\s*\d+\s*\]', '', cand_clean, flags=re.IGNORECASE).strip()
        orig_clean = re.sub(r'\[\s*TAG\s*_?\s*\d+\s*\]', '', orig_clean, flags=re.IGNORECASE).strip()

        # Check if source actually had CJK or translatable text
        orig_has_cjk = bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', orig_clean))
        if not orig_has_cjk:
            # For non-CJK strings (pure numbers, symbols, tags), identical text is acceptable if non-empty
            return bool(cand_clean or cand_str)

        # 1. Exact raw copy check
        if cand_str == orig_str or cand_clean == orig_clean:
            logger.warning("Fallback rejected: translation is exact raw copy of source text.")
            return False

        # 2. Japanese (JA) specific integrity validation
        is_ja = not source_lang or str(source_lang).upper() in ("JA", "JP", "JAPANESE")
        if is_ja:
            jp_matches = re.findall(r'[\u3040-\u309F\u30A0-\u30FF]', cand_clean)
            jp_count = len(jp_matches)
            hangul_matches = re.findall(r'[\uAC00-\uD7AF]', cand_clean)
            hangul_count = len(hangul_matches)

            # Rule: Hiragana/Katakana >= 3 -> reject
            if jp_count >= 3:
                sample_jp = "".join(jp_matches[:10])
                logger.warning(
                    f"Fallback rejected: {jp_count} Hiragana/Katakana characters retained ('{sample_jp}...')"
                )
                return False

            # Rule: Hangul < 10 but Japanese characters exist -> reject
            if hangul_count < 10 and jp_count > 0:
                sample_jp = "".join(jp_matches[:10])
                logger.warning(
                    f"Fallback rejected: Hangul < 10 ({hangul_count}) and Japanese characters exist ({jp_count}: '{sample_jp}...')"
                )
                return False

            # Rule: Source has CJK but translation has zero Hangul
            if hangul_count == 0 and len(orig_clean) > 0:
                logger.warning("Fallback rejected: Source has Japanese/CJK but translation contains 0 Hangul.")
                return False

        return True

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
            if cls.is_valid_translation(result, text, source_lang=source_lang):
                logger.info(f"Fallback GoogleTranslator (deep-translator) succeeded: {len(text)} -> {len(result)} chars.")
                return result
            elif result:
                logger.warning("Fallback deep_translator result rejected due to untranslated/echoed content.")
        except Exception as e:
            logger.warning(f"deep_translator GoogleTranslator failed ({e}). Proceeding to direct GTX endpoint...")

        # 2. Attempt direct GTX endpoint as robust secondary channel
        try:
            gtx_result = await loop.run_in_executor(None, lambda: cls._translate_gtx_sync(text, src, tgt))
            if cls.is_valid_translation(gtx_result, text, source_lang=source_lang):
                logger.info(f"Fallback GoogleTranslator (direct GTX) succeeded: {len(text)} -> {len(gtx_result)} chars.")
                return gtx_result
            elif gtx_result:
                logger.warning("Fallback direct GTX result rejected due to untranslated/echoed content.")
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
                all_parts_valid = True
                temp_parts = []
                for (_, orig_text), trans_p in zip(text_nodes, parts):
                    p_strip = trans_p.strip()
                    if not cls.is_valid_translation(p_strip, orig_text, source_lang=source_lang):
                        all_parts_valid = False
                        break
                    temp_parts.append(p_strip)
                if all_parts_valid:
                    translated_parts = temp_parts

        # If delimiter batching failed, mismatched, or contained invalid parts, fallback to parallel per-node translation
        if not translated_parts:
            logger.info(f"Batch delimiter translation mismatch/invalid. Falling back to concurrent per-node translation ({len(text_nodes)} nodes)...")
            async def _trans_single(txt: str) -> Optional[str]:
                res = await cls.translate_async(txt.strip(), source_lang=source_lang, target_lang=target_lang)
                if res and cls.is_valid_translation(res.strip(), txt, source_lang=source_lang):
                    return res.strip()
                orig_has_cjk = bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', txt))
                if not orig_has_cjk:
                    return res.strip() if res else txt.strip()
                return None

            translated_parts = await asyncio.gather(*[_trans_single(t) for _, t in text_nodes])

        # Validate that no CJK text node failed (never return partial raw Japanese!)
        for (_, orig_text), trans_text in zip(text_nodes, translated_parts):
            orig_has_cjk = bool(re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', orig_text))
            if orig_has_cjk and (trans_text is None or not cls.is_valid_translation(trans_text, orig_text, source_lang=source_lang)):
                logger.warning(
                    f"Fallback HTML translation failed on text node: '{orig_text[:30]}...' -> '{str(trans_text)[:30]}...'"
                )
                return None

        # Replace text in DOM
        for (node, orig_text), trans_text in zip(text_nodes, translated_parts):
            if trans_text is not None:
                leading = orig_text[:len(orig_text) - len(orig_text.lstrip())]
                trailing = orig_text[len(orig_text.rstrip()):]
                node.replace_with(f"{leading}{trans_text}{trailing}")

        result_html = str(soup)
        if not cls.is_valid_translation(result_html, html_content, source_lang=source_lang):
            logger.warning("Fallback translate_html_async generated invalid/untranslated HTML. Returning None.")
            return None

        return result_html
