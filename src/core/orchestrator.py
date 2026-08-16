"""
OmniTranslator Pro - Main Orchestrator Engine
Integrates chunking, profile loading, key manager, Gemini calls, and UI signals.
"""

import asyncio
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

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
from domain.glossary.injector import GlossaryInjector
from domain.postprocess.cleaner import TextCleaner
from domain.postprocess.quality_checker import QualityChecker
from ui.signals import TranslationSignals

logger = setup_logger("Orchestrator")

class TranslationOrchestrator(QtCore.QObject):
    """Pipeline orchestrator for whole document translation jobs."""

    def __init__(self, signals: TranslationSignals, config: Dict[str, Any]):
        super().__init__()
        self.signals = signals
        self.config = config
        
        self.is_running = False
        self.is_paused = False
        self.cancel_requested = False

        self.key_manager = KeyManager(
            api_keys=self.config.get("api_keys", []),
            requests_per_minute=self.config.get("rpm_limit", 60)
        )
        self.gemini_client = GeminiClient(self.key_manager)

    def _get_profile(self, lang_code: str):
        lang = lang_code.upper()
        if lang == "ZH":
            return ChineseProfile()
        elif lang == "EN":
            return EnglishProfile()
        return JapaneseProfile()

    def _get_chunker(self, is_epub: bool):
        return EpubDomChunker() if is_epub else TxtChunker()

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

    async def run_pipeline_async(
        self,
        input_path: Path,
        output_path: Path,
        language: str,
        resume_existing: bool = True
    ):
        """Executes full translation pipeline."""
        self.is_running = True
        self.is_paused = False
        self.cancel_requested = False

        self.signals.status_changed.emit("초기화 및 파일 로딩 중...")
        profile = self._get_profile(language)
        is_epub = input_path.suffix.lower() == ".epub"
        chunker = self._get_chunker(is_epub)

        # 1. Load Raw File Content
        if is_epub:
            raw_content = EpubIO.extract_epub_html_content(input_path)
        else:
            raw_content = TxtIO.read_text_file(input_path)

        # 2. Chunking
        max_chunk_size = 2000 if is_epub else 6000
        chunks = chunker.split_into_chunks(raw_content, max_size=max_chunk_size)
        total_chunks = len(chunks)

        translated_dict: Dict[int, str] = {}
        glossary_entries: List[Dict[str, Any]] = []

        # Check existing checkpoint
        if resume_existing:
            ckpt = SessionManager.load_checkpoint(input_path)
            if ckpt and "translated_chunks" in ckpt:
                translated_dict = ckpt["translated_chunks"]
                glossary_entries = ckpt.get("glossary", [])
                logger.info(f"Resuming job: {len(translated_dict)}/{total_chunks} chunks already done.")

        self.signals.progress.emit(len(translated_dict), total_chunks, "번역 준비 완료")

        # 3. Parallel Translation Loop
        start_time = time.time()
        max_workers = self.config.get("max_workers", 4)
        semaphore = asyncio.Semaphore(max_workers)

        async def process_single_chunk(idx: int, text_chunk: str):
            if idx in translated_dict:
                return  # Skip already translated

            async with semaphore:
                while self.is_paused and not self.cancel_requested:
                    await asyncio.sleep(0.5)

                if self.cancel_requested:
                    return

                # Build prompt with Glossary & Prefill
                glossary_context = GlossaryInjector.inject_glossary_context(text_chunk, glossary_entries)
                prompt_str = profile.get_prompt_template().replace("{{slot}}", text_chunk).replace("{{glossary_context}}", glossary_context)

                # Prepare contents & prefill history
                prompt_contents: List[genai_types.Content] = []
                if self.config.get("enable_prefill", True):
                    history_raw = profile.get_prefill_history()
                    for item in history_raw:
                        prompt_contents.append(
                            genai_types.Content(
                                role=item["role"],
                                parts=[genai_types.Part.from_text(text=p) for p in item["parts"]]
                            )
                        )
                prompt_contents.append(
                    genai_types.Content(role="user", parts=[genai_types.Part.from_text(text=prompt_str)])
                )

                try:
                    result_raw = await self.gemini_client.generate_text_async(
                        prompt_contents=prompt_contents,
                        model_name=self.config.get("current_model", "gemini-2.5-flash"),
                        temperature=self.config.get("temperature", 0.7),
                        top_p=self.config.get("top_p", 0.9),
                        system_instruction=profile.get_system_instruction()
                    )

                    # Postprocess Clean
                    cleaned_result = TextCleaner.clean_text(result_raw, profile.get_cleaner_patterns())
                    
                    # Quality Inspection
                    qa_res = QualityChecker.inspect_chunk(text_chunk, cleaned_result)
                    if qa_res["is_suspicious"]:
                        self.signals.log_emitted.emit("WARNING", f"Chunk #{idx+1} QA Warning: {qa_res['issue']}")

                    translated_dict[idx] = cleaned_result
                    
                    # Emit chunk updates
                    processed_count = len(translated_dict)
                    elapsed = time.time() - start_time
                    speed = processed_count / elapsed if elapsed > 0 else 0.1
                    eta_sec = int((total_chunks - processed_count) / speed) if speed > 0 else 0
                    
                    status_msg = f"처리 중 ({processed_count}/{total_chunks}) | 속도: {speed:.1f} 청크/s | ETA: {eta_sec}s"
                    self.signals.progress.emit(processed_count, total_chunks, status_msg)
                    self.signals.preview_updated.emit(text_chunk[:300], cleaned_result[:300])

                    # Save checkpoint
                    SessionManager.save_checkpoint(input_path, output_path, language, total_chunks, translated_dict, glossary_entries)

                except Exception as e:
                    logger.error(f"Error processing chunk #{idx+1}: {e}")
                    self.signals.log_emitted.emit("ERROR", f"Chunk #{idx+1} error: {e}")

        # Execute chunk tasks
        tasks = [process_single_chunk(i, chunks[i]) for i in range(total_chunks)]
        await asyncio.gather(*tasks, return_exceptions=True)

        if self.cancel_requested:
            self.signals.completed.emit(False, "작업이 사용자에 의해 취소되었습니다.")
            return

        # 4. Assembly & Reconstruction
        self.signals.status_changed.emit("최종 파일 조립 및 저장 중...")
        ordered_results = [translated_dict.get(i, chunks[i]) for i in range(total_chunks)]

        if is_epub:
            EpubIO.rebuild_epub(input_path, output_path, ordered_results)
        else:
            final_text = "\n\n".join(ordered_results)
            TxtIO.write_text_file(output_path, final_text)

        # Cleanup checkpoint on clean finish
        SessionManager.remove_checkpoint(input_path)

        self.signals.progress.emit(total_chunks, total_chunks, "번역 완료!")
        self.signals.completed.emit(True, f"성공적으로 번역되었습니다:\n{output_path}")
        self.is_running = False
