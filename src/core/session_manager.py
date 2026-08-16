"""
OmniTranslator Pro - Session & Checkpoint Manager
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from common.paths import get_app_data_path
from common.logger import setup_logger

logger = setup_logger("SessionManager")

class SessionManager:
    """Manages metadata serialization and checkpoint recovery for translation jobs."""

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
        try:
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.debug(f"Checkpoint saved: {meta_path}")
        except Exception as e:
            logger.error(f"Failed to save checkpoint ({meta_path}): {e}")
        return meta_path

    @classmethod
    def load_checkpoint(cls, input_file_path: Path) -> Optional[Dict[str, Any]]:
        meta_path = cls.get_meta_filepath(input_file_path)
        if not meta_path.exists():
            return None
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Convert keys back to integer indices
                if "translated_chunks" in data:
                    data["translated_chunks"] = {int(k): v for k, v in data["translated_chunks"].items()}
                logger.info(f"Loaded existing checkpoint from {meta_path}")
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
