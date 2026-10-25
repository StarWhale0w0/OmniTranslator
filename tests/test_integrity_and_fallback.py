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

    def test_session_manager_rejects_untranslated_japanese(self):
        # 1. Raw Japanese chunk with Hiragana & Katakana
        raw_jp = "<div><p>彼が部屋に入ると、そこには誰もいなかった。カバンを置いて窓を開けた。</p></div>"
        valid, reason = SessionManager.is_chunk_valid(raw_jp, lang_code="JA")
        self.assertFalse(valid)
        self.assertIn("미번역 히라가나/가타카나", reason)

        # 2. Residual Hiragana/Katakana (>= 3 chars) inside Korean translation
        leaked_jp = "<div><p>그는 방문을 열며 조용히 말했다. '誰もいないの？' 하지만 대답은 없었다.</p></div>"
        valid_leak, reason_leak = SessionManager.is_chunk_valid(leaked_jp, lang_code="JA")
        self.assertFalse(valid_leak)
        self.assertIn("미번역 히라가나/가타카나", reason_leak)

        # 3. Short Hangul (< 10 chars) with Japanese character (e.g. 1 char)
        short_ko_jp = "<p>확인です</p>"
        valid_short, reason_short = SessionManager.is_chunk_valid(short_ko_jp, lang_code="JA")
        self.assertFalse(valid_short)
        self.assertIn("한글 부족", reason_short)

        # 4. Clean Korean translation should pass
        clean_ko = "<div><p>그가 방에 들어갔을 때, 그곳에는 아무도 없었다. 가방을 내려놓고 창문을 열었다.</p></div>"
        valid_clean, reason_clean = SessionManager.is_chunk_valid(clean_ko, lang_code="JA")
        self.assertTrue(valid_clean)
        self.assertIsNone(reason_clean)

    def test_sanitize_translated_chunks_purges_japanese_corrupted_chunks(self):
        chunks = {
            0: "<div><p>정상적으로 번역된 일본어 소설 첫 번째 챕터 문장입니다.</p></div>",
            1: "<div><p>彼が部屋に入ると、そこには誰もいなかった。</p></div>",
            2: "<div><p>그는 문을 닫고 한숨을 내쉬었다. 완전히 지친 하루였다.</p></div>",
            3: "<div><p>이것은 테스트 문장입니다만 これは何ですか 잔존.</p></div>",
            4: "<p>확인です</p>",
        }
        sanitized, purged_count = SessionManager.sanitize_translated_chunks(chunks, lang_code="JA")
        self.assertEqual(purged_count, 3)
        self.assertEqual(len(sanitized), 2)
        self.assertIn(0, sanitized)
        self.assertIn(2, sanitized)
        self.assertNotIn(1, sanitized)
        self.assertNotIn(3, sanitized)
        self.assertNotIn(4, sanitized)

    def test_fallback_translator_rejects_raw_source_and_japanese_leak(self):
        jp_source = "彼が部屋に入ると、そこには誰もいなかった。"

        # 1. Exact raw copy echo
        self.assertFalse(FallbackTranslator.is_valid_translation(jp_source, jp_source, source_lang="JA"))

        # 2. Raw copy with slight HTML wrapping
        self.assertFalse(FallbackTranslator.is_valid_translation(f"<p>{jp_source}</p>", jp_source, source_lang="JA"))

        # 3. Residual Hiragana / Katakana
        leaked_cand = "그가 방에 들어갔을 때, そこには 아무도 없었다."
        self.assertFalse(FallbackTranslator.is_valid_translation(leaked_cand, jp_source, source_lang="JA"))

        # 4. Short Hangul with Japanese
        short_cand = "그는 部屋"
        # 部屋 is Hanja, but if it has Japanese:
        short_jp = "그는 だ"
        self.assertFalse(FallbackTranslator.is_valid_translation(short_jp, jp_source, source_lang="JA"))

        # 5. Zero Hangul output when source has Japanese
        zero_hangul = "He entered the room and nobody was there."
        self.assertFalse(FallbackTranslator.is_valid_translation(zero_hangul, jp_source, source_lang="JA"))

        # 6. Valid Korean translation accepted
        valid_ko = "그가 방에 들어서자 그곳에는 아무도 없었다."
        self.assertTrue(FallbackTranslator.is_valid_translation(valid_ko, jp_source, source_lang="JA"))

        # 7. Non-CJK preservation (e.g. pure numbers / pagination)
        num_source = "1 2 3 4 5"
        self.assertTrue(FallbackTranslator.is_valid_translation(num_source, num_source, source_lang="JA"))

    def test_quality_checker_detects_untranslated_japanese(self):
        from domain.postprocess.quality_checker import QualityChecker

        src = "彼が部屋に入ると、そこには誰もいなかった。"
        trans_leaked = "그가 방에 들어갔을 때, そこには 아무도 없었다."

        qc_res = QualityChecker.inspect_chunk(src, trans_leaked)
        self.assertTrue(qc_res["is_suspicious"])
        self.assertTrue(qc_res["is_critical"])
        self.assertTrue(qc_res.get("is_untranslated_japanese", False))
        self.assertIn("UNTRANSLATED_JAPANESE_DETECTED", qc_res["issue"])

if __name__ == "__main__":
    unittest.main()
