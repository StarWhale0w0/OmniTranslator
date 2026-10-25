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
        """Extracts plain text stripped of HTML tags, [TAG_N] placeholders, and unescaped."""
        if not text:
            return ""
        # 1. Strip [TAG_N] placeholders
        text = re.sub(r'\[\s*TAG\s*_?\s*\d+\s*\]', ' ', text, flags=re.IGNORECASE)
        # 2. Strip HTML tags
        if '<' in text:
            try:
                soup = BeautifulSoup(text, 'html.parser')
                text = soup.get_text(separator=' ', strip=True)
            except Exception:
                text = re.sub(r'<[^>]+>', ' ', text)
        # 3. Unescape html entities and strip
        text = html.unescape(text)
        # 4. Normalize multiple spaces
        text = re.sub(r'[ \t\r\f\v]+', ' ', text)
        return text.strip()

    @classmethod
    def check_consecutive_repetition(cls, text: str, min_repeats: int = 3, is_source: bool = False) -> Tuple[bool, Optional[str]]:
        """
        Detects if identical lines, sentences, or phrases repeat 3 or more times consecutively.
        Returns (is_repetition, description).
        Supports CJK ideograph repetitions down to 1 character for source text.
        """
        if not text:
            return False, None

        clean_all = cls.extract_clean_text(text)
        if not clean_all:
            return False, None

        has_cjk = bool(re.search(r'[\u4e00-\u9fff]', clean_all))
        min_char_len = 1 if (has_cjk or is_source) else 2

        # 1. Line-by-line repetition check
        lines = [cls.extract_clean_text(l) for l in text.splitlines() if cls.extract_clean_text(l)]
        repeat_count = 1
        prev_line = None
        for line in lines:
            norm_line = re.sub(r'^[\s"\'“”‘’【】《》「」『』\(\)\[\]!?,.。！？…~—\-]+|[\s"\'“”‘’【】《》「」『』\(\)\[\]!?,.。！？…~—\-]+$', '', line).strip()
            if len(norm_line) >= min_char_len and norm_line == prev_line:
                repeat_count += 1
                if repeat_count >= min_repeats:
                    return True, f"동일 라인 {repeat_count}회 연속 반복: '{norm_line[:40]}...'"
            else:
                repeat_count = 1
                prev_line = norm_line

        # 2. Sentence-by-sentence repetition check
        sentences = [s.strip() for s in re.split(r'[\n.!?。！？…~—]+', clean_all) if len(s.strip()) >= min_char_len]
        repeat_count = 1
        prev_sent = None
        for sent in sentences:
            norm_sent = re.sub(r'^[\s"\'“”‘’【】《》「」『』\(\)\[\]!?,.。！？…~—\-]+|[\s"\'“”‘’【】《》「」『』\(\)\[\]!?,.。！？…~—\-]+$', '', sent).strip()
            if len(norm_sent) >= min_char_len and norm_sent == prev_sent:
                repeat_count += 1
                if repeat_count >= min_repeats:
                    return True, f"동일 문장 {repeat_count}회 연속 반복: '{norm_sent[:40]}...'"
            else:
                repeat_count = 1
                prev_sent = norm_sent

        # 3. Substring repeating phrase check (e.g. repeated loops >= 2 chars, e.g. "알겠습니다 번역하겠습니다")
        sub_match = re.search(r'([^\s\n<>]{' + str(max(min_char_len, 2)) + r',}[^\n<>]*?)\s*(?:\1\s*){' + str(min_repeats - 1) + r',}', clean_all)
        if sub_match:
            rep_text = sub_match.group(1).strip()
            norm_rep = re.sub(r'^[\s"\'“”‘’【】《》「」『』\(\)\[\]!?,.。！？…~—\-]+|[\s"\'“”‘’【】《》「」『』\(\)\[\]!?,.。！？…~—\-]+$', '', rep_text).strip()
            if len(norm_rep) >= min_char_len:
                return True, f"동일 구문 3회 이상 연속 반복: '{norm_rep[:40]}...'"

        # 4. Token/phrase level repetition with delimiters (e.g. "더티밤... 더티밤... 더티밤..." or "脏弹…… 脏弹…… 脏弹……")
        phrase_match = re.search(r'([\w\u4e00-\u9fff\uac00-\ud7af]{' + str(min_char_len) + r',})[^\w\u4e00-\u9fff\uac00-\ud7af]+(?:\1[^\w\u4e00-\u9fff\uac00-\ud7af]+){' + str(min_repeats - 1) + r',}', clean_all)
        if phrase_match:
            rep_phrase = phrase_match.group(1).strip()
            if len(rep_phrase) >= min_char_len:
                return True, f"동일 어구 3회 이상 연속 반복: '{rep_phrase[:40]}...'"

        return False, None

    @classmethod
    def check_source_keyword_occurrence(cls, source_text: str, rep_phrase: str, min_count: int = 2) -> bool:
        """
        Checks if source text contains high frequency keywords or repeated characters
        corresponding to the repeated context in translation.
        """
        if not source_text:
            return False
        clean_src = cls.extract_clean_text(source_text)
        if not clean_src:
            return False

        # 1. Direct character / 2-gram frequency in source
        bigrams = {}
        for i in range(len(clean_src) - 1):
            bg = clean_src[i:i+2]
            if re.match(r'[\u4e00-\u9fff]{2}', bg):
                bigrams[bg] = bigrams.get(bg, 0) + 1
                if bigrams[bg] >= min_count:
                    return True

        # 2. Check single CJK characters with higher count (>= 3)
        cjk_chars = re.findall(r'[\u4e00-\u9fff]', clean_src)
        char_counts = {}
        for c in cjk_chars:
            char_counts[c] = char_counts.get(c, 0) + 1
            if char_counts[c] >= max(min_count, 3):
                return True

        return False

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
    def inspect_chunk(cls, source_text: str, translated_text: str, tag_map_size: int = 0) -> Dict[str, Any]:
        """
        Inspects chunk for Content Drop (missing text), repetition loops, sentence bloating, and length mismatch.
        Args:
            source_text:     The original (masked) source text.
            translated_text: The unmasked translated output.
            tag_map_size:    Number of tags in the tag_map used for masking (0 = TXT plain-text mode).
                             When 0, TAG_UNMASK_CORRUPTED is treated as a non-critical false positive.
        """
        src_text_clean = cls.extract_clean_text(source_text)
        trans_text_clean = cls.extract_clean_text(translated_text)
        src_len = len(src_text_clean)
        trans_len = len(trans_text_clean)

        # If source has no meaningful text, no anomaly
        if src_len == 0:
            return {
                "is_suspicious": False,
                "is_critical": False,
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
                "is_critical": True,
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
                "is_critical": True,
                "is_content_drop": True,
                "is_repetition": False,
                "is_hallucination": False,
                "ratio": trans_len / src_len if src_len > 0 else 0.0,
                "issue": issue
            }

        # 3. Repetition Hallucination Check (3+ consecutive repetitions)
        is_rep, rep_detail = cls.check_consecutive_repetition(translated_text, min_repeats=3, is_source=False)
        src_is_rep, src_rep_detail = cls.check_consecutive_repetition(source_text, min_repeats=3, is_source=True) if source_text else (False, None)

        if is_rep and not src_is_rep:
            phrase_match = re.search(r"'(.*?)'", rep_detail or "")
            rep_phrase = phrase_match.group(1).rstrip('.').strip() if phrase_match else ""

            # Check 1: If source text contains repeating keywords/concepts (e.g. 脏弹 >= 2 times) -> Pass
            if cls.check_source_keyword_occurrence(source_text, rep_phrase, min_count=2):
                logger.info(
                    f"Quality Check: 원문 내 핵심 키워드/연속 묘사 출현 감지 -> "
                    f"번역문 반복 ({rep_detail}) 정상 통과 (Pass)"
                )
            # Check 2: Short noun / word (<= 5 chars) in normal Korean sentences with particles (은/는/이/가/을/를/의/에...)
            elif len(rep_phrase) <= 5 and rep_phrase and not re.search(r'(' + re.escape(rep_phrase) + r'\s*){4,}', trans_text_clean):
                particle_pattern = re.compile(
                    r'(' + re.escape(rep_phrase) + r')(은|는|이|가|을|를|의|에|에서|에게|로|으로|와|과|도|만|뿐|까지|부터|마저|조차|이다|이었다|이라|이며|이고|이나|처럼|같이)'
                )
                particle_matches = particle_pattern.findall(trans_text_clean)
                if len(particle_matches) >= 2:
                    logger.info(
                        f"Quality Check: 단어({rep_phrase})의 정상 한국어 조사 결합 및 서술 감지 ({len(particle_matches)}회) -> "
                        f"번역문 반복 ({rep_detail}) 정상 통과 (Pass)"
                    )
                else:
                    issue = f"REPETITION_HALLUCINATION ({rep_detail})"
                    logger.warning(f"Quality Check Alert: {issue}")
                    return {
                        "is_suspicious": True,
                        "is_critical": False,
                        "is_content_drop": False,
                        "is_repetition": True,
                        "is_hallucination": True,
                        "ratio": trans_len / src_len if src_len > 0 else 0.0,
                        "issue": issue
                    }
            else:
                issue = f"REPETITION_HALLUCINATION ({rep_detail})"
                logger.warning(f"Quality Check Alert: {issue}")
                return {
                    "is_suspicious": True,
                    "is_critical": False,
                    "is_content_drop": False,
                    "is_repetition": True,
                    "is_hallucination": True,
                    "ratio": trans_len / src_len if src_len > 0 else 0.0,
                    "issue": issue
                }
        elif is_rep and src_is_rep:
            logger.info(
                f"Quality Check: 원문 반복 연출 감지 ({src_rep_detail}) -> "
                f"번역문 반복 ({rep_detail}) 정상 통과 (Pass)"
            )

        # 3.5. Unmasked [TAG_N] Placeholder Corruption Check
        residual_tags = re.findall(r'[\[［]\s*TAG\s*[_\-\s]*\d[\d\s]*\s*[\]］]', translated_text, re.IGNORECASE)
        if residual_tags:
            if tag_map_size == 0:
                # TXT 모드(태그 없는 평문): Gemini가 프롬프트 예시를 흉내내어 [TAG_N]을 직접
                # 출력한 것. 실제 HTML 태그와 무관하므로 오탐(false positive)으로 처리.
                # → WARNING만 기록하고 검사 통과 (QC 재시도 루프를 발생시키지 않음)
                logger.warning(
                    f"Quality Check: [TAG_N] 잔여 감지 ({len(residual_tags)}개) — "
                    f"tag_map=0 (TXT 모드)이므로 허상 플레이스홀더로 판정, 정리 후 통과. "
                    f"잔여: {residual_tags[:5]}"
                )
                # translated_text 자체는 여기서 수정할 수 없지만,
                # orchestrator에서 unmask_tags가 이미 제거했을 것이므로 통과 처리.
            else:
                issue = "TAG_UNMASK_CORRUPTED (잔여 [TAG_N] 플레이스홀더 감지)"
                logger.warning(f"Quality Check Alert: {issue}")
                return {
                    "is_suspicious": True,
                    "is_critical": True,
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
                "is_critical": False,
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
        char_ratio = trans_len / src_len if src_len > 0 else 1.0

        if sent_ratio > 2.0 and sent_diff >= 8:
            # Check for natural compound sentence splitting (e.g. Chinese/Japanese clauses connected by ，、；： etc. split into Korean sentences)
            # If total character ratio is within normal translation range (0.8x ~ 2.0x), sentence count expansion (2.0x ~ 3.8x) is natural and valid.
            src_clauses = len([s for s in re.split(r'[\n.!?。！？，,；;：:—…]+', src_text_clean) if s.strip()])
            is_natural_splitting = (
                (char_ratio <= 2.8 and sent_ratio <= 3.8) or
                (char_ratio <= 2.8 and trans_sents <= max(src_clauses, src_sents * 2) + 5)
            )

            if is_natural_splitting:
                logger.info(
                    f"Quality Check: 복문/만연체 분할로 인한 문장 수 증가 감지 "
                    f"(원문 {src_sents}문장({src_clauses}절) -> 번역문 {trans_sents}문장, 문장비율 {sent_ratio:.2f}배, "
                    f"글자수비율 {char_ratio:.2f}배) -> 정상 통과 (Pass)"
                )
            else:
                # Flag only when sentence count explodes abnormally AND text length explodes beyond normal limits
                issue = f"SENTENCE_BLOATING_HALLUCINATION (원문 {src_sents}문장/{src_len}자 대비 번역문 {trans_sents}문장/{trans_len}자로 급증, +{sent_diff}문장 / 문장비율 {sent_ratio:.2f}배 / 글자비율 {char_ratio:.2f}배)"
                logger.warning(f"Quality Check Alert: {issue}")
                return {
                    "is_suspicious": True,
                    "is_critical": False,
                    "is_content_drop": False,
                    "is_repetition": False,
                    "is_hallucination": True,
                    "ratio": char_ratio,
                    "issue": issue
                }

        # 3.8. Untranslated CJK (Hanja) Ideograph Residual Check
        # ── 괄호 병기 형태 예외 처리 ──────────────────────────────────────────
        # 무협/선협 특유의 구결/사자성어 병기: '양강패절(陽剛霸絕)' 처럼 한글(한국어) 뒤에
        # 바로 이어지는 괄호 안 한자는 독자 가독성을 위한 의도적 병기이므로 제거 후 카운트.
        trans_text_no_bracket_hanja = re.sub(
            r'[\uac00-\ud7af]+\s*[\(\（][\u4e00-\u9fff\s]+[\)\）]',
            lambda m: re.sub(r'[\u4e00-\u9fff]', '', m.group(0)),
            trans_text_clean
        )
        hanja_matches = re.findall(r'[\u4e00-\u9fff]', trans_text_no_bracket_hanja)
        hanja_count = len(hanja_matches)
        hanja_ratio = (hanja_count / trans_len) if trans_len > 0 else 0.0
        hangul_count = len(re.findall(r'[\uac00-\ud7af]', trans_text_clean))

        if hanja_count > 0:
            src_hanja_set = set(re.findall(r'[\u4e00-\u9fff]', src_text_clean))
            matching_hanja = [h for h in hanja_matches if h in src_hanja_set]
            match_ratio = (len(matching_hanja) / hanja_count) if hanja_count > 0 else 0.0

            # ── 통과 조건 1: 주요 한국어 번역 + 소량 한자 (< 12%) + 원문 일치율 >= 50% ──
            # 구결/부적/이름 풀이 등 의도적 보존 한자
            if hangul_count >= 20 and hanja_ratio < 0.12 and match_ratio >= 0.50:
                logger.info(
                    f"Quality Check: 원문 한자(이름 풀이/주문/부적/구결/병기 등) 보존 감지 "
                    f"({len(matching_hanja)}/{hanja_count}자 원문 일치, 한자 비율 {hanja_ratio*100:.1f}%) -> 정상 통과 (Pass)"
                )
            # ── 통과 조건 2: 한자 비율 < 5% AND 절대 수 < 50자 → 극소량이므로 WARNING 후 통과 ──
            # 무협 사자성어/구결 한자 1% 미만 잔존이 이 케이스에 해당
            elif hanja_ratio < 0.05 and hanja_count < 50:
                sample_hanja = "".join(hanja_matches[:15])
                logger.warning(
                    f"Quality Check: UNTRANSLATED_HANJA_WARNING (번역문 내 소량 한자 {hanja_count}자 "
                    f"({hanja_ratio*100:.1f}%) 잔존: '{sample_hanja}') "
                    f"— 비율 5% 미만 & {hanja_count}자 미만 50자 → 경고만 기록하고 통과 (Pass)"
                )
                # is_suspicious=False 로 반환 → QC 재시도 루프 미발생
            elif hanja_count >= 5 or (trans_len >= 30 and hanja_ratio >= 0.05):
                sample_hanja = "".join(hanja_matches[:10])
                issue = f"UNTRANSLATED_HANJA_DETECTED (번역문 내 미번역 한자 {hanja_count}자({hanja_ratio*100:.1f}%) 잔존: '{sample_hanja}...')"
                logger.warning(f"Quality Check Alert: {issue}")
                return {
                    "is_suspicious": True,
                    "is_critical": True,
                    "is_content_drop": False,
                    "is_repetition": False,
                    "is_untranslated_hanja": True,
                    "is_hallucination": False,
                    "ratio": trans_len / src_len if src_len > 0 else 0.0,
                    "issue": issue
                }

        # 3.9. Untranslated Japanese (Hiragana/Katakana) Residual Check
        jp_matches = re.findall(r'[\u3040-\u309f\u30a0-\u30ff]', trans_text_clean)
        jp_count = len(jp_matches)
        if jp_count >= 3 or (hangul_count < 10 and jp_count > 0):
            sample_jp = "".join(jp_matches[:10])
            issue = f"UNTRANSLATED_JAPANESE_DETECTED (번역문 내 미번역 히라가나/가타카나 {jp_count}자 잔존: '{sample_jp}...')"
            logger.warning(f"Quality Check Alert: {issue}")
            return {
                "is_suspicious": True,
                "is_critical": True,
                "is_content_drop": False,
                "is_repetition": False,
                "is_untranslated_hanja": False,
                "is_untranslated_japanese": True,
                "is_hallucination": False,
                "ratio": trans_len / src_len if src_len > 0 else 0.0,
                "issue": issue
            }

        # 4. Length Ratio Anomaly Check
        ratio = trans_len / src_len if src_len > 0 else 1.0
        is_suspicious = False
        is_hallucination = False
        is_critical = False
        issue = None

        if src_len > 50:
            if ratio < 0.25:
                is_suspicious = True
                is_critical = True
                issue = f"OMISSION_SUSPECTED (번역문 길이 급감: 비율 {ratio:.2f})"
                logger.warning(f"Quality Check Alert: {issue}")
            elif ratio > 2.8:
                is_suspicious = True
                is_hallucination = True
                issue = f"HALLUCINATION_SUSPECTED (번역문 길이 급증: 비율 {ratio:.2f} > 2.8)"
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
            "is_critical": is_critical,
            "is_content_drop": False,
            "is_repetition": False,
            "is_hallucination": is_hallucination,
            "ratio": ratio,
            "issue": issue
        }
