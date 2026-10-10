import sys
import unittest
from pathlib import Path

# Add src to sys.path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from core.session_manager import SessionManager
from infra.fallback_translator import FallbackTranslator

class TestTranslationIntegrityAndFallback(unittest.TestCase):

    def test_session_manager_rejects_warning_comments(self):
        corrupted_1 = "<!-- [번역경고] 한자 415자 미변환 잔존(Gemini 응답 부재) --> <div><p>在他这异于常人的速度</p></div>"
        valid_1, reason_1 = SessionManager.is_chunk_valid(corrupted_1)
        self.assertFalse(valid_1)
        self.assertIn("번역 실패/미변환 경고 태그 잔존", reason_1)

        corrupted_2 = "[번역경고] QC 4회 실패"
        valid_2, reason_2 = SessionManager.is_chunk_valid(corrupted_2)
        self.assertFalse(valid_2)

        corrupted_3 = "[품질경고:CONTENT_DROP] 원문 텍스트"
        valid_3, reason_3 = SessionManager.is_chunk_valid(corrupted_3)
        self.assertFalse(valid_3)

    def test_session_manager_rejects_untranslated_cjk(self):
        # Raw Chinese text without Korean
        raw_zh = "<div><p>在他这异于常人的速度与精准打击之下，这一片商场很快消停了下来，虽然各处都已响起了连串的痛呼与叫喊。</p></div>"
        valid, reason = SessionManager.is_chunk_valid(raw_zh)
        self.assertFalse(valid)
        self.assertIn("한글 부재 및 미번역 원문 한자", reason)

        # High Hanja ratio with minimal Hangul
        mixed_bad = "<div><p>테스트 그의 速度와 精準 打擊之下 這一片 商場 很快 消停了下来 雖然 各處 都已 響起</p></div>"
        valid_mixed, reason_mixed = SessionManager.is_chunk_valid(mixed_bad)
        self.assertFalse(valid_mixed)

    def test_session_manager_accepts_clean_korean(self):
        clean_ko = "<div><p>그의 남다른 속도와 정밀한 타격 아래, 이 쇼핑몰 일대는 순식간에 잠잠해졌다.</p></div>"
        valid, reason = SessionManager.is_chunk_valid(clean_ko)
        self.assertTrue(valid)
        self.assertIsNone(reason)

    def test_session_manager_accepts_legitimate_annotated_hanja(self):
        annotated_ko = "<div><p>그는 양강패절(陽剛霸絕)의 초식을 펼쳤으며 그의 검술은 천하제일이었다.</p></div>"
        valid, reason = SessionManager.is_chunk_valid(annotated_ko)
        self.assertTrue(valid)

    def test_sanitize_translated_chunks_purges_bad_chunks(self):
        chunks = {
            0: "<div><p>정상적으로 번역된 본문 내용입니다.</p></div>",
            1: "<!-- [번역경고] 한자 415자 미변환 잔존(Gemini 응답 부재) --> <div><p>在他这异于常人的速度</p></div>",
            2: "<div><p>두 번째 정상 번역 문장입니다.</p></div>",
            3: "<div><p>在他这异于常人的速度与精准打击之下，这一片商场很快消停了下来</p></div>",
        }
        sanitized, purged_count = SessionManager.sanitize_translated_chunks(chunks)
        self.assertEqual(purged_count, 2)
        self.assertEqual(len(sanitized), 2)
        self.assertIn(0, sanitized)
        self.assertIn(2, sanitized)
        self.assertNotIn(1, sanitized)
        self.assertNotIn(3, sanitized)

if __name__ == "__main__":
    unittest.main()
