"""
OmniTranslator Pro - Session & Checkpoint Manager
Manages metadata serialization, atomic checkpoint recovery, TOC synchronization, and integrity validation.
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from common.paths import get_app_data_path
from common.logger import setup_logger

logger = setup_logger("SessionManager")

class SessionManager:
    """Manages metadata serialization, atomic checkpoint recovery, TOC mapping, and integrity validation."""

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
    HANJA_REGEX = re.compile(r'[\u4e00-\u9fff]')

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

        # Reject any chunks with warning tags or uncompleted safeguard markers
        if "<!-- [번역경고]" in chunk_text or "[번역경고]" in chunk_text or "[품질경고:" in chunk_text:
            return False, "번역 실패/미변환 경고 태그 잔존 (<!-- [번역경고] -->)"

        # Check for untranslated Hanja (CJK) ideographs
        clean_body = re.sub(r'<[^>]+>', '', chunk_text)
        clean_body = re.sub(r'\[\s*TAG\s*_?\s*\d+\s*\]', '', clean_body, flags=re.IGNORECASE)
        # Exclude legitimate bracketed Hanja annotations (e.g. 양강패절(陽剛霸絕))
        clean_body_no_brackets = re.sub(
            r'[\uac00-\ud7af]+\s*[\(\（][\u4e00-\u9fff\s]+[\)\）]',
            lambda m: re.sub(r'[\u4e00-\u9fff]', '', m.group(0)),
            clean_body
        )
        hanja_matches = cls.HANJA_REGEX.findall(clean_body_no_brackets)
        hangul_matches = re.findall(r'[\uac00-\ud7af]', clean_body)
        hanja_count = len(hanja_matches)
        hangul_count = len(hangul_matches)

        if hanja_count > 0:
            total_clean_len = len(clean_body.strip())
            hanja_ratio = (hanja_count / total_clean_len) if total_clean_len > 0 else 0.0

            # 1. No Hangul with multiple Hanja characters (completely untranslated raw source)
            if hangul_count < 10 and hanja_count >= 5:
                sample_hanja = "".join(hanja_matches[:10])
                return False, f"한글 부재 및 미번역 원문 한자 {hanja_count}자 잔존 ('{sample_hanja}...')"

            # 2. More Hanja than Hangul (abnormal untranslated state)
            if hanja_count > hangul_count:
                sample_hanja = "".join(hanja_matches[:10])
                return False, f"미번역 한자({hanja_count}자)가 한글({hangul_count}자) 초과 ('{sample_hanja}...')"

            # 3. High Hanja ratio
            if hangul_count >= 30 and hanja_ratio < 0.05 and hangul_count >= hanja_count * 3:
                pass
            elif hanja_count >= 10 or (total_clean_len >= 30 and hanja_ratio >= 0.06):
                sample_hanja = "".join(hanja_matches[:10])
                return False, f"비정상적 미번역 한자 잔존: {hanja_count}자 ({hanja_ratio*100:.1f}%) ('{sample_hanja}...')"

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
                    f"Purging from checkpoint for re-translation."
                )

        return sanitized, purged_count

    @classmethod
    def get_meta_filepath(cls, input_file_path: Path) -> Path:
        """Returns the .meta.json path for a given input file."""
        return input_file_path.parent / f"{input_file_path.name}.meta.json"

    @classmethod
    def _atomic_json_write(cls, target_path: Path, data: Dict[str, Any]) -> bool:
        """
        Safely and atomically writes JSON data to disk on all platforms (including Windows).
        Uses explicit f.flush() + os.fsync() and exponential backoff retry for Windows file locks.
        """
        import os
        import time
        import uuid
        
        target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target_path.parent / f"{target_path.name}.tmp_{os.getpid()}_{uuid.uuid4().hex[:8]}"
        
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            
            # Atomic replace with retry for Windows WinError 32 / 5
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    os.replace(temp_path, target_path)
                    return True
                except (PermissionError, OSError) as pe:
                    if attempt < max_retries - 1:
                        time.sleep(0.05 * (2 ** attempt))
                    else:
                        # Final fallback: copy & remove temp
                        import shutil
                        shutil.copyfile(temp_path, target_path)
                        try:
                            temp_path.unlink()
                        except Exception:
                            pass
                        return True
        except Exception as e:
            logger.error(f"Failed atomic JSON write to {target_path}: {e}")
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            return False

    @classmethod
    def save_checkpoint(
        cls,
        input_file_path: Path,
        output_file_path: Path,
        language: str,
        total_chunks: int,
        translated_chunks: Dict[int, str],
        glossary: List[Dict[str, Any]],
        toc: Optional[List[Dict[str, Any]]] = None,
        book_title: Optional[str] = None
    ) -> Path:
        """Atomic and synchronized write of checkpoint data including TOC and title metadata into .meta.json."""
        meta_path = cls.get_meta_filepath(input_file_path)
        data = {
            "input_file": str(input_file_path),
            "output_file": str(output_file_path),
            "language": language,
            "book_title": book_title,
            "total_chunks": total_chunks,
            "processed_count": len(translated_chunks),
            "toc": toc or [],
            "translated_chunks": {str(k): v for k, v in translated_chunks.items()},
            "glossary": glossary
        }
        
        success = cls._atomic_json_write(meta_path, data)
        if success:
            logger.debug(f"Atomic Checkpoint saved & synced: {meta_path} ({len(translated_chunks)} chunks, {len(data['toc'])} TOC items)")
            # Create a backup mirror (.meta.json.bak) to guarantee disaster recovery
            try:
                import shutil
                bak_path = meta_path.with_name(f"{meta_path.name}.bak")
                shutil.copyfile(meta_path, bak_path)
            except Exception as _be:
                logger.debug(f"Checkpoint backup mirror creation skipped: {_be}")
        return meta_path

    @classmethod
    def load_checkpoint(cls, input_file_path: Path) -> Optional[Dict[str, Any]]:
        """Loads and sanitizes existing checkpoint from .meta.json, with automatic fallback to .bak."""
        meta_path = cls.get_meta_filepath(input_file_path)
        if not meta_path.exists():
            bak_path = meta_path.with_name(f"{meta_path.name}.bak")
            if bak_path.exists():
                logger.info(f"기본 체크포인트 파일 부재 -> 백업본({bak_path.name})으로부터 자동 복구 및 로드 시도.")
                meta_path = bak_path
            else:
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
                        # Immediately persist sanitized state back to disk so purged chunks stay purged
                        cls._atomic_json_write(meta_path, {
                            **data,
                            "translated_chunks": {str(k): v for k, v in clean_chunks.items()},
                            "processed_count": len(clean_chunks)
                        })
                        logger.info(f"Persisted sanitized checkpoint to {meta_path} (purged {purged_count} chunks).")
                logger.info(
                    f"Loaded existing checkpoint from {meta_path} "
                    f"({data.get('processed_count', 0)} chunks, {len(data.get('toc', []))} TOC items)"
                )
                return data
        except Exception as e:
            logger.error(f"Failed to load checkpoint ({meta_path}): {e}")
            return None

    @classmethod
    def update_toc_in_checkpoint(
        cls,
        input_file_path: Path,
        toc_entries: List[Dict[str, Any]],
        book_title: Optional[str] = None
    ) -> bool:
        """Updates only the TOC and book_title in an existing .meta.json file."""
        meta_path = cls.get_meta_filepath(input_file_path)
        if not meta_path.exists():
            return False
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data["toc"] = toc_entries
            if book_title:
                data["book_title"] = book_title
            
            success = cls._atomic_json_write(meta_path, data)
            if success:
                logger.info(f"Updated TOC entries ({len(toc_entries)} items) in checkpoint: {meta_path}")
            return success
        except Exception as e:
            logger.error(f"Failed to update TOC in checkpoint ({meta_path}): {e}")
            return False

    @classmethod
    def cleanup_checkpoint(cls, input_file_path: Path) -> List[Path]:
        """
        Safely removes all temporary metadata and checkpoint files associated with input_file_path.
        Guarantees that *.glossary.json is NEVER deleted as it is a permanent asset.
        Returns the list of successfully removed file paths.
        """
        parent_dir = input_file_path.parent
        fname = input_file_path.name
        fstem = input_file_path.stem

        # Explicit candidate paths
        candidate_paths = {
            cls.get_meta_filepath(input_file_path),
            cls.get_meta_filepath(input_file_path).with_suffix(".tmp"),
            parent_dir / f"{fname}.meta.tmp",
            parent_dir / f"{fname}.checkpoint.json",
            parent_dir / f"{fname}.checkpoint.tmp",
            parent_dir / f"{fstem}.meta.json",
            parent_dir / f"{fstem}.checkpoint.json",
        }

        # Dynamic search in parent directory for matching temp/checkpoint files
        try:
            for p in parent_dir.glob(f"{fname}*.meta*"):
                candidate_paths.add(p)
            for p in parent_dir.glob(f"{fname}*.checkpoint*"):
                candidate_paths.add(p)
        except Exception as glob_err:
            logger.warning(f"Failed to glob temporary files in {parent_dir}: {glob_err}")

        removed_files: List[Path] = []
        for target in candidate_paths:
            # 절대 삭제 금지: *.glossary.json (영구 보존 자산) 및 *.bak (재해 복구용 최후 백업본)
            if target.name.endswith(".glossary.json") or target.name.endswith(".bak"):
                continue

            try:
                if target.exists() and target.is_file():
                    target.unlink()
                    removed_files.append(target)
                    logger.debug(f"Removed temporary checkpoint file: {target}")
            except Exception as e:
                logger.warning(f"Could not remove temporary checkpoint file ({target}): {e}")

        if removed_files:
            logger.info(f"Cleaned up {len(removed_files)} temporary checkpoint file(s) for {fname}")
        return removed_files

    @classmethod
    def remove_checkpoint(cls, input_file_path: Path) -> None:
        """Removes metadata checkpoint file (delegates to cleanup_checkpoint)."""
        cls.cleanup_checkpoint(input_file_path)
