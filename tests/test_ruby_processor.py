"""
Tests for RubyProcessor, EpubIO ruby integration, and CSS reset injection.
"""

import sys
import unittest
from pathlib import Path

# Add src to sys.path
src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from domain.epub.ruby_processor import RubyProcessor
from domain.postprocess.tag_masker import TagMasker
from domain.postprocess.cleaner import TextCleaner
from infra.epub_io import EpubIO
from ebooklib import epub


class TestRubyProcessor(unittest.TestCase):

    def test_simple_hiragana_furigana(self):
        html = "<p><ruby>滲<rt>にじ</rt></ruby>み出る</p>"
        result = RubyProcessor.flatten_ruby_html(html)
        self.assertIn("滲み出る", result)
        self.assertNotIn("<ruby", result)
        self.assertNotIn("<rt", result)
        self.assertNotIn("にじ", result)

    def test_paired_rb_rt_hiragana(self):
        html = "<p><ruby><rb>神</rb><rt>み</rt><rb>子</rb><rt>こ</rt></ruby></p>"
        result = RubyProcessor.flatten_ruby_html(html)
        self.assertIn("神子", result)
        self.assertNotIn("み", result)
        self.assertNotIn("こ", result)

    def test_interleaved_rt_hiragana(self):
        html = "<p><ruby>焦<rt>こげ</rt>茶<rt>ちや</rt>色<rt>いろ</rt></ruby></p>"
        result = RubyProcessor.flatten_ruby_html(html)
        self.assertIn("焦茶色", result)
        self.assertNotIn("こげ", result)

    def test_interleaved_rt_with_newlines(self):
        html = "<p><ruby>焦<rt>こげ</rt>\n 茶<rt>ちや</rt>\n 色<rt>いろ</rt>\n</ruby></p>"
        result = RubyProcessor.flatten_ruby_html(html)
        self.assertIn("焦茶色", result)
        self.assertNotIn("こげ", result)

    def test_rp_tag_removal(self):
        html = "<p><ruby>走<rp>(</rp><rt>はし</rt><rp>)</rp></ruby>る</p>"
        result = RubyProcessor.flatten_ruby_html(html)
        self.assertIn("走る", result)
        self.assertNotIn("<rp", result)
        self.assertNotIn("はし", result)

    def test_katakana_special_reading_preservation(self):
        # Light novel special naming: Kanji + Katakana reading
        html = "<p><ruby><rb>長距離拡散式女神の慈悲</rb><rt>パナケイア・ブレス</rt></ruby></p>"
        result = RubyProcessor.flatten_ruby_html(html)
        self.assertIn("長距離拡散式女神の慈悲(パナケイア・ブレス)", result)
        self.assertNotIn("<ruby", result)

    def test_katakana_special_reading_single(self):
        html = "<p><ruby>地球<rt>テラ</rt></ruby>へ</p>"
        result = RubyProcessor.flatten_ruby_html(html)
        self.assertIn("地球(テラ)へ", result)

    def test_chinese_pinyin_removal(self):
        html = "<p><ruby>汉字<rt>hànzì</rt></ruby></p>"
        result = RubyProcessor.flatten_ruby_html(html)
        self.assertIn("汉字", result)
        self.assertNotIn("hànzì", result)

    def test_orphan_rt_and_rp(self):
        html = "<p>앞단어<rt>해설</rt>뒷단어<rp>(</rp>텍스트<rp>)</rp></p>"
        result = RubyProcessor.flatten_ruby_html(html)
        self.assertIn("앞단어(해설)뒷단어텍스트", result)
        self.assertNotIn("<rt", result)
        self.assertNotIn("<rp", result)

    def test_korean_broken_ruby_flattening(self):
        html = "<p><ruby>배<rt>어</rt></ruby>나오는</p>"
        result = RubyProcessor.flatten_ruby_html(html)
        self.assertIn("배(어)나오는", result)
        self.assertNotIn("<ruby", result)

    def test_tag_masker_integration(self):
        html = "<p><ruby>滲<rt>にじ</rt></ruby>み出る<ruby>地球<rt>テラ</rt></ruby></p>"
        masked, tag_map, pure = TagMasker.mask_tags(html)
        # Ruby tags should NOT produce [TAG_N] placeholders
        for placeholder, tag_val in tag_map.items():
            self.assertNotIn("<ruby", tag_val)
            self.assertNotIn("<rt", tag_val)
        # Pure text should be clean
        self.assertIn("滲み出る", pure)
        self.assertIn("地球(テラ)", pure)

    def test_text_cleaner_integration(self):
        html = "<p><ruby>学校<rt>がっこう</rt></ruby>に行く</p>"
        cleaned = TextCleaner.strip_html_tags(html)
        self.assertEqual(cleaned, "学校に行く")

    def test_css_injection(self):
        book = epub.EpubBook()
        # Add a dummy css
        css_item = epub.EpubItem(
            uid="style",
            file_name="style.css",
            media_type="text/css",
            content=b"body { color: black; }\n"
        )
        book.add_item(css_item)

        injected = RubyProcessor.inject_ruby_css_to_book(book)
        self.assertTrue(injected)

        # Check content
        content = css_item.get_content().decode('utf-8')
        self.assertIn("ruby {", content)
        self.assertIn("font-size: inherit;", content)
        self.assertIn("rt {", content)

        # Second injection should not duplicate
        injected_again = RubyProcessor.inject_ruby_css_to_book(book)
        self.assertFalse(injected_again)
        self.assertEqual(content.count("/* OmniTranslator Ruby Tag Reset for Korean EPUB */"), 1)

    def test_css_injection_when_no_css_exists(self):
        book = epub.EpubBook()
        injected = RubyProcessor.inject_ruby_css_to_book(book)
        self.assertTrue(injected)
        # Should have created a stylesheet
        css_items = [i for i in book.get_items() if i.media_type == "text/css"]
        self.assertEqual(len(css_items), 1)
        self.assertIn("ruby {", css_items[0].get_content().decode('utf-8'))


if __name__ == "__main__":
    unittest.main()
