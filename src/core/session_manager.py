"""
OmniTranslator Pro - Session & Checkpoint Manager
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from common.paths import get_app_data_path
from common.logger import setup_logger

logger = setup_logger("SessionManager")

class SessionManager:
    """Manages metadata serialization, atomic checkpoint recovery, and integrity validation for translation jobs."""

    POLLUTION_REGEX = re.compile(
        r'\[\s*(?:구글\s*폴백|GoogleTranslator\s*폴백|2차\s*폴백|Gemini\s*차단|본문\s*누락|PROMPT_BLOCKED)\s*\]',
        re.IGNORECASE
    )
    THINKING_LEAK_REGEX = re.compile(
        r'(?:'
        r'Ah[!,.]?\s*I\s*see|'
        r'Final\s*Polish\s*of\s*Korean|'
        r'Ready\s*to\s*output|'
        r'The\s*prompt\s*got\s*cut\s*off|'
        r'<(?:think|thought|thinking|reflection)>|'
        r'Here\s+is\s+the\s+(?:Korean\s+)?translation'
        r')',
        re.IGNORECASE
    )
    UNMASKED_TAG_REGEX = re.compile(r'\[\s*TAG\s*_?\s*\d+\s*\]', re.IGNORECASE)

    @classmethod
    def is_chunk_valid(cls, chunk_text: str) -> Tuple[bool, Optional[str]]:
        """
        Validates if a translated chunk is clean and uncontaminated.
        Returns: (is_valid, corruption_reason)
        """
        if not chunk_text or not str(chunk_text).strip():
            return False, "빈 번역 텍스트"

        # Check for system notification pollution (e.g. [구글 폴백])
        if cls.POLLUTION_PATTERN_SEARCH(chunk_text):
            return False, "시스템 알림 문구 오염 ([구글 폴백] 등 감지)"

        # Check for LLM Thinking / Meta monologue leak
        if cls.THINKING_LEAK_REGEX.search(chunk_text):
            return False, "LLM Thinking 메타 텍스트 유출 ('Ah, I see!', 'Final Polish' 등)"

        # Check for unmasked [TAG_N] placeholders
        if cls.UNMASKED_TAG_REGEX.search(chunk_text):
            return False, "미복원된 [TAG_N] 플레이스홀더 잔존"

        return True, None

    @classmethod
    def POLLUTION_PATTERN_SEARCH(cls, text: str) -> bool:
        if not text:
            return False
        return bool(cls.POLLUTION_REGEX.search(text))

    @classmethod
    def sanitize_translated_chunks(cls, chunks: Dict[int, str]) -> Tuple[Dict[int, str], int]:
        """
        Filters out contaminated / corrupted chunks from checkpoint dictionary.
        Returns: (sanitized_dict, purged_count)
        """
        sanitized = {}
        purged_count = 0

        for idx, text in chunks.items():
            valid, reason = cls.is_chunk_valid(text)
            if valid:
                sanitized[idx] = text
            else:
                purged_count += 1
                logger.warning(
                    f"Checkpoint Chunk #{idx+1} is contaminated/corrupted ({reason}). "
                    f"Purging from checkpoint for Gemini re-translation."
                )

        return sanitized, purged_count

    @classmethod
    def get_meta_filepath(cls, input_file_path: Path) -> Path:
        """Returns the .meta.json path for a given input file."""
        return input_file_path.parent / f"{input_file_path.name}.meta.json"

    @classmethod
    def save_checkpoint(
        cls,
        input_file_path: Path,
        output_file_path: Path,
        language: str,
        total_chunks: int,
        translated_chunks: Dict[int, str],
        glossary: List[Dict[str, Any]]
    ) -> Path:
        """Atomic write of checkpoint data into .meta.json."""
        meta_path = cls.get_meta_filepath(input_file_path)
        data = {
            "input_file": str(input_file_path),
            "output_file": str(output_file_path),
            "language": language,
            "total_chunks": total_chunks,
            "processed_count": len(translated_chunks),
            "translated_chunks": {str(k): v for k, v in translated_chunks.items()},
            "glossary": glossary
        }
        
        temp_meta_path = meta_path.with_suffix(".tmp")
        try:
            with open(temp_meta_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            temp_meta_path.replace(meta_path)  # Atomic replace
            logger.debug(f"Atomic Checkpoint saved: {meta_path} ({len(translated_chunks)} chunks)")
        except Exception as e:
            logger.error(f"Failed to save atomic checkpoint ({meta_path}): {e}")
        return meta_path

    @classmethod
    def load_checkpoint(cls, input_file_path: Path) -> Optional[Dict[str, Any]]:
        meta_path = cls.get_meta_filepath(input_file_path)
        if not meta_path.exists():
            return None
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if "translated_chunks" in data:
                    raw_chunks = {int(k): v for k, v in data["translated_chunks"].items()}
                    clean_chunks, purged_count = cls.sanitize_translated_chunks(raw_chunks)
                    data["translated_chunks"] = clean_chunks
                    data["processed_count"] = len(clean_chunks)
                    if purged_count > 0:
                        logger.warning(
                            f"Sanitized checkpoint: {purged_count} contaminated/corrupted chunks purged for re-translation. "
                            f"{len(clean_chunks)} valid chunks retained."
                        )
                logger.info(f"Loaded existing checkpoint from {meta_path} ({data.get('processed_count', 0)} chunks complete)")
                return data
        except Exception as e:
            logger.error(f"Failed to load checkpoint ({meta_path}): {e}")
            return None

    @classmethod
    def remove_checkpoint(cls, input_file_path: Path) -> None:
        meta_path = cls.get_meta_filepath(input_file_path)
        if meta_path.exists():
            try:
                meta_path.unlink()
                logger.info(f"Removed metadata checkpoint: {meta_path}")
            except Exception as e:
                logger.error(f"Failed to remove checkpoint: {e}")
