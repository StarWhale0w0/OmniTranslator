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
                    input_path, output_path, language, 0, translated_dict, glossary_entries,
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

                # 4.4. Safe Fallback Safeguard: 4회 재시도 실패 시 강제 중단 대신
                #      3단계 세이프가드를 통해 최선 결과를 저장하고 다음 청크로 진행.
                if not gemini_success:
                    last_issue = qc_result.get("issue", "품질 검사 미달") if 'qc_result' in locals() else "Gemini 응답 부재"
                    warn_prefix = f"[품질경고:{last_issue[:40]}]"

                    self.signals.log_emitted.emit(
                        "WARNING",
                        f"⚠️ Chunk #{idx+1}: Gemini {max_gemini_qc_retries}회 재시도 실패 ({last_issue}). "
                        f"3단계 세이프가드 진행..."
                    )
                    logger.warning(
                        f"Chunk #{idx+1}: QC {max_gemini_qc_retries}회 실패 ({last_issue}). "
                        f"Safe Fallback Safeguard 진입."
                    )

                    # ── 세이프가드 1단계: 잔존 한자 → 한글 독음 강제 변환 ───────────────────
                    # best_gemini_candidate가 있고 HANJA 관련 이슈인 경우, 한자를 독음으로 치환
                    safeguard_text = best_gemini_candidate if best_gemini_candidate.strip() else masked_text
                    hanja_in_safe = re.findall(r'[\u4e00-\u9fff]', safeguard_text)
                    if hanja_in_safe and "HANJA" in str(last_issue).upper():
                        # 간이 한자→한글독음 매핑 (중요 무협 관련 자주 출현 한자 중심)
                        _HANJA_KO_READING = {
                            '陽': '양', '剛': '강', '霸': '패', '絕': '절', '陰': '음',
                            '柔': '유', '玄': '현', '逸': '일', '天': '천', '地': '지',
                            '人': '인', '道': '도', '武': '무', '功': '공', '劍': '검',
                            '刀': '도', '拳': '권', '掌': '장', '氣': '기', '力': '력',
                            '神': '신', '魔': '마', '仙': '선', '龍': '용', '虎': '호',
                            '鳳': '봉', '鶴': '학', '雷': '뇌', '火': '화', '水': '수',
                            '風': '풍', '雲': '운', '山': '산', '海': '해', '星': '성',
                            '月': '월', '日': '일', '金': '금', '木': '목', '土': '토',
                            '心': '심', '法': '법', '術': '술', '式': '식', '訣': '결',
                            '境': '경', '界': '계', '宗': '종', '派': '파', '門': '문',
                            '經': '경', '典': '전', '丹': '단', '靈': '영', '寶': '보',
                        }
                        def _hanja_to_reading(ch):
                            return _HANJA_KO_READING.get(ch, ch)

                        converted = re.sub(
                            r'[\u4e00-\u9fff]',
                            lambda m: _hanja_to_reading(m.group(0)),
                            safeguard_text
                        )
                        remaining = re.findall(r'[\u4e00-\u9fff]', converted)
                        if len(remaining) < len(hanja_in_safe):
                            logger.warning(
                                f"Chunk #{idx+1}: [세이프가드-1] 한자 독음 변환 "
                                f"{len(hanja_in_safe) - len(remaining)}자 처리. "
                                f"잔여 {len(remaining)}자."
                            )
                            safeguard_text = converted
                            self.signals.log_emitted.emit(
                                "WARNING",
                                f"Chunk #{idx+1}: [세이프가드-1] 잔존 한자 "
                                f"{len(hanja_in_safe) - len(remaining)}자 독음 변환 적용"
                            )

                    # ── 세이프가드 2단계: FallbackTranslator(구글 번역 등) 최종 시도 ──────────
                    fallback_success = False
                    try:
                        pure_src = TagMasker.unmask_tags(masked_text, tag_map)
                        clean_src_for_fb = QualityChecker.extract_clean_text(pure_src)
                        if clean_src_for_fb.strip():
                            fb_result = await FallbackTranslator.translate_async(
                                clean_src_for_fb,
                                source_lang=language.upper(),
                                target_lang="KO"
                            )
                            if fb_result and fb_result.strip() and fb_result.strip() != clean_src_for_fb.strip():
                                # FallbackTranslator 성공 시 이를 우선 사용
                                safeguard_text = fb_result
                                fallback_success = True
                                logger.warning(
                                    f"Chunk #{idx+1}: [세이프가드-2] FallbackTranslator 번역 성공 "
                                    f"({len(fb_result)}자). 폴백 결과 사용."
                                )
                                self.signals.log_emitted.emit(
                                    "WARNING",
                                    f"Chunk #{idx+1}: [세이프가드-2] FallbackTranslator 폴백 성공 → 다음 청크 계속 진행"
                                )
                    except Exception as fb_err:
                        logger.warning(f"Chunk #{idx+1}: [세이프가드-2] FallbackTranslator 실패: {fb_err}")

                    # ── 세이프가드 3단계: 최선 후보 + 경고 태그 삽입 후 저장, 다음 청크 진행 ──
                    if not fallback_success:
                        # 최선 후보(독음 변환 적용된 safeguard_text)에 경고 태그 삽입
                        remaining_hanja = re.findall(r'[\u4e00-\u9fff]', safeguard_text)
                        if remaining_hanja:
                            safe_note = f"\n<!-- [번역경고] 한자 {len(remaining_hanja)}자 미변환 잔존({last_issue[:60]}) -->\n"
                        else:
                            safe_note = f"\n<!-- [번역경고] QC {max_gemini_qc_retries}회 실패({last_issue[:60]}) -->\n"
                        safeguard_text = safe_note + safeguard_text
                        logger.warning(
                            f"Chunk #{idx+1}: [세이프가드-3] 경고 태그 삽입 후 저장 → 다음 청크 계속 진행."
                        )
                        self.signals.log_emitted.emit(
                            "WARNING",
                            f"Chunk #{idx+1}: [세이프가드-3] 경고 태그 삽입 후 저장 → Chunk #{idx+2}부터 번역 재개"
                        )

                    # 태그 언마스크 & 최종 후처리
                    if fallback_success:
                        # 폴백 결과는 순수 텍스트이므로 원본 태그 구조로 감싸지 않음
                        final_safeguard = safeguard_text
                    else:
                        final_safeguard = TagMasker.unmask_tags(safeguard_text, tag_map)
                    if not is_epub:
                        final_safeguard = TextCleaner.strip_html_tags(final_safeguard)
                    if not final_safeguard.strip():
                        final_safeguard = text_chunk  # 최후 보루: 원문 보존

                    translated_dict[idx] = final_safeguard
                    self.signals.preview_updated.emit(text_chunk, final_safeguard)
                    SessionManager.save_checkpoint(
                        input_path, output_path, language, 0, translated_dict, glossary_entries,
                        toc=toc_entries, book_title=book_title
                    )
                    logger.info(f"Chunk #{idx+1}: 세이프가드 저장 완료. Chunk #{idx+2}부터 계속 진행.")
                    return final_safeguard

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

                # 6. Final Integrity Validation before saving to Checkpoint
                is_valid, invalid_reason = SessionManager.is_chunk_valid(final_translated)
                if not is_valid:
                    abort_reason = f"Chunk #{idx+1} 최종 산출물 무결성 검증 실패: {invalid_reason}"
                    logger.error(f"[FAIL-FAST ABORT] {abort_reason}. 체크포인트 오염 방지를 위해 번역 파이프라인을 즉시 안전 중단합니다.")
                    
                    self.cancel_requested = True
                    self.is_running = False
                    
                    self.signals.log_emitted.emit(
                        "ERROR",
                        f"🚨 [긴급 강제 중단] Chunk #{idx+1}: {invalid_reason}\n"
                        f"데이터 무결성 보호를 위해 작업을 즉시 중단했습니다."
                    )
                    self.signals.status_changed.emit("품질 기준 미달로 안전을 위해 번역 프로세스를 강제 중단합니다")
                    self.signals.completed.emit(
                        False,
                        f"[번역 긴급 중단]\n\n"
                        f"청크 #{idx+1}의 최종 번역문에서 데이터 무결성 결함이 감지되었습니다.\n"
                        f"사유: {invalid_reason}\n\n"
                        f"불량 데이터의 체크포인트 저장을 차단하기 위해 프로세스를 안전하게 강제 중단했습니다."
                    )
                    return None

                # Save pure translation output only (Passed all quality checks)
                translated_dict[idx] = final_translated
                
                # Update UI preview and checkpoint with pure translated text
                self.signals.preview_updated.emit(text_chunk, final_translated)
                SessionManager.save_checkpoint(
                    input_path, output_path, language, 0, translated_dict, glossary_entries,
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

            already_done = len(translated_dict)
            logger.info(
                f"EPUB 청크 사전 집계: 실제 청크 수={total_epub_chunks}, "
                f"체크포인트 완료={already_done}"
            )

            if already_done >= total_epub_chunks:
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
                    if self.cancel_requested:
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
                        if self.cancel_requested or not self.is_running:
                            break
                        res = await translate_single_chunk(g_idx, c_str)
                        if res is None or self.cancel_requested or not self.is_running:
                            break
                        ch_results.append(res)
                        
                        self.signals.progress.emit(
                            len(translated_dict),
                            global_chunk_idx,
                            f"챕터 {ch_idx+1}/{total_chapters} 번역 중... ({len(translated_dict)} 청크 완료)"
                        )

                    if self.cancel_requested or not self.is_running or len(ch_results) < len(ch_tasks):
                        break

                    # HTML DOM reconstruction per chapter
                    rebuilt_html = EpubIO.rebuild_chapter_html(raw_html, ch_results)
                    chapter.set_content(rebuilt_html.encode('utf-8'))

            if not self.cancel_requested and self.is_running:
                self.signals.status_changed.emit("목차(TOC) 및 네비게이션 메타데이터 한국어 동기화 중...")
                logger.info("Synchronizing and applying translated TOC to EPUB and metadata...")
                
                # Apply synchronized TOC & Navigation (toc.ncx, nav.xhtml, book.toc, visual TOC pages, DC title)
                final_toc_meta = EpubIO.save_epub(
                    book=book,
                    output_epub_path=output_path,
                    toc_entries=toc_entries,
                    book_title=book_title,
                    input_file_path=input_path,
                    language="ko",
                    auto_sync_toc=True
                )
                
                # Update checkpoint with final TOC metadata
                SessionManager.update_toc_in_checkpoint(
                    input_file_path=input_path,
                    toc_entries=final_toc_meta,
                    book_title=book.title
                )

        # =========================================================================
        # TXT PARSED WORKFLOW
        # =========================================================================
        else:
            raw_content = TxtIO.read_text_file(input_path)
            txt_chunker = PlainTextChunker()
            chunks = txt_chunker.split_into_chunks(raw_content, max_size=configured_chunk_size)
            total_chunks = len(chunks)

            results = []
            for i in range(total_chunks):
                if self.cancel_requested or not self.is_running:
                    break
                res = await translate_single_chunk(i, chunks[i])
                if res is None or self.cancel_requested or not self.is_running:
                    break
                results.append(res)

            if not self.cancel_requested and self.is_running and len(results) == total_chunks:
                final_text = "\n\n".join(results)
                final_text = TextCleaner.strip_html_tags(final_text)
                TxtIO.write_text_file(output_path, final_text)

        if self.cancel_requested or not self.is_running:
            self.is_running = False
            return

        # Cleanup checkpoint on clean finish
        SessionManager.remove_checkpoint(input_path)

        self.signals.progress.emit(len(translated_dict), len(translated_dict), "번역 완료!")
        self.signals.completed.emit(True, f"성공적으로 번역되었습니다:\n{output_path}")
        self.is_running = False
