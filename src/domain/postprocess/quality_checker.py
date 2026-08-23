"""
OmniTranslator Pro - Quality Assurance & Omission Detector
Detects content drop (loss of body text), repetition hallucinations, and length anomalies.
"""

import re
import html
from typing import Tuple, Dict, Any, Optional
from bs4 import BeautifulSoup
from common.logger import setup_logger

logger = setup_logger("QualityChecker")

class QualityChecker:
    """Uses length ratio variance, repetition detection, and text presence checks to flag suspected translation defects."""

    @classmethod
    def extract_clean_text(cls, text: str) -> str:
        """Extracts plain text stripped of HTML tags and unescaped."""
        if not text:
            return ""
        if '<' in text:
            try:
                soup = BeautifulSoup(text, 'html.parser')
                return html.unescape(soup.get_text(separator=' ', strip=True))
            except Exception:
                stripped = re.sub(r'<[^>]+>', ' ', text)
                return html.unescape(stripped).strip()
        return html.unescape(text).strip()

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
            clean_l = cls.extract_clean_text(line)
            if len(clean_l) >= 4 and clean_l == prev_line:
                repeat_count += 1
                if repeat_count >= min_repeats:
                    return True, f"동일 라인 {repeat_count}회 연속 반복: '{clean_l[:40]}...'"
            else:
                repeat_count = 1
                prev_line = clean_l

        # 2. Sentence-by-sentence repetition check
        clean_all = cls.extract_clean_text(text)
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
    def count_sentences(cls, text: str) -> int:
        """
        Counts sentences based on terminators (. ! ? 。 ！？ \n) and meaningful clauses.
        """
        if not text:
            return 0
        clean = cls.extract_clean_text(text)
        if not clean:
            return 0
        sentences = [s.strip() for s in re.split(r'[\n.!?。！？]+', clean) if len(s.strip()) > 0]
        return max(len(sentences), 1)

    @classmethod
    def inspect_chunk(cls, source_text: str, translated_text: str) -> Dict[str, Any]:
        """
        Inspects chunk for Content Drop (missing text), repetition loops, sentence bloating, and length mismatch.
        """
        src_text_clean = cls.extract_clean_text(source_text)
        trans_text_clean = cls.extract_clean_text(translated_text)
        src_len = len(src_text_clean)
        trans_len = len(trans_text_clean)

        # If source has no meaningful text, no anomaly
        if src_len == 0:
            return {
                "is_suspicious": False,
                "is_content_drop": False,
                "is_repetition": False,
                "is_hallucination": False,
                "ratio": 0.0,
                "issue": None
            }

        # 1. Content Drop Check: Meaningful source text (>=10 chars) but translated text is empty / empty tag
        if src_len >= 10 and trans_len == 0:
            issue = f"CONTENT_DROP (원문 {src_len}자 존재하나 번역 결과 본문 누락/빈 태그)"
            logger.warning(f"Quality Check Alert: {issue}")
            return {
                "is_suspicious": True,
                "is_content_drop": True,
                "is_repetition": False,
                "is_hallucination": False,
                "ratio": 0.0,
                "issue": issue
            }

        # 2. Extreme Content Drop: Source >= 30 chars but translation < 5 chars
        if src_len >= 30 and trans_len < 5:
            issue = f"CONTENT_DROP (원문 {src_len}자 대비 번역문 {trans_len}자로 극단적 본문 유실)"
            logger.warning(f"Quality Check Alert: {issue}")
            return {
                "is_suspicious": True,
                "is_content_drop": True,
                "is_repetition": False,
                "is_hallucination": False,
                "ratio": trans_len / src_len if src_len > 0 else 0.0,
                "issue": issue
            }

        # 3. Repetition Hallucination Check (3+ consecutive repetitions)
        is_rep, rep_detail = cls.check_consecutive_repetition(translated_text, min_repeats=3)
        src_is_rep, _ = cls.check_consecutive_repetition(source_text, min_repeats=3) if source_text else (False, None)

        if is_rep and not src_is_rep:
            issue = f"REPETITION_HALLUCINATION ({rep_detail})"
            logger.warning(f"Quality Check Alert: {issue}")
            return {
                "is_suspicious": True,
                "is_content_drop": False,
                "is_repetition": True,
                "is_hallucination": True,
                "ratio": trans_len / src_len if src_len > 0 else 0.0,
                "issue": issue
            }

        # 3.5. Unmasked [TAG_N] Placeholder Corruption Check
        if re.search(r'\[\s*TAG\s*_?\s*\d+\s*\]', translated_text, re.IGNORECASE):
            issue = "TAG_UNMASK_CORRUPTED (잔여 [TAG_N] 플레이스홀더 감지)"
            logger.warning(f"Quality Check Alert: {issue}")
            return {
                "is_suspicious": True,
                "is_content_drop": False,
                "is_repetition": False,
                "is_tag_corrupted": True,
                "is_hallucination": False,
                "ratio": trans_len / src_len if src_len > 0 else 0.0,
                "issue": issue
            }

        # 3.6. LLM Thinking / Meta monologue leak check
        if re.search(r'(?:Ah[!,.]?\s*I\s*see|Final\s*Polish\s*of\s*Korean|Ready\s*to\s*output|The\s*prompt\s*got\s*cut\s*off|<think|<thought)', translated_text, re.IGNORECASE):
            issue = "THINKING_LEAK_DETECTED (LLM Thinking 메타 텍스트 유출 감지)"
            logger.warning(f"Quality Check Alert: {issue}")
            return {
                "is_suspicious": True,
                "is_content_drop": False,
                "is_repetition": False,
                "is_thinking_leak": True,
                "is_hallucination": False,
                "ratio": trans_len / src_len if src_len > 0 else 0.0,
                "issue": issue
            }

        # 3.7. Sentence Count Distortion Check (Bloating / Expansion Hallucination)
        src_sents = cls.count_sentences(source_text)
        trans_sents = cls.count_sentences(translated_text)
        sent_diff = trans_sents - src_sents
        sent_ratio = trans_sents / src_sents if src_sents > 0 else 1.0

        if (sent_ratio > 1.8 and sent_diff >= 2) or sent_diff >= 3:
            issue = f"SENTENCE_BLOATING_HALLUCINATION (원문 {src_sents}문장 대비 번역문 {trans_sents}문장으로 급증, +{sent_diff}문장 / 비율 {sent_ratio:.2f}배)"
            logger.warning(f"Quality Check Alert: {issue}")
            return {
                "is_suspicious": True,
                "is_content_drop": False,
                "is_repetition": False,
                "is_hallucination": True,
                "ratio": trans_len / src_len if src_len > 0 else 0.0,
                "issue": issue
            }

        # 4. Length Ratio Anomaly Check
        ratio = trans_len / src_len if src_len > 0 else 1.0
        is_suspicious = False
        is_hallucination = False
        issue = None

        if src_len > 50:
            if ratio < 0.25:
                is_suspicious = True
                issue = f"OMISSION_SUSPECTED (번역문 길이 급감: 비율 {ratio:.2f})"
                logger.warning(f"Quality Check Alert: {issue}")
            elif ratio > 2.2:
                is_suspicious = True
                is_hallucination = True
                issue = f"HALLUCINATION_SUSPECTED (번역문 길이 급증: 비율 {ratio:.2f} > 2.2)"
                logger.warning(f"Quality Check Alert: {issue}")
        else:
            # Short text / dialogue protection (src_len <= 50)
            if src_len >= 5 and (ratio > 3.0 or (trans_len - src_len >= 60) or trans_len > 120):
                is_suspicious = True
                is_hallucination = True
                issue = f"HALLUCINATION_SUSPECTED (단문 대화 대비 번역문 급증: 원문 {src_len}자 -> 번역문 {trans_len}자, 비율 {ratio:.2f})"
                logger.warning(f"Quality Check Alert: {issue}")

        return {
            "is_suspicious": is_suspicious,
            "is_content_drop": False,
            "is_repetition": False,
            "is_hallucination": is_hallucination,
            "ratio": ratio,
            "issue": issue
        }
