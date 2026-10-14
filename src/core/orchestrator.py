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

        # Live session state tracking for graceful shutdown & flushing
        self.current_input_path: Optional[Path] = None
        self.current_output_path: Optional[Path] = None
        self.current_language: str = "JA"
        self.current_translated_dict: Dict[int, str] = {}
        self.current_glossary_entries: List[Dict[str, Any]] = []
        self.current_toc_entries: List[Dict[str, Any]] = []
        self.current_book_title: Optional[str] = None
        self.current_total_chunks: int = 0

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

    def flush_checkpoint(self) -> None:
        """Immediately flushes in-memory translation progress and checkpoint data to disk."""
        if (
            self.current_input_path and 
            self.current_translated_dict is not None and 
            len(self.current_translated_dict) > 0
        ):
            try:
                out_path = self.current_output_path or (self.current_input_path.parent / f"{self.current_input_path.stem}_translated{self.current_input_path.suffix}")
                SessionManager.save_checkpoint(
                    input_file_path=self.current_input_path,
                    output_file_path=out_path,
                    language=self.current_language or "JA",
                    total_chunks=self.current_total_chunks or 0,
                    translated_chunks=self.current_translated_dict,
                    glossary=self.current_glossary_entries or [],
                    toc=self.current_toc_entries or [],
                    book_title=self.current_book_title
                )
                logger.info(f"💾 Flushed {len(self.current_translated_dict)} chunks to checkpoint on disk.")
            except Exception as e:
                logger.error(f"Failed to flush checkpoint to disk: {e}")

    def pause(self):
        self.is_paused = True
        self.flush_checkpoint()
        self.signals.status_changed.emit("일시 정지됨")

    def resume(self):
        self.is_paused = False
        self.signals.status_changed.emit("번역 재개 중...")

    def cancel(self):
        self.cancel_requested = True
        self.is_running = False
        self.flush_checkpoint()
        self.signals.status_changed.emit("작업 취소 요청됨...")

    def cleanup(self):
        """Cleans up ongoing sessions, key managers, or client pools."""
        if hasattr(self, 'gemini_client') and self.gemini_client:
            try:
                self.gemini_client.close()
            except Exception as e:
                logger.warning(f"Error during gemini_client cleanup: {e}")

    async def extract_glossary_async(self, input_path: Path, language: str):
        """Extracts AI glossary from entire document text asynchronously using Map-Reduce scanner."""
        if not input_path.exists():
            self.signals.log_emitted.emit("ERROR", "용어 추출 실패: 입력 파일이 존재하지 않습니다.")
            return

        # ── [버그 방어] gemini_client None 체크 + Lazy Loading ───────────────────────
        # __init__에서 KeyManager / GeminiClient가 정상 생성되었는지 확인하고,
        # None인 경우 Lazy Loading으로 재생성하여 'NoneType' 오류를 방지함.
        if self.gemini_client is None:
            logger.warning("[Orchestrator] gemini_client가 None입니다. Lazy Loading으로 재생성합니다.")
            try:
                self.key_manager = KeyManager(
                    api_keys=self.config.get("api_keys", []),
                    requests_per_minute=self.config.get("rpm_limit", 60),
                    request_delay=self.config.get("request_delay", 0.5)
                )
                self.gemini_client = GeminiClient(self.key_manager)
                logger.info("[Orchestrator] gemini_client Lazy Loading 성공.")
            except Exception as lazy_err:
                err_msg = f"GeminiClient 초기화 실패: {lazy_err}"
                logger.error(f"[Orchestrator] {err_msg}")
                self.signals.log_emitted.emit("ERROR", f"용어 추출 실패: {err_msg}")
                self.signals.glossary_completed.emit(False, err_msg, 0)
                return

        if not self.config.get("api_keys"):
            err_msg = "API 키가 등록되지 않았습니다. 설정 메뉴에서 Gemini API 키를 등록해주세요."
            self.signals.log_emitted.emit("ERROR", err_msg)
            self.signals.glossary_completed.emit(False, err_msg, 0)
            return

        # ── [버그 방어] language 값 정규화 ────────────────────────────────────────────
        if not language:
            language = self.config.get("source_lang", self.config.get("default_language", "JA"))
            logger.warning(f"[Orchestrator] language 파라미터가 비어 있어 config 기본값 '{language}'로 대체합니다.")
        language = str(language).upper().strip() or "JA"
        # ─────────────────────────────────────────────────────────────────────────────

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
            import traceback as _tb
            full_tb = _tb.format_exc()
            logger.error(f"Glossary extraction pipeline failed: {e}\n[FULL TRACEBACK]\n{full_tb}")
            self.signals.glossary_loading.emit(False, f"추출 실패: {e}")
            # UI 로그에도 전체 traceback 출력 (라인별 분리)
            for tb_line in full_tb.splitlines():
                if tb_line.strip():
                    self.signals.log_emitted.emit("ERROR", f"  {tb_line}")
            self.signals.glossary_completed.emit(False, str(e), 0)

    async def run_pipeline_async(
        self,
        input_path: Path,
        output_path: Path,
        language: str,
        active_glossary: Optional[List[Dict[str, Any]]] = None,
        resume_existing: bool = True
    ) -> Optional[Path]:
        """
        Executes SeaMarine / Novel Batch Translation pipeline:
        Tag Masking -> Pure Image Instant Pass -> Gemini Translation -> 2nd Fallback (GoogleTranslator) -> Tag Unmasking.
        """
        self.is_running = True
        self.is_paused = False
        self.cancel_requested = False

        try:
            return await self._run_pipeline_core(
                input_path=input_path,
                output_path=output_path,
                language=language,
                active_glossary=active_glossary,
                resume_existing=resume_existing
            )
        except asyncio.CancelledError:
            logger.info("번역 파이프라인이 취소되었습니다.")
            self.signals.status_changed.emit("번역 작업이 취소되었습니다.")
            return None
        except Exception as e:
            import traceback as _tb
            full_tb = _tb.format_exc()
            logger.error(f"Translation pipeline failed: {e}\n[FULL TRACEBACK]\n{full_tb}")
            self.signals.status_changed.emit(f"번역 실패: {e}")
            for tb_line in full_tb.splitlines():
                if tb_line.strip():
                    self.signals.log_emitted.emit("ERROR", f"  {tb_line}")
            self.signals.completed.emit(False, f"번역 중 오류가 발생했습니다:\n{e}")
            return None
        finally:
            self.is_running = False
            self.cleanup()

    async def _run_pipeline_core(
        self,
        input_path: Path,
        output_path: Path,
        language: str,
        active_glossary: Optional[List[Dict[str, Any]]] = None,
        resume_existing: bool = True
    ) -> Optional[Path]:
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
        toc_entries: List[Dict[str, Any]] = []
        book_title: Optional[str] = None
        
        # Check existing checkpoint
        if resume_existing:
            ckpt = SessionManager.load_checkpoint(input_path)
            if ckpt:
                translated_dict = ckpt.get("translated_chunks", {})
                toc_entries = ckpt.get("toc", [])
                book_title = ckpt.get("book_title", None)
                if not glossary_entries:
                    glossary_entries = ckpt.get("glossary", [])
                logger.info(f"Resuming job: {len(translated_dict)} chunks already complete, {len(toc_entries)} TOC items loaded.")

        start_time = time.time()
        max_workers = self.config.get("max_workers", 4)
        semaphore = asyncio.Semaphore(max_workers)
        trans_model = self.config.get("translation_model", "gemini-3.1-pro-preview")
        use_glossary = self.config.get("use_dynamic_glossary", True)
        prefill_text = self.config.get("prefill_text", "").strip()
        configured_chunk_size = self.config.get("chunk_size", 2000)

        # Sync live state attributes for immediate disk flush support
        self.current_input_path = input_path
        self.current_output_path = output_path
        self.current_language = language
        self.current_translated_dict = translated_dict
        self.current_glossary_entries = glossary_entries
        self.current_toc_entries = toc_entries
        self.current_book_title = book_title

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

            # 2. Pure Whitespace / Tag-Only / Image / Non-CJK Navigation Instant Pass
            # Condition A: 0 translatable chars (empty/nav/structural tags)
            # Condition B: < 10 translatable chars with media tags (image-only chapter)
            # Condition C: digits/spaces/punctuation ONLY — nav page-number link lists
            #              e.g. "1 2 3 4 … 35", "36 37 … 69" from nav.xhtml
            # Condition D: no CJK source chars, short text, more tags than chars
            #              (structural nav/metadata block with no translatable content)
            _has_media = BaseChunker.has_media_tags(text_chunk)
            _pure_stripped = pure_text.strip()

            _is_digits_only = (
                bool(_pure_stripped) and
                not re.search(
                    r'[^\d\s\.\,\:\;\!\?\-\u2013\u2014\/\(\)\[\]\'\"\u3000\u300c\u300d\u3001\u3002]',
                    _pure_stripped
                )
            )
            _has_cjk_source = bool(
                re.search(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]', _pure_stripped)
            )
            _is_structural_nav = (
                not _has_cjk_source and
                pure_len > 0 and
                pure_len < 200 and
                len(tag_map) > pure_len // 2
            )

            _is_passthrough = (
                (pure_len == 0) or
                (pure_len < 10 and _has_media) or
                _is_digits_only or
                _is_structural_nav
            )
            if _is_passthrough:
                if pure_len == 0:
                    _reason = "순수 공백/태그 전용 구간 (번역 대상 없음)"
                elif pure_len < 10 and _has_media:
                    _reason = f"순수 이미지/미디어 구간 ({pure_len}자 < 10자)"
                elif _is_digits_only:
                    _reason = f"숫자/기호 전용 구간 (nav 페이지 번호, {pure_len}자)"
                else:
                    _reason = f"CJK 원문 없는 구조적 내비게이션 구간 ({pure_len}자)"
                logger.info(
                    f"Chunk #{idx+1}: [즉시 패스스루] {_reason} "
                    f"-> API 호출 없이 원본 즉시 반환"
                )
                self.signals.log_emitted.emit(
                    "INFO",
                    f"Chunk #{idx+1}: [패스스루] {_reason}"
                )
                self.signals.preview_updated.emit(text_chunk, f"[{_reason} - 바이패스됨]")
                translated_dict[idx] = text_chunk
                SessionManager.save_checkpoint(
                    input_path, output_path, language, self.current_total_chunks, translated_dict, glossary_entries,
                    toc=toc_entries, book_title=book_title
                )
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
                best_gemini_candidate = ""
                best_qc_score = -99999.0

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
                            system_instruction=current_sys_instruction
                        )

                        # If Gemini returned empty text
                        if not result_raw or not result_raw.strip() or result_raw.strip() == masked_text.strip():
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
                        # unmask_tags now auto-strips residual [TAG_N] that cannot be mapped
                        test_unmasked = TagMasker.unmask_tags(cleaned, tag_map)

                        # Extra safety: if tag_map is empty (TXT mode) but Gemini hallucinated
                        # [TAG_N] tokens, strip them directly from both cleaned and test_unmasked
                        if not tag_map and TagMasker.has_unmasked_placeholders(test_unmasked):
                            logger.warning(
                                f"Chunk #{idx+1}: TXT 모드 - Gemini가 [TAG_N] 허상 플레이스홀더 출력. "
                                f"직접 제거 후 QC 진행."
                            )
                            test_unmasked = re.sub(
                                r'\[\s*TAG\s*_?\s*\d[\d\s]*\s*\]', '', test_unmasked,
                                flags=re.IGNORECASE
                            ).strip()
                            cleaned = re.sub(
                                r'\[\s*TAG\s*_?\s*\d[\d\s]*\s*\]', '', cleaned,
                                flags=re.IGNORECASE
                            ).strip()

                        qc_result = QualityChecker.inspect_chunk(
                            masked_text, test_unmasked, tag_map_size=len(tag_map)
                        )

                        # Track best Gemini candidate during retries
                        if cleaned.strip() and cleaned != masked_text:
                            cand_score = 100.0
                            if qc_result.get("is_tag_corrupted", False): cand_score -= 40.0
                            if qc_result.get("is_thinking_leak", False): cand_score -= 30.0
                            if qc_result.get("is_content_drop", False): cand_score -= 50.0
                            if qc_result.get("is_repetition", False): cand_score -= 30.0
                            if qc_result.get("is_hallucination", False): cand_score -= 20.0
                            ratio = qc_result.get("ratio", 1.0)
                            cand_score -= abs(ratio - 1.5) * 10.0
                            if cand_score > best_qc_score:
                                best_qc_score = cand_score
                                best_gemini_candidate = cleaned

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

                            if qc_result.get("is_untranslated_hanja", False) or "HANJA" in str(issue):
                                hanja_rule = (
                                    "\n\n[긴급 원문 한자(CJK) 한국어 번역 절대 지침]\n"
                                    "번역문에 원문의 중국어 한자를 단 한 글자도 남겨두지 마십시오. "
                                    "모든 한자를 반드시 한국어(인명은 표준 병음 한글 표기, 지명/사물은 한국식 한자음)로 100% 완전하게 번역하여 출력하십시오."
                                )
                                if hanja_rule not in current_sys_instruction:
                                    current_sys_instruction += hanja_rule

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

                # 4.4. Secondary Fallback: FallbackTranslator (Google Translator via GTX/deep-translator)
                # Gemini 응답 부재 / 품질 미달 시 2차 폴백 번역을 즉시 호출
                if not gemini_success:
                    last_issue = qc_result.get("issue", "품질 검사 미달") if 'qc_result' in locals() else "Gemini 응답 부재"
                    logger.warning(
                        f"Chunk #{idx+1}: Gemini {max_gemini_qc_retries}회 재시도 실패 ({last_issue}). "
                        f"2차 폴백 번역(구글 번역) 즉시 호출..."
                    )
                    self.signals.log_emitted.emit(
                        "WARNING",
                        f"⚠️ Chunk #{idx+1}: Gemini 시도 실패 ({last_issue}) -> 2차 폴백 번역(구글 번역) 호출 중..."
                    )

                    # 1) Try translating masked text with FallbackTranslator to preserve tags
                    fb_trans = await FallbackTranslator.translate_async(
                        masked_text,
                        source_lang=language.upper(),
                        target_lang="KO"
                    )

                    # 2) If masked translation failed or tags corrupt, try unmasked clean source text
                    if not fb_trans or not fb_trans.strip():
                        pure_src = TagMasker.unmask_tags(masked_text, tag_map)
                        clean_src_for_fb = QualityChecker.extract_clean_text(pure_src)
                        if clean_src_for_fb.strip():
                            fb_trans = await FallbackTranslator.translate_async(
                                clean_src_for_fb,
                                source_lang=language.upper(),
                                target_lang="KO"
                            )

                    # 3) Validate Fallback result
                    if fb_trans and fb_trans.strip():
                        fb_unmasked = TagMasker.unmask_tags(fb_trans, tag_map)
                        if not is_epub:
                            fb_unmasked = TextCleaner.strip_html_tags(fb_unmasked)

                        is_fb_valid, fb_invalid_reason = SessionManager.is_chunk_valid(fb_unmasked)
                        if is_fb_valid:
                            logger.info(
                                f"Chunk #{idx+1}: [2차 폴백 성공] 구글 번역 대체 완료 ({len(fb_unmasked)}자)."
                            )
                            self.signals.log_emitted.emit(
                                "INFO",
                                f"Chunk #{idx+1}: [2차 폴백 성공] Gemini 실패 구간을 구글 번역으로 대체 완료."
                            )
                            final_translated = fb_unmasked
                            translated_dict[idx] = final_translated
                            self.signals.preview_updated.emit(text_chunk, final_translated)
                            SessionManager.save_checkpoint(
                                input_path, output_path, language, self.current_total_chunks, translated_dict, glossary_entries,
                                toc=toc_entries, book_title=book_title
                            )
                            return final_translated
                        else:
                            logger.warning(
                                f"Chunk #{idx+1}: 2차 폴백 번역 결과 무결성 검증 탈락 ({fb_invalid_reason})."
                            )

                    # 4.5. All translation channels failed (Gemini + Fallback)
                    # 절대 중국어 원문이나 경고 태그를 저장하지 않고 작업을 안전 일시 정지!
                    logger.error(
                        f"Chunk #{idx+1}: Gemini 및 2차 폴백 번역 모두 실패! "
                        f"원문 오염 저장 방지를 위해 작업을 안전 일시 정지합니다."
                    )
                    self.signals.log_emitted.emit(
                        "ERROR",
                        f"🚨 [번역 일시 정지] Chunk #{idx+1}: Gemini 및 2차 폴백(구글 번역) 모두 응답 불가. "
                        f"중국어 원문 오염 저장을 차단하고 작업을 안전 일시 정지합니다."
                    )
                    self.signals.status_changed.emit(f"Chunk #{idx+1} 번역 실패 (일시 정지됨 - API 키 및 네트워크 확인 필요)")
                    self.pause()
                    return None

                # 4.6. Glossary Post-Correction & Korean Josa Repair
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
                    logger.warning(f"Chunk #{idx+1}: 최종 출력 공백 -> 폴백 번역 시도")
                    fb_rescue = await FallbackTranslator.translate_async(masked_text, source_lang=language.upper(), target_lang="KO")
                    if fb_rescue and fb_rescue.strip():
                        final_translated = TagMasker.unmask_tags(fb_rescue, tag_map)
                    else:
                        final_translated = text_chunk

                # 6. Final Integrity Validation before saving to Checkpoint
                is_valid, invalid_reason = SessionManager.is_chunk_valid(final_translated)
                if not is_valid:
                    logger.warning(
                        f"Chunk #{idx+1}: Gemini 산출물 최종 무결성 검증 탈락 ({invalid_reason}). "
                        f"2차 폴백 번역(구글 번역)으로 긴급 구제 시도..."
                    )
                    fb_rescue = await FallbackTranslator.translate_async(
                        masked_text,
                        source_lang=language.upper(),
                        target_lang="KO"
                    )
                    if fb_rescue and fb_rescue.strip():
                        fb_unmasked = TagMasker.unmask_tags(fb_rescue, tag_map)
                        if not is_epub:
                            fb_unmasked = TextCleaner.strip_html_tags(fb_unmasked)
                        is_fb_valid, _ = SessionManager.is_chunk_valid(fb_unmasked)
                        if is_fb_valid:
                            logger.info(f"Chunk #{idx+1}: 2차 폴백 번역으로 성공적 긴급 구제 완료.")
                            final_translated = fb_unmasked
                            is_valid = True

                if not is_valid:
                    abort_reason = f"Chunk #{idx+1} 최종 산출물 무결성 검증 실패: {invalid_reason}"
                    logger.error(f"[FAIL-FAST] {abort_reason}. 불량 데이터 체크포인트 저장 방지를 위해 작업을 일시 정지합니다.")
                    self.signals.log_emitted.emit(
                        "ERROR",
                        f"🚨 [번역 일시 정지] Chunk #{idx+1}: {invalid_reason}\n"
                        f"체크포인트 오염 보호를 위해 작업을 일시 정지했습니다."
                    )
                    self.signals.status_changed.emit(f"Chunk #{idx+1} 품질 기준 미달로 일시 정지됨")
                    self.pause()
                    return None

                # Save pure translation output only (Passed all quality checks)
                translated_dict[idx] = final_translated
                
                # Update UI preview and checkpoint with pure translated text
                self.signals.preview_updated.emit(text_chunk, final_translated)
                SessionManager.save_checkpoint(
                    input_path, output_path, language, self.current_total_chunks, translated_dict, glossary_entries,
                    toc=toc_entries, book_title=book_title
                )
                return final_translated

        # =========================================================================
        # EPUB PARSED WORKFLOW (SeaMarine chapter reconstruction)
        # =========================================================================
        if is_epub:
            book, chapters = EpubIO.get_epub_chapters(input_path)
            total_chapters = len(chapters)
            
            # Extract initial TOC metadata from EPUB if not yet cached in checkpoint
            if not toc_entries:
                toc_entries = EpubIO.extract_toc_metadata(book)
                logger.info(f"Extracted {len(toc_entries)} initial TOC entries from EPUB.")

            self.signals.status_changed.emit(f"EPUB 챕터 구조 분석 중... (총 {total_chapters}개 챕터)")
            global_chunk_idx = 0

            # ---------------------------------------------------------------
            # Pre-scan: count total chunks from EPUB before starting translation.
            # If checkpoint already covers ALL chunks (translated_dict has more
            # entries than the actual EPUB chunk count), skip the translation loop
            # and go directly to the EPUB rebuild step.  This prevents the
            # "chunk #299 빈 응답/원문 반환" pattern that occurs when chunk_size
            # was changed between runs or when a stale extra index exists in the
            # checkpoint from a previous run.
            # ---------------------------------------------------------------
            total_epub_chunks = 0
            for ch_pre in chapters:
                rc_pre = ch_pre.get_content()
                rh_pre = rc_pre.decode('utf-8', errors='ignore') if isinstance(rc_pre, bytes) else str(rc_pre)
                sp_pre = BeautifulSoup(rh_pre, 'html.parser')
                bd_pre = sp_pre.body if sp_pre.body else sp_pre
                total_epub_chunks += len(
                    DomChunker.chunk_body_preserving_structure(bd_pre, max_chars=configured_chunk_size)
                )

            self.current_total_chunks = total_epub_chunks
            already_done = len(translated_dict)
            logger.info(
                f"EPUB 청크 사전 집계: 실제 청크 수={total_epub_chunks}, "
                f"체크포인트 완료={already_done}"
            )

            if already_done >= total_epub_chunks and total_epub_chunks > 0:
                # All chunks already translated — rebuild EPUB from checkpoint directly.
                logger.info(
                    f"[체크포인트 완전 재개] 체크포인트({already_done}개) >= "
                    f"실제 EPUB 청크 수({total_epub_chunks}개). "
                    f"Gemini 호출 없이 EPUB 재조립 단계로 직행합니다."
                )
                self.signals.log_emitted.emit(
                    "INFO",
                    f"[체크포인트 완전 재개] 모든 청크 번역 완료 확인 "
                    f"({already_done}/{total_epub_chunks}). EPUB 재조립 중..."
                )
                self.signals.status_changed.emit(
                    f"번역 완료 (체크포인트): EPUB 재조립 중... ({already_done}개 청크)"
                )
                # Reconstruct each chapter HTML from checkpoint
                flat_idx = 0
                for ch_rebuild in chapters:
                    rc_r = ch_rebuild.get_content()
                    rh_r = rc_r.decode('utf-8', errors='ignore') if isinstance(rc_r, bytes) else str(rc_r)
                    sp_r = BeautifulSoup(rh_r, 'html.parser')
                    bd_r = sp_r.body if sp_r.body else sp_r
                    ctags_r = DomChunker.chunk_body_preserving_structure(bd_r, max_chars=configured_chunk_size)
                    ch_translated_r = []
                    for _ in ctags_r:
                        ch_translated_r.append(translated_dict.get(flat_idx, str(_)))
                        flat_idx += 1
                    rebuilt_r = EpubIO.rebuild_chapter_html(rh_r, ch_translated_r)
                    ch_rebuild.set_content(rebuilt_r.encode('utf-8'))
            else:
                for ch_idx, chapter in enumerate(chapters):
                    if self.cancel_requested or self.is_paused or not self.is_running:
                        break

                    raw_content = chapter.get_content()
                    raw_html = raw_content.decode('utf-8', errors='ignore') if isinstance(raw_content, bytes) else str(raw_content)
                    soup = BeautifulSoup(raw_html, 'html.parser')
                    body = soup.body if soup.body else soup

                    # DOM preserving recursive chunking
                    chunk_tags = DomChunker.chunk_body_preserving_structure(body, max_chars=configured_chunk_size)
                    
                    ch_tasks = []
                    for chunk_tag in chunk_tags:
                        chunk_str = str(chunk_tag)
                        ch_tasks.append((global_chunk_idx, chunk_str))
                        global_chunk_idx += 1

                    # Execute chapter chunks
                    ch_results = []
                    for g_idx, c_str in ch_tasks:
                        if self.cancel_requested or self.is_paused or not self.is_running:
                            break
                        res = await translate_single_chunk(g_idx, c_str)
                        if res is None or self.cancel_requested or self.is_paused or not self.is_running:
                            break
                        ch_results.append(res)
                        
                        self.signals.progress.emit(
                            len(translated_dict),
                            total_epub_chunks,
                            f"챕터 {ch_idx+1}/{total_chapters} 번역 중... ({len(translated_dict)}/{total_epub_chunks} 청크 완료)"
                        )

                    if self.cancel_requested or self.is_paused or not self.is_running or len(ch_results) < len(ch_tasks):
                        break

                    # HTML DOM reconstruction per chapter
                    rebuilt_html = EpubIO.rebuild_chapter_html(raw_html, ch_results)
                    chapter.set_content(rebuilt_html.encode('utf-8'))

            # ---------------------------------------------------------------
            # EPUB 최종 완료 엄격 검증 (Strict Completion Check)
            # ---------------------------------------------------------------
            is_epub_fully_completed = (
                not self.cancel_requested and
                not self.is_paused and
                self.is_running and
                total_epub_chunks > 0 and
                len(translated_dict) == total_epub_chunks
            )

            if is_epub_fully_completed:
                self.signals.status_changed.emit("목차(TOC) 동기화 및 EPUB 파일 저장 중...")
                logger.info("Synchronizing and applying translated TOC to EPUB and metadata...")
                
                # Apply synchronized TOC & Navigation and write EPUB file asynchronously
                loop = asyncio.get_running_loop()
                final_toc_meta = await loop.run_in_executor(
                    None,
                    lambda: EpubIO.save_epub(
                        book=book,
                        output_epub_path=output_path,
                        toc_entries=toc_entries,
                        book_title=book_title,
                        input_file_path=input_path,
                        language="ko",
                        auto_sync_toc=True
                    )
                )
                
                logger.info(f"🎉 번역 및 EPUB 파일 생성이 완료되었습니다: {output_path}")
                self.signals.log_emitted.emit("INFO", f"🎉 번역 및 EPUB 파일 생성이 완료되었습니다: {output_path}")
                self.signals.status_changed.emit(f"EPUB 파일 저장 완료: {output_path.name}")

                # Update checkpoint with final TOC metadata
                try:
                    book_title_val = getattr(book, 'title', None) or book_title
                    SessionManager.update_toc_in_checkpoint(
                        input_file_path=input_path,
                        toc_entries=final_toc_meta,
                        book_title=book_title_val
                    )
                except Exception as _e_toc:
                    logger.warning(f"체크포인트 TOC 업데이트 건너뜀: {_e_toc}")
            else:
                # 미완성 상태: 절대 save_epub / cleanup_checkpoint을 수행하지 않고 체크포인트 보존
                self.flush_checkpoint()
                self.is_running = False
                done_cnt = len(translated_dict)
                pct = (done_cnt / total_epub_chunks * 100) if total_epub_chunks > 0 else 0
                warn_msg = f"일시정지 또는 미완료 상태로 세션이 저장되었습니다 (완료: {done_cnt}/{total_epub_chunks} 청크, {pct:.1f}%)"
                logger.warning(f"[세션 보존] {warn_msg}. 최종 EPUB 생성 및 체크포인트 정리를 중단하고 체크포인트를 안전하게 보존합니다.")
                self.signals.log_emitted.emit("WARNING", f"⚠️ [미완료 세션 보존] {warn_msg}. 체크포인트가 보존되었습니다.")
                self.signals.status_changed.emit(f"번역 일시정지 또는 미완료 ({done_cnt}/{total_epub_chunks}) - 체크포인트 보존됨")
                return None

        # =========================================================================
        # TXT PARSED WORKFLOW
        # =========================================================================
        else:
            raw_content = TxtIO.read_text_file(input_path)
            txt_chunker = PlainTextChunker()
            chunks = txt_chunker.split_into_chunks(raw_content, max_size=configured_chunk_size)
            total_chunks = len(chunks)
            self.current_total_chunks = total_chunks

            results = []
            for i in range(total_chunks):
                if self.cancel_requested or self.is_paused or not self.is_running:
                    break
                res = await translate_single_chunk(i, chunks[i])
                if res is None or self.cancel_requested or self.is_paused or not self.is_running:
                    break
                results.append(res)
                self.signals.progress.emit(
                    len(translated_dict),
                    total_chunks,
                    f"TXT 번역 중... ({len(translated_dict)}/{total_chunks} 청크 완료)"
                )

            is_txt_fully_completed = (
                not self.cancel_requested and
                not self.is_paused and
                self.is_running and
                total_chunks > 0 and
                len(translated_dict) == total_chunks and
                len(results) == total_chunks
            )

            if is_txt_fully_completed:
                final_text = "\n\n".join(results)
                final_text = TextCleaner.strip_html_tags(final_text)
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, lambda: TxtIO.write_text_file(output_path, final_text))
                logger.info(f"🎉 번역 및 TXT 파일 생성이 완료되었습니다: {output_path}")
                self.signals.log_emitted.emit("INFO", f"🎉 번역 및 TXT 파일 생성이 완료되었습니다: {output_path}")
                self.signals.status_changed.emit(f"TXT 저장 완료: {output_path.name}")
            else:
                self.flush_checkpoint()
                self.is_running = False
                done_cnt = len(translated_dict)
                pct = (done_cnt / total_chunks * 100) if total_chunks > 0 else 0
                warn_msg = f"일시정지 또는 미완료 상태로 세션이 저장되었습니다 (완료: {done_cnt}/{total_chunks} 청크, {pct:.1f}%)"
                logger.warning(f"[세션 보존] {warn_msg}. 최종 TXT 생성 및 체크포인트 정리를 중단하고 체크포인트를 안전하게 보존합니다.")
                self.signals.log_emitted.emit("WARNING", f"⚠️ [미완료 세션 보존] {warn_msg}. 체크포인트가 보존되었습니다.")
                self.signals.status_changed.emit(f"번역 일시정지 또는 미완료 ({done_cnt}/{total_chunks}) - 체크포인트 보존됨")
                return None

        # ---------------------------------------------------------------
        # 최후의 방어선: Strict Completion Guard before cleanup_checkpoint
        # ---------------------------------------------------------------
        expected_total = total_epub_chunks if is_epub else total_chunks
        final_completed_count = len(translated_dict)

        if (
            self.cancel_requested or
            self.is_paused or
            not self.is_running or
            expected_total == 0 or
            final_completed_count != expected_total
        ):
            self.flush_checkpoint()
            self.is_running = False
            guard_msg = f"일시정지 또는 미완료 상태로 세션이 저장되었습니다 (완료: {final_completed_count}/{expected_total} 청크)"
            logger.warning(f"[세션 보존 가드] {guard_msg}. 체크포인트 정리를 차단하고 상태를 보존합니다.")
            self.signals.log_emitted.emit("WARNING", f"⚠️ [세션 보존] {guard_msg}")
            self.signals.status_changed.emit(guard_msg)
            return None

        # 100% 완벽 검증 통과 시에만 임시 체크포인트 정리 실행
        try:
            SessionManager.cleanup_checkpoint(input_path)
            logger.info(f"🧹 번역 100% 완료 ({final_completed_count}/{expected_total}): 임시 체크포인트 및 메타데이터 파일을 정리했습니다.")
            self.signals.log_emitted.emit("INFO", "🧹 번역 완료: 임시 체크포인트 및 메타데이터 파일을 정리했습니다.")
        except Exception as e_clean:
            logger.warning(f"임시 체크포인트 파일 정리 중 경고 (무시됨): {e_clean}")

        self.signals.progress.emit(final_completed_count, expected_total, "번역 완료!")
        self.signals.status_changed.emit("번역 작업이 성공적으로 완료되었습니다.")
        logger.info(f"[INFO] Translation completed successfully: {output_path}")
        self.signals.log_emitted.emit("INFO", f"[INFO] 번역 파이프라인 전체 완료: {output_path.name}")
        self.signals.completed.emit(True, f"성공적으로 번역되었습니다:\n{output_path}")
        self.is_running = False
        return output_path
