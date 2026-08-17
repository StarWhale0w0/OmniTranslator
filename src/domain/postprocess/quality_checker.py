"""
OmniTranslator Pro - Quality Assurance & Omission Detector
"""

import re
import math
from typing import Tuple, Dict, Any, Optional
from bs4 import BeautifulSoup
from common.logger import setup_logger

logger = setup_logger("QualityChecker")

class QualityChecker:
    """Uses length ratio variance, repetition detection, and text presence checks to flag suspected translation defects."""

    @classmethod
    def check_consecutive_repetition(cls, text: str, min_repeats: int = 3) -> Tuple[bool, Optional[str]]:
        """
        Detects if identical lines, sentences, or phrases repeat 3 or more times consecutively.
        Returns (is_repetition, description).
        """
        if not text:
            return False, None

        # 1. Line-by-line repetition check
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        repeat_count = 1
        prev_line = None
        for line in lines:
            clean_l = BeautifulSoup(line, 'html.parser').get_text(strip=True) if '<' in line else line
            if len(clean_l) >= 4 and clean_l == prev_line:
                repeat_count += 1
                if repeat_count >= min_repeats:
                    return True, f"동일 라인 {repeat_count}회 연속 반복: '{clean_l[:40]}...'"
            else:
                repeat_count = 1
                prev_line = clean_l

        # 2. Sentence-by-sentence repetition check
        clean_all = BeautifulSoup(text, 'html.parser').get_text(separator='\n', strip=True) if '<' in text else text
        sentences = [s.strip() for s in re.split(r'[\n.!?。！？]+', clean_all) if len(s.strip()) >= 4]
        repeat_count = 1
        prev_sent = None
        for sent in sentences:
            if sent == prev_sent:
                repeat_count += 1
                if repeat_count >= min_repeats:
                    return True, f"동일 문장 {repeat_count}회 연속 반복: '{sent[:40]}...'"
            else:
                repeat_count = 1
                prev_sent = sent

        # 3. Substring repeating phrase check (e.g. repeated loops >= 4 chars)
        match = re.search(r'([^\s\n<>]{4,}[^\n<>]*?)\s*(?:\1\s*){2,}', clean_all)
        if match:
            rep_text = match.group(1).strip()
            if len(rep_text) >= 4:
                return True, f"동일 구문 3회 이상 연속 반복: '{rep_text[:40]}...'"

        return False, None

    @classmethod
    def inspect_chunk(cls, source_text: str, translated_text: str) -> Dict[str, Any]:
        src_len = len(source_text.strip())
        trans_len = len(translated_text.strip())

        if src_len == 0:
            return {"is_suspicious": False, "ratio": 0.0, "issue": None, "is_repetition": False}

        # Check text presence inside HTML or plain text
        src_text_clean = BeautifulSoup(source_text, 'html.parser').get_text(strip=True) if "<" in source_text else source_text.strip()
        trans_text_clean = BeautifulSoup(translated_text, 'html.parser').get_text(strip=True) if "<" in translated_text else translated_text.strip()

        if len(src_text_clean) > 20 and len(trans_text_clean) == 0:
            logger.warning("Quality Check Alert: Source text present but translated text empty.")
            return {
                "is_suspicious": True,
                "ratio": 0.0,
                "issue": "EMPTY_TRANSLATION_TEXT (Source text present but translation text empty)",
                "is_repetition": False
            }

        # Repetition Hallucination Check (3+ consecutive repetitions)
        is_rep, rep_detail = cls.check_consecutive_repetition(translated_text, min_repeats=3)
        src_is_rep, _ = cls.check_consecutive_repetition(source_text, min_repeats=3) if source_text else (False, None)

        if is_rep and not src_is_rep:
            issue = f"REPETITION_HALLUCINATION ({rep_detail})"
            logger.warning(f"Quality Check Alert: {issue}")
            return {
                "is_suspicious": True,
                "ratio": trans_len / src_len if src_len > 0 else 0.0,
                "issue": issue,
                "is_repetition": True
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
            "issue": issue,
            "is_repetition": False
        }
