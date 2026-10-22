"""
Unit tests for Japanese Novel Translation Fixes:
1. Tag masking isolation & broken tag fragment recovery ([TAG_N], [태그_N], __TAG_N__, isolated numbers like '27]')
2. Japanese character name mistranslation & Hanja-eum correction (将人->마사토, 恋海->코나미, 匠->타쿠미)
3. Sentence boundary chunk slicing & stuttering removal ("이미 이미")
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import unittest
from domain.postprocess.tag_masker import TagMasker
from domain.postprocess.glossary_corrector import GlossaryCorrector
from domain.postprocess.cleaner import TextCleaner
from domain.chunkers.dom_chunker import DomChunker

class TestJpMaskingAndGlossary(unittest.TestCase):

    def test_broken_tag_restoration_and_cleanup(self):
        tag_map = {
            '[TAG_0]': '<div class="main">',
            '[TAG_1]': '<p>',
            '[TAG_2]': '</p>',
            '[TAG_27]': '</p><p class="quote">',
            '[TAG_5]': '<span class="tcy">',
        }

        # 1. Broken isolated number fragment: "아니오! 27] 그때는..."
        input_text = "아니오! 27] 그때는..."
        unmasked = TagMasker.unmask_tags(input_text, tag_map)
        self.assertIn('</p><p class="quote">', unmasked)
        self.assertNotIn('27]', unmasked)

        # 2. Mutated format: "장인의 좋음, 별로 외모가 아니니까… TAG_5]「그것"
        input_text2 = "장인의 좋음, 별로 외모가 아니니까… TAG_5]「그것"
        unmasked2 = TagMasker.unmask_tags(input_text2, tag_map)
        self.assertIn('<span class="tcy">', unmasked2)
        self.assertNotIn('TAG_5]', unmasked2)

        # 3. Korean tag mutation: [태그_1], [태그 2], __TAG_0__
        input_text3 = "__TAG_0__[태그_1]안녕하세요[태그 2]"
        unmasked3 = TagMasker.unmask_tags(input_text3, tag_map)
        self.assertEqual(unmasked3, '<div class="main"><p>안녕하세요</p>')

        # 4. Unmapped leftover hallucinated fragment
        input_text4 = "정말인가요? 99] 그런 일은 없습니다."
        unmasked4 = TagMasker.unmask_tags(input_text4, tag_map)
        self.assertNotIn('99]', unmasked4)

    def test_jp_name_glossary_correction(self):
        glossary = [
            {'keyword': '将人', 'translated_keyword': '마사토', 'category': '인명'},
            {'keyword': '恋海', 'translated_keyword': '코나미', 'category': '인명'},
            {'keyword': '匠', 'translated_keyword': '타쿠미', 'category': '인명'},
            {'keyword': '由佳', 'translated_keyword': '유카', 'category': '인명'},
        ]

        # 1. Hanja-eum reading & honorific: 将人さん -> 장인 씨 -> 마사토 씨
        src1 = "将人さんひとつお願いがあるんですけど"
        trans1 = "장인 씨 하나 부탁이 있습니다만..."
        res1 = GlossaryCorrector.correct_text(src1, trans1, glossary, lang_code="JA")
        self.assertIn("마사토 씨", res1)
        self.assertNotIn("장인 씨", res1)

        # 2. Literal semantic translation: 匠 -> 장인 -> 타쿠미
        src2 = "匠の店に行く"
        trans2 = "장인의 가게로 간다"
        res2 = GlossaryCorrector.correct_text(src2, trans2, glossary, lang_code="JA")
        self.assertIn("타쿠미의", res2)
        self.assertNotIn("장인의", res2)

        # 3. Particle recalculation: 그런 장인이니까 -> 그런 마사토니까
        src3 = "そんな将人だから"
        trans3 = "그런 장인이니까 나는"
        res3 = GlossaryCorrector.correct_text(src3, trans3, glossary, lang_code="JA")
        self.assertIn("마사토니까", res3)
        self.assertNotIn("장인이니까", res3)

        # 4. Hanja-eum with initial sound rule: 恋海 -> 연해 -> 코나미
        src4 = "恋海が入ってきた"
        trans4 = "연해가 들어왔다"
        res4 = GlossaryCorrector.correct_text(src4, trans4, glossary, lang_code="JA")
        self.assertIn("코나미가", res4)
        self.assertNotIn("연해가", res4)

    def test_stuttering_removal(self):
        text = "그는 이미 이미 알고 있었다. 정말 정말 괜찮아?"
        cleaned = TextCleaner.clean_text(text)
        self.assertIn("이미 알고", cleaned)
        self.assertNotIn("이미 이미", cleaned)
        self.assertIn("정말 괜찮아", cleaned)
        self.assertNotIn("정말 정말", cleaned)

    def test_sentence_boundary_chunking(self):
        long_paragraph = (
            "첫 번째 문장입니다。두 번째 문장입니다！"
            "세 번째 문장도 있습니다？「네 번째 대화 문장입니다。」"
            "다섯 번째 마지막 문장입니다。"
        )
        chunks = DomChunker.split_text_by_sentence_boundary(long_paragraph, max_chars=35)
        self.assertTrue(len(chunks) >= 2)
        for chunk in chunks:
            # Each chunk should end with punctuation or closing quote
            last_char = chunk.strip()[-1]
            self.assertIn(last_char, ['。', '！', '？', '」', '”', '"'])

if __name__ == '__main__':
    unittest.main()
