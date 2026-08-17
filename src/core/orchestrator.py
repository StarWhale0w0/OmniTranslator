"""
OmniTranslator Pro - Main Orchestrator Engine
Integrates seamarine EPUB parsing & DOM reconstruction workflow
with batch_translator Gemini API multi-key async rotation.
"""

import asyncio
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup
from PySide6 import QtCore
from google.genai import types as genai_types

from common.logger import setup_logger
from core.session_manager import SessionManager
from infra.key_manager import KeyManager
from infra.gemini_client import GeminiClient
from infra.epub_io import EpubIO
from infra.txt_io import TxtIO

from domain.profiles.ja_profile import JapaneseProfile
from domain.profiles.zh_profile import ChineseProfile
from domain.profiles.en_profile import EnglishProfile
from domain.chunkers.epub_dom_chunker import EpubDomChunker
from domain.chunkers.txt_chunker import TxtChunker
from domain.glossary.extractor import GlossaryExtractor
from domain.glossary.injector import GlossaryInjector
from domain.postprocess.cleaner import TextCleaner
from domain.postprocess.quality_checker import QualityChecker
from ui.signals import TranslationSignals

logger = setup_logger("Orchestrator")

class TranslationOrchestrator(QtCore.QObject):
    """Pipeline orchestrator combining seamarine EPUB workflow with batch_translator API rotation."""

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
            gloss_model = self.config.get("glossary_model", "gemini-2.5-flash")

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
                progress_callback=on_progress
            )

            glossary_file = input_path.parent / f"{input_path.name}.glossary.json"
            GlossaryExtractor.save_glossary_json(entries, glossary_file)

            self.signals.glossary_extracted.emit(entries)
            success_msg = f"용어 총 {len(entries)}개 전수 추출 완료! ({glossary_file.name})"
            self.signals.glossary_loading.emit(False, success_msg)
            self.signals.status_changed.emit(success_msg)
            self.signals.log_emitted.emit("INFO", f"AI 용어 전수 추출 완료: {len(entries)}개 고유명사 저장됨 ({glossary_file.name})")

        except Exception as e:
            logger.error(f"Glossary extraction pipeline failed: {e}")
            self.signals.glossary_loading.emit(False, f"추출 실패: {e}")
            self.signals.log_emitted.emit("ERROR", f"용어 추출 중 오류 발생: {e}")

    async def run_pipeline_async(
        self,
        input_path: Path,
        output_path: Path,
        language: str,
        active_glossary: Optional[List[Dict[str, Any]]] = None,
        resume_existing: bool = True
    ):
        """Executes translation pipeline combining seamarine EPUB parser with batch_translator API rotation."""
        self.is_running = True
        self.is_paused = False
        self.cancel_requested = False

        self.signals.status_changed.emit("초기화 및 파일 로딩 중...")
        profile = self._get_profile(language)
        is_epub = input_path.suffix.lower() == ".epub"

        # Update KeyManager delay settings
        self.key_manager.set_request_delay(self.config.get("request_delay", 0.5))

        # Retrieve system prompt & custom rules from config
        prompt_cfg = self.config.get("prompts", {}).get(language.upper(), {})
        base_sys_prompt = prompt_cfg.get("system_prompt", profile.get_system_instruction(is_epub=is_epub))
        custom_rules = prompt_cfg.get("custom_rules", "").strip()

        final_system_instruction = base_sys_prompt
        if custom_rules:
            final_system_instruction += f"\n\n## Additional User Custom Rules:\n{custom_rules}"

        # If translating TXT, adjust system instruction to strip HTML mandates and enforce pure text
        if not is_epub:
            final_system_instruction = re.sub(
                r'Do NOT translate, modify, or strip any HTML tags[^\n]*',
                'Translate into pure plain text without HTML tags.',
                final_system_instruction,
                flags=re.IGNORECASE
            )
            final_system_instruction = re.sub(
                r'Return raw HTML only\.?',
                'Return plain novel text only without HTML tags.',
                final_system_instruction,
                flags=re.IGNORECASE
            )
            if "HTML 태그를 일절 생성하지 마십시오" not in final_system_instruction and "순수 소설 텍스트" not in final_system_instruction:
                final_system_instruction += (
                    "\n\n[TXT 포맷 규칙]\n"
                    "본 문서는 순수 텍스트(TXT) 문서입니다. 원문에 없던 <main>, <div>, <p>, <span> 등의 HTML 태그를 일절 생성하지 말고 순수 소설 텍스트로만 출력하십시오."
                )

        strict_meta_rule = (
            "\n\n[출력 절대 규칙]\n"
            "절대로 번역 과정, 검토 메모, 체크리스트, 'Final check' 등의 메타 텍스트를 출력하지 마십시오. "
            "오직 최종 번역된 본문 HTML/텍스트만을 출력하십시오."
        )
        if "절대로 번역 과정" not in final_system_instruction:
            final_system_instruction += strict_meta_rule

        # Load or use passed glossary entries
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
        trans_model = self.config.get("translation_model", "gemini-2.5-flash")
        use_glossary = self.config.get("use_dynamic_glossary", True)
        prefill_text = self.config.get("prefill_text", "").strip()
        configured_chunk_size = self.config.get("chunk_size", 2000)

        # Helper: Async single chunk translation with batch_translator key rotation & retry
        async def translate_single_chunk(idx: int, text_chunk: str) -> str:
            if idx in translated_dict:
                return translated_dict[idx]

            async with semaphore:
                while self.is_paused and not self.cancel_requested:
                    await asyncio.sleep(0.5)

                if self.cancel_requested:
                    return text_chunk

                # Inject dynamic glossary
                glossary_context = GlossaryInjector.inject_glossary_context(
                    text_chunk, glossary_entries, enabled=use_glossary
                )
                prompt_template = profile.get_prompt_template(is_epub=is_epub)
                prompt_str = prompt_template.replace("{{slot}}", text_chunk).replace("{{glossary_context}}", glossary_context)

                # Prepare contents & prefill history
                prompt_contents: List[genai_types.Content] = []
                if self.config.get("enable_prefill", True):
                    history_raw = profile.get_prefill_history(is_epub=is_epub)
                    for item in history_raw:
                        p_text = prefill_text if item["role"] == "model" and prefill_text else item["parts"][0]
                        if not is_epub:
                            p_text = p_text.replace("raw HTML structure", "plain text structure").replace("preserving all HTML tags", "in pure novel prose without HTML tags")
                        prompt_contents.append(
                            genai_types.Content(
                                role=item["role"],
                                parts=[genai_types.Part.from_text(text=p_text)]
                            )
                        )
                prompt_contents.append(
                    genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=prompt_str)])
                )

                try:
                    init_temp = self.config.get("temperature", 0.3)
                    result_raw = await self.gemini_client.generate_text_async(
                        prompt_contents=prompt_contents,
                        model_name=trans_model,
                        temperature=init_temp,
                        top_p=self.config.get("top_p", 0.9),
                        thinking_budget=0,
                        system_instruction=final_system_instruction
                    )

                    cleaned_result = TextCleaner.clean_text(result_raw, profile.get_cleaner_patterns())
                    if not is_epub:
                        cleaned_result = TextCleaner.strip_html_tags(cleaned_result)

                    qc_result = QualityChecker.inspect_chunk(text_chunk, cleaned_result)

                    # Repetition or severe quality failure: Auto-retry with lowered temperature (0.1)
                    if qc_result["is_suspicious"]:
                        logger.warning(
                            f"Chunk #{idx+1} quality check issue ({qc_result['issue']}). "
                            f"Retrying with lower temperature (0.1)..."
                        )
                        self.signals.log_emitted.emit(
                            "WARNING",
                            f"Chunk #{idx+1} 품질 불량 ({qc_result['issue']}) -> 온도 0.1로 자동 재요청(Retry) 중..."
                        )

                        retry_raw = await self.gemini_client.generate_text_async(
                            prompt_contents=prompt_contents,
                            model_name=trans_model,
                            temperature=0.1,
                            top_p=self.config.get("top_p", 0.9),
                            thinking_budget=0,
                            system_instruction=final_system_instruction
                        )
                        retry_cleaned = TextCleaner.clean_text(retry_raw, profile.get_cleaner_patterns())
                        if not is_epub:
                            retry_cleaned = TextCleaner.strip_html_tags(retry_cleaned)
                        retry_qc = QualityChecker.inspect_chunk(text_chunk, retry_cleaned)

                        if not retry_qc["is_suspicious"]:
                            cleaned_result = retry_cleaned
                            logger.info(f"Chunk #{idx+1} quality restored successfully on retry.")
                            self.signals.log_emitted.emit("INFO", f"Chunk #{idx+1} 재시도로 품질 정상 복구 완료.")
                        else:
                            if retry_qc.get("is_repetition"):
                                cleaned_result = TextCleaner.deduplicate_repetitions(retry_cleaned)
                                logger.info(f"Chunk #{idx+1} repetition deduplication fallback applied.")
                            else:
                                cleaned_result = retry_cleaned

                    if not is_epub:
                        cleaned_result = TextCleaner.strip_html_tags(cleaned_result)

                    translated_dict[idx] = cleaned_result
                    
                    processed_count = len(translated_dict)
                    elapsed = time.time() - start_time
                    speed = processed_count / elapsed if elapsed > 0 else 0.1
                    
                    self.signals.preview_updated.emit(text_chunk[:300], cleaned_result[:300])
                    SessionManager.save_checkpoint(input_path, output_path, language, 0, translated_dict, glossary_entries)
                    return cleaned_result

                except Exception as e:
                    logger.error(f"Error processing chunk #{idx+1}: {e}")
                    self.signals.log_emitted.emit("ERROR", f"Chunk #{idx+1} error: {e}")
                    return text_chunk

        # =========================================================================
        # EPUB PARSED WORKFLOW (seamarine)
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

                # seamarine DOM preserving chunking
                chunk_tags = EpubDomChunker.chunk_body_preserving_structure(body, max_chars=configured_chunk_size)
                
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

                # seamarine HTML DOM reconstruction per chapter
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
            txt_chunker = TxtChunker()
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
