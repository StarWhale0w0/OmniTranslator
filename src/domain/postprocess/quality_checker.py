"""
OmniTranslator Pro - Quality Assurance & Omission Detector
"""

import math
from typing import Tuple, Dict, Any
from bs4 import BeautifulSoup
from common.logger import setup_logger

logger = setup_logger("QualityChecker")

class QualityChecker:
    """Uses length ratio variance and text presence checks to flag suspected translation omissions or hallucinations."""

    @classmethod
    def inspect_chunk(cls, source_text: str, translated_text: str) -> Dict[str, Any]:
        src_len = len(source_text.strip())
        trans_len = len(translated_text.strip())

        if src_len == 0:
            return {"is_suspicious": False, "ratio": 0.0, "issue": None}

        # Check text presence inside HTML or plain text
        src_text_clean = BeautifulSoup(source_text, 'html.parser').get_text(strip=True) if "<" in source_text else source_text.strip()
        trans_text_clean = BeautifulSoup(translated_text, 'html.parser').get_text(strip=True) if "<" in translated_text else translated_text.strip()

        if len(src_text_clean) > 20 and len(trans_text_clean) == 0:
            logger.warning("Quality Check Alert: Source text present but translated text empty.")
            return {
                "is_suspicious": True,
                "ratio": 0.0,
                "issue": "EMPTY_TRANSLATION_TEXT (Source text present but translation text empty)"
            }

        ratio = trans_len / src_len
        is_suspicious = False
        issue = None

        # Thresholds: Ratio < 0.3 implies omission; Ratio > 3.0 implies hallucination
        if ratio < 0.3 and len(src_text_clean) > 50:
            is_suspicious = True
            issue = "OMISSION_SUSPECTED (Translation too short)"
            logger.warning(f"Quality Check Alert: {issue} (ratio={ratio:.2f})")
        elif ratio > 3.0 and len(src_text_clean) > 50:
            is_suspicious = True
            issue = "HALLUCINATION_SUSPECTED (Translation too long)"
            logger.warning(f"Quality Check Alert: {issue} (ratio={ratio:.2f})")

        return {
            "is_suspicious": is_suspicious,
            "ratio": ratio,
            "issue": issue
        }
