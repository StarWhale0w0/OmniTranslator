"""
OmniTranslator Pro - Quality Assurance & Omission Detector
"""

import math
from typing import Tuple, Dict, Any
from common.logger import setup_logger

logger = setup_logger("QualityChecker")

class QualityChecker:
    """Uses length ratio variance to flag suspected translation omissions or hallucinations."""

    @classmethod
    def inspect_chunk(cls, source_text: str, translated_text: str) -> Dict[str, Any]:
        src_len = len(source_text.strip())
        trans_len = len(translated_text.strip())

        if src_len == 0:
            return {"is_suspicious": False, "ratio": 0.0, "issue": None}

        ratio = trans_len / src_len
        is_suspicious = False
        issue = None

        # Thresholds: Ratio < 0.3 implies omission; Ratio > 3.0 implies hallucination
        if ratio < 0.3 and src_len > 50:
            is_suspicious = True
            issue = "OMISSION_SUSPECTED (Translation too short)"
            logger.warning(f"Quality Check Alert: {issue} (ratio={ratio:.2f})")
        elif ratio > 3.0 and src_len > 50:
            is_suspicious = True
            issue = "HALLUCINATION_SUSPECTED (Translation too long)"
            logger.warning(f"Quality Check Alert: {issue} (ratio={ratio:.2f})")

        return {
            "is_suspicious": is_suspicious,
            "ratio": ratio,
            "issue": issue
        }
