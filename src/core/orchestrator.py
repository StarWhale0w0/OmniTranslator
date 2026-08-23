"""
OmniTranslator Pro - Main Orchestrator Engine
Revamped SeaMarine / Novel Batch Translator Pipeline:
1. Tag Masking ([TAG_N] placeholders) isolating media & HTML tags from AI.
2. Instant pass for pure image chapters (< 10 translatable chars).
3. Simplified, censorship-resistant prompts.
4. Secondary fallback translation (GoogleTranslator via deep-translator) on Gemini blocks/errors.
"""

import asyncio
import time
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup
from PySide6 import QtCore
from google.genai import types as genai_types

from common.logger import setup_logger
from core.session_manager import SessionManager
from infra.key_manager import KeyManager
from infra.gemini_client import GeminiClient
from infra.fallback_translator import FallbackTranslator
from infra.epub_io import EpubIO
from infra.txt_io import TxtIO

from domain.profiles.ja_profile import JapaneseProfile
from domain.profiles.zh_profile import ChineseProfile
from domain.profiles.en_profile import EnglishProfile
from domain.chunkers.base_chunker import BaseChunker
from domain.chunkers.dom_chunker import DomChunker, EpubDomChunker
from domain.chunkers.plain_text_chunker import PlainTextChunker, TxtChunker
from domain.glossary.extractor import GlossaryExtractor
from domain.glossary.matcher import GlossaryMatcher
from domain.glossary.injector import GlossaryInjector
from domain.postprocess.cleaner import TextCleaner
from domain.postprocess.quality_checker import QualityChecker
from domain.postprocess.tag_masker import TagMasker
from domain.postprocess.glossary_corrector import GlossaryCorrector
from ui.signals import TranslationSignals


logger = setup_logger("Orchestrator")

class TranslationOrchestrator(QtCore.QObject):
    """Pipeline orchestrator implementing SeaMarine tag masking and multi-tier fallback translation."""

    def __init__(self, signals: TranslationSignals, config: Dict[str, Any]):
        super().__init__()
        self.signals = signals
        self.config = config
        
        self.is_running = False
        self.is_paused = False
        self.cancel_requested = False

        self.key_manager = KeyManager(
            api_keys=self.config.get("api_keys", []),
            requests_per_minute=self.config.get("rpm_limit", 60),
            request_delay=self.config.get("request_delay", 0.5)
        )
        self.gemini_client = GeminiClient(self.key_manager)

    def _get_profile(self, lang_code: str):
        lang = lang_code.upper()
        if lang == "ZH":
            return ChineseProfile()
        elif lang == "EN":
            return EnglishProfile()
        return JapaneseProfile()

    def pause(self):
        self.is_paused = True
        self.signals.status_changed.emit("일시 정지됨")

    def resume(self):
        self.is_paused = False
        self.signals.status_changed.emit("번역 재개 중...")

    def cancel(self):
        self.cancel_requested = True
        self.is_running = False
        self.signals.status_changed.emit("작업 취소 요청됨...")

    async def extract_glossary_async(self, input_path: Path, language: str):
        """Extracts AI glossary from entire document text asynchronously using Map-Reduce scanner."""
        if not input_path.exists():
            self.signals.log_emitted.emit("ERROR", "용어 추출 실패: 입력 파일이 존재하지 않습니다.")
            return

        self.signals.glossary_loading.emit(True, "문서 로드 및 분석 블록 분할 중...")
        self.signals.status_changed.emit("AI 용어집 전수 추출 준비 중...")
        self.signals.log_emitted.emit("INFO", f"AI 전수 용어 추출 시작: {input_path.name}")

        try:
            gloss_model = self.config.get("glossary_model", "gemini-3.1-pro-preview")

            def on_progress(block_idx: int, total_blocks: int, terms_count: int):
                msg = f"[용어집 분석 중] 블록 {block_idx} / {total_blocks} 완료 (현재 수집된 고유명사: {terms_count}개)..."
                self.signals.glossary_loading.emit(True, msg)
                self.signals.status_changed.emit(msg)
                self.signals.log_emitted.emit("INFO", msg)

            entries = await GlossaryExtractor.extract_glossary_from_file_async(
                gemini_client=self.gemini_client,
                file_path=input_path,
                lang_code=language,
                model_name=gloss_model,
                progress_callback=on_progress,
                resume_existing=True
            )

            glossary_file = input_path.parent / f"{input_path.name}.glossary.json"
            GlossaryExtractor.save_glossary_json(entries, glossary_file)

            self.signals.glossary_extracted.emit(entries)
            success_msg = f"용어 총 {len(entries)}개 전수 추출 완료! ({glossary_file.name})"
            self.signals.glossary_loading.emit(False, success_msg)
            self.signals.status_changed.emit(success_msg)
            self.signals.log_emitted.emit("INFO", f"AI 용어 전수 추출 완료: {len(entries)}개 고유명사 저장됨 ({glossary_file.name})")
            self.signals.glossary_completed.emit(True, str(glossary_file), len(entries))

        except Exception as e:
            logger.error(f"Glossary extraction pipeline failed: {e}")
            self.signals.glossary_loading.emit(False, f"추출 실패: {e}")
            self.signals.log_emitted.emit("ERROR", f"용어 추출 중 오류 발생: {e}")
            self.signals.glossary_completed.emit(False, str(e), 0)

    async def run_pipeline_async(
        self,
        input_path: Path,
        output_path: Path,
        language: str,
        active_glossary: Optional[List[Dict[str, Any]]] = None,
        resume_existing: bool = True
    ):
        """
        Executes SeaMarine / Novel Batch Translation pipeline:
        Tag Masking -> Pure Image Instant Pass -> Gemini Translation -> 2nd Fallback (GoogleTranslator) -> Tag Unmasking.
        """
        self.is_running = True
        self.is_paused = False
        self.cancel_requested = False

        self.signals.status_changed.emit("초기화 및 파일 로딩 중...")
        profile = self._get_profile(language)
        is_epub = input_path.suffix.lower() == ".epub"

        # Update KeyManager delay settings
        self.key_manager.set_request_delay(self.config.get("request_delay", 0.5))

        # Retrieve system prompt & custom rules
        prompt_cfg = self.config.get("prompts", {}).get(language.upper(), {})
        base_sys_prompt = prompt_cfg.get("system_prompt", profile.get_system_instruction(is_epub=is_epub))
        custom_rules = prompt_cfg.get("custom_rules", "").strip()

        final_system_instruction = base_sys_prompt
        if custom_rules:
            final_system_instruction += f"\n\n## Custom Rules:\n{custom_rules}"

        strict_meta_rule = (
            "\n\n[출력 절대 규칙]\n"
            "절대로 번역 과정, 검토 메모, 체크리스트 등의 메타 텍스트를 출력하지 마십시오. "
            "오직 최종 번역된 본문 텍스트만을 출력하십시오."
        )
        if "절대로 번역 과정" not in final_system_instruction:
            final_system_instruction += strict_meta_rule

        # Load glossary
        glossary_file = input_path.parent / f"{input_path.name}.glossary.json"
        glossary_entries: List[Dict[str, Any]] = active_glossary if active_glossary is not None else GlossaryExtractor.load_glossary_json(glossary_file)

        translated_dict: Dict[int, str] = {}
        
        # Check existing checkpoint
        if resume_existing:
            ckpt = SessionManager.load_checkpoint(input_path)
            if ckpt and "translated_chunks" in ckpt:
                translated_dict = ckpt["translated_chunks"]
                if not glossary_entries:
                    glossary_entries = ckpt.get("glossary", [])
                logger.info(f"Resuming job: {len(translated_dict)} chunks already complete.")

        start_time = time.time()
        max_workers = self.config.get("max_workers", 4)
        semaphore = asyncio.Semaphore(max_workers)
        trans_model = self.config.get("translation_model", "gemini-3.1-pro-preview")
        use_glossary = self.config.get("use_dynamic_glossary", True)
        prefill_text = self.config.get("prefill_text", "").strip()
        configured_chunk_size = self.config.get("chunk_size", 2000)

        # Helper: Async single chunk translation with SeaMarine Tag Masking & Multi-Key Failover
        async def translate_single_chunk(idx: int, text_chunk: str) -> str:
            if idx in translated_dict:
                cached_text = translated_dict[idx]
                is_valid, reason = SessionManager.is_chunk_valid(cached_text)
                if is_valid:
                    return cached_text
                else:
                    logger.warning(
                        f"Chunk #{idx+1}: 기존 캐시/체크포인트 오염 감지 ({reason}) -> Gemini 재번역 대상으로 초기화"
                    )
                    self.signals.log_emitted.emit(
                        "WARNING",
                        f"Chunk #{idx+1}: [오염 복구] 이전 체크포인트 정합성 실패 ({reason}) -> Gemini 재번역 시작"
                    )
                    del translated_dict[idx]

            # 1. Tag Masking: Isolate HTML/XML/Media tags into [TAG_N] placeholders
            masked_text, tag_map, pure_text = TagMasker.mask_tags(text_chunk)
            pure_len = len(pure_text.strip())

            # 2. Pure Image / Media Instant Pass (< 10 translatable characters)
            if pure_len < 10 and (BaseChunker.has_media_tags(text_chunk) or pure_len == 0):
                logger.info(
                    f"Chunk #{idx+1}: [순수 이미지/미디어 즉시 패스] "
                    f"번역 대상 텍스트 {pure_len}자 (< 10자) -> API 호출 없이 원본 태그 즉시 반환"
                )
                self.signals.log_emitted.emit("INFO", f"Chunk #{idx+1}: [미디어 패스] 순수 이미지/삽화 챕터 즉시 바이패스")
                self.signals.preview_updated.emit(text_chunk, "[표지/삽화 이미지 구간 - 바이패스됨]")
                translated_dict[idx] = text_chunk
                SessionManager.save_checkpoint(input_path, output_path, language, 0, translated_dict, glossary_entries)
                return text_chunk

            async with semaphore:
                while self.is_paused and not self.cancel_requested:
                    await asyncio.sleep(0.5)

                if self.cancel_requested:
                    return text_chunk

                # 3. Dynamic Glossary Injection on masked text (NFKC normalized, Longest Match First)
                glossary_context = GlossaryInjector.inject_glossary_context(
                    masked_text, glossary_entries, enabled=use_glossary, lang_code=language
                )
                prompt_template = profile.get_prompt_template(is_epub=is_epub)
                prompt_str = prompt_template.replace("{{slot}}", masked_text).replace("{{glossary_context}}", glossary_context)

                # Prepare prompt contents
                prompt_contents: List[genai_types.Content] = []
                if self.config.get("enable_prefill", True):
                    history_raw = profile.get_prefill_history(is_epub=is_epub)
                    for item in history_raw:
                        p_text = prefill_text if item["role"] == "model" and prefill_text else item["parts"][0]
                        prompt_contents.append(
                            genai_types.Content(
                                role=item["role"],
                                parts=[genai_types.Part.from_text(text=p_text)]
                            )
                        )
                prompt_contents.append(
                    genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=prompt_str)])
                )

                translated_masked = ""
                gemini_success = False
                current_sys_instruction = final_system_instruction
                max_gemini_qc_retries = 4

                # 4. Primary Translation: Gemini API with Quality-Check Retry & Key Failover Loop
                for gemini_att in range(max_gemini_qc_retries):
                    try:
                        init_temp = self.config.get("temperature", 0.3)
                        result_raw = await self.gemini_client.generate_text_async(
                            prompt_contents=prompt_contents,
                            model_name=trans_model,
                            temperature=init_temp,
                            top_p=self.config.get("top_p", 0.9),
                            thinking_budget=None,
                            system_instruction=current_sys_instruction,
                            raw_fallback_text=masked_text
                        )

                        # If Gemini returned raw fallback or empty text
                        if result_raw == masked_text or not result_raw.strip():
                            logger.warning(
                                f"Chunk #{idx+1}: Gemini 빈 응답/원문 반환 (시도 {gemini_att+1}/{max_gemini_qc_retries}). "
                                f"키 교체 후 Gemini 재시도..."
                            )
                            if gemini_att < max_gemini_qc_retries - 1:
                                self.key_manager.rotate_key(is_rate_limit=False, cooldown_seconds=15.0)
                                await asyncio.sleep(1.0 * (gemini_att + 1))
                                continue
                            else:
                                break

                        cleaned = TextCleaner.clean_text(result_raw, profile.get_cleaner_patterns())
                        
                        # Pre-unmask test to inspect tag integrity
                        test_unmasked = TagMasker.unmask_tags(cleaned, tag_map)
                        qc_result = QualityChecker.inspect_chunk(masked_text, test_unmasked)

                        # If QualityChecker detects any defect (tag corruption, thinking leak, content drop):
                        if qc_result["is_suspicious"]:
                            issue = qc_result.get("issue", "품질 검사 불량")
                            logger.warning(
                                f"Chunk #{idx+1}: Gemini 품질 검사 이상 감지 ({issue}) [시도 {gemini_att+1}/{max_gemini_qc_retries}]. "
                                f"보정 지침 주입 및 키 교체 후 Gemini 재번역 시도..."
                            )
                            self.signals.log_emitted.emit(
                                "WARNING",
                                f"Chunk #{idx+1}: [품질 재시도 {gemini_att+1}/{max_gemini_qc_retries}] {issue} -> 키 교체 후 Gemini 재번역"
                            )

                            # Corrective Prompt Injections
                            if qc_result.get("is_tag_corrupted", False) or "TAG" in str(issue):
                                tag_rule = (
                                    "\n\n[긴급 태그 보존 절대 지침]\n"
                                    "원문의 [TAG_0], [TAG_1] 등의 플레이스홀더를 절대로 누락하거나 태그 안에 공백(예: [TAG_ 0], [TAG_1 3])을 넣지 마십시오. "
                                    "원문 그대로의 [TAG_N] 형식을 정확하게 본문 번역문에 포함하여 출력하십시오."
                                )
                                if tag_rule not in current_sys_instruction:
                                    current_sys_instruction += tag_rule

                            if qc_result.get("is_thinking_leak", False) or "THINKING" in str(issue):
                                thinking_rule = (
                                    "\n\n[긴급 메타 텍스트 금지 절대 지침]\n"
                                    "절대로 'Ah, I see!', 'Final Polish', 'Ready to output' 등의 영어 사고 과정이나 메타 메모를 출력하지 마십시오. "
                                    "오직 최종 한국어 번역 텍스트만을 즉시 출력하십시오."
                                )
                                if thinking_rule not in current_sys_instruction:
                                    current_sys_instruction += thinking_rule

                            if qc_result.get("is_content_drop", False) or "CONTENT_DROP" in str(issue):
                                content_rule = (
                                    "\n\n[긴급 본문 전수 번역 지침]\n"
                                    "원문의 모든 문장과 내용을 단 한 줄도 요약하거나 누락하지 말고 100% 완전하게 번역하십시오."
                                )
                                if content_rule not in current_sys_instruction:
                                    current_sys_instruction += content_rule

                            if qc_result.get("is_hallucination", False) or "HALLUCINATION" in str(issue) or "BLOATING" in str(issue):
                                hallucination_rule = (
                                    "\n\n[긴급 원문 1:1 대조 번역 및 임의 창작 금지 지침]\n"
                                    "원문에 없는 인물의 심리 묘사, 배경 설명, 미언급 대화나 상황을 절대로 임의로 지어내거나 덧붙이지 마십시오. "
                                    "원문의 모든 문장과 정확히 1:1로 대응되도록 엄격하고 절제된 번역문만을 출력하십시오."
                                )
                                if hallucination_rule not in current_sys_instruction:
                                    current_sys_instruction += hallucination_rule

                            if gemini_att < max_gemini_qc_retries - 1:
                                self.key_manager.rotate_key(is_rate_limit=False, cooldown_seconds=15.0)
                                await asyncio.sleep(1.0 * (gemini_att + 1))
                                continue
                            else:
                                break
                        else:
                            # Quality check passed cleanly!
                            translated_masked = cleaned
                            gemini_success = True
                            break

                    except Exception as e:
                        logger.warning(
                            f"Chunk #{idx+1}: Gemini 번역 예외 발생 ({e}) [시도 {gemini_att+1}/{max_gemini_qc_retries}]. 키 교체 후 재시도..."
                        )
                        if gemini_att < max_gemini_qc_retries - 1:
                            self.key_manager.rotate_key(is_rate_limit=False, cooldown_seconds=15.0)
                            await asyncio.sleep(1.0 * (gemini_att + 1))
                            continue
                        else:
                            break

                # 4.4. Extreme Fallback: Only if all Gemini retries and keys completely fail
                if not gemini_success:
                    logger.error(
                        f"Chunk #{idx+1}: Gemini {max_gemini_qc_retries}회 재시도 및 키 순환 모두 실패 -> 최후 수단으로 GoogleTranslator 가동."
                    )
                    self.signals.log_emitted.emit(
                        "WARNING",
                        f"Chunk #{idx+1}: [최후 수단 폴백] Gemini {max_gemini_qc_retries}회 재시도 소진 -> GoogleTranslator 번역 실행"
                    )
                    translated_masked = await FallbackTranslator.translate_async(
                        masked_text, source_lang=language, target_lang="KO"
                    )

                # 4.5. Glossary Post-Correction & Korean Josa Repair
                if glossary_entries and use_glossary:
                    translated_masked = GlossaryCorrector.correct_text(
                        source_text=masked_text,
                        translated_text=translated_masked,
                        glossary_entries=glossary_entries,
                        lang_code=language
                    )

                # 5. Tag Unmasking: Restore [TAG_N] placeholders back to original HTML tags
                final_translated = TagMasker.unmask_tags(translated_masked, tag_map)

                if not is_epub:
                    final_translated = TextCleaner.strip_html_tags(final_translated)

                # Final Safeguard: Ensure non-empty output
                if not final_translated.strip():
                    logger.warning(f"Chunk #{idx+1}: 최종 출력 공백 -> 원문 태그 안전 보존")
                    final_translated = text_chunk

                # Save pure translation output only (Zero text pollution)
                translated_dict[idx] = final_translated
                
                # Update UI preview and checkpoint with pure translated text
                self.signals.preview_updated.emit(text_chunk, final_translated)
                SessionManager.save_checkpoint(input_path, output_path, language, 0, translated_dict, glossary_entries)
                return final_translated

        # =========================================================================
        # EPUB PARSED WORKFLOW (SeaMarine chapter reconstruction)
        # =========================================================================
        if is_epub:
            book, chapters = EpubIO.get_epub_chapters(input_path)
            total_chapters = len(chapters)
            
            self.signals.status_changed.emit(f"EPUB 챕터 구조 분석 중... (총 {total_chapters}개 챕터)")
            global_chunk_idx = 0

            for ch_idx, chapter in enumerate(chapters):
                if self.cancel_requested:
                    break

                raw_html = chapter.get_content().decode('utf-8', errors='ignore')
                soup = BeautifulSoup(raw_html, 'html.parser')
                body = soup.body if soup.body else soup

                # DOM preserving recursive chunking
                chunk_tags = DomChunker.chunk_body_preserving_structure(body, max_chars=configured_chunk_size)
                
                ch_tasks = []
                for chunk_tag in chunk_tags:
                    chunk_str = str(chunk_tag)
                    ch_tasks.append((global_chunk_idx, chunk_str))
                    global_chunk_idx += 1

                # Execute chapter chunks in parallel
                ch_results = []
                for g_idx, c_str in ch_tasks:
                    res = await translate_single_chunk(g_idx, c_str)
                    ch_results.append(res)
                    
                    self.signals.progress.emit(
                        len(translated_dict),
                        global_chunk_idx,
                        f"챕터 {ch_idx+1}/{total_chapters} 번역 중... ({len(translated_dict)} 청크 완료)"
                    )

                # HTML DOM reconstruction per chapter
                rebuilt_html = EpubIO.rebuild_chapter_html(raw_html, ch_results)
                chapter.set_content(rebuilt_html.encode('utf-8'))

            if not self.cancel_requested:
                self.signals.status_changed.emit("최종 EPUB 파일 패키징 중...")
                EpubIO.save_epub(book, output_path)

        # =========================================================================
        # TXT PARSED WORKFLOW
        # =========================================================================
        else:
            raw_content = TxtIO.read_text_file(input_path)
            txt_chunker = PlainTextChunker()
            chunks = txt_chunker.split_into_chunks(raw_content, max_size=configured_chunk_size)
            total_chunks = len(chunks)

            tasks = [translate_single_chunk(i, chunks[i]) for i in range(total_chunks)]
            results = await asyncio.gather(*tasks)

            if not self.cancel_requested:
                final_text = "\n\n".join(results)
                final_text = TextCleaner.strip_html_tags(final_text)
                TxtIO.write_text_file(output_path, final_text)

        if self.cancel_requested:
            self.signals.completed.emit(False, "작업이 사용자에 의해 취소되었습니다.")
            return

        # Cleanup checkpoint on clean finish
        SessionManager.remove_checkpoint(input_path)

        self.signals.progress.emit(len(translated_dict), len(translated_dict), "번역 완료!")
        self.signals.completed.emit(True, f"성공적으로 번역되었습니다:\n{output_path}")
        self.is_running = False
