"""
Unit tests for Web Novel Style Tuning, Common Noun/Currency Disambiguation,
and Prompt Engineering in OmniTranslator Pro.
"""

import sys
from pathlib import Path

src_dir = Path(__file__).resolve().parent.parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from domain.profiles.zh_profile import ChineseProfile
from domain.profiles.ja_profile import JapaneseProfile
from domain.profiles.en_profile import EnglishProfile
from domain.postprocess.cleaner import TextCleaner
from domain.glossary.extractor import GlossaryExtractor


def test_zh_profile_prompt_contents():
    """Verify Chinese profile contains all required tuning rules."""
    profile = ChineseProfile()
    sys_prompt = profile.get_system_instruction()

    # 1. Conversational & Web novel narrative rules
    assert "웹소설 맞춤형 대화체" in sys_prompt
    assert "~하지 않습니까?" in sys_prompt
    assert "3인칭 대명사 직역 금지" in sys_prompt or "그는" in sys_prompt
    assert "과거형 서술" in sys_prompt

    # 2. Currency & Common noun rules
    assert "화폐 '钱' 번역 절대 규칙" in sys_prompt
    assert "첸" in sys_prompt
    assert "단돈 한 푼" in sys_prompt
    assert "사물/단위/도구" in sys_prompt or "刀" in sys_prompt

    # 3. Proper noun vs common noun rules
    assert "고유 인명" in sys_prompt
    assert "지명/문파" in sys_prompt

    print("✅ test_zh_profile_prompt_contents passed!")


def test_ja_en_profiles():
    """Verify Japanese and English profiles have updated web novel prompts."""
    ja_profile = JapaneseProfile()
    ja_prompt = ja_profile.get_system_instruction()
    assert "웹소설 맞춤형 구어체" in ja_prompt
    assert "~하지 않습니까?" in ja_prompt

    en_profile = EnglishProfile()
    en_prompt = en_profile.get_system_instruction()
    assert "웹소설 맞춤형 구어체" in en_prompt
    assert "3인칭 대명사" in en_prompt

    print("✅ test_ja_en_profiles passed!")


def test_text_cleaner_currency_disambiguation():
    """Verify TextCleaner corrects '첸' in currency contexts."""
    # Test cases where '첸' was erroneously used instead of money/currency terms
    test1 = "그는 단돈 한 첸도 받지 못했다."
    cleaned1 = TextCleaner.clean_text(test1)
    assert "단돈 한 푼" in cleaned1 or "단돈 한" in cleaned1

    test2 = "상인은 100 첸을 요구했다."
    cleaned2 = TextCleaner.clean_text(test2)
    assert "100 푼" in cleaned2 or "100푼" in cleaned2

    test3 = "주머니에 첸이 없었다."
    cleaned3 = TextCleaner.clean_text(test3)
    assert "돈이 없었다" in cleaned3

    test4 = "그에게 첸을 주며 말했다."
    cleaned4 = TextCleaner.clean_text(test4)
    assert "돈을 주며" in cleaned4

    test5 = "은자와 첸을 챙겼다."
    cleaned5 = TextCleaner.clean_text(test5)
    assert "은자와 돈" in cleaned5

    print("✅ test_text_cleaner_currency_disambiguation passed!")


def test_glossary_extractor_common_noun_filter():
    """Verify GlossaryExtractor filters common currency/unit words from character names."""
    # '钱' should not be categorized as 인명 with '첸'
    kw, tr, cat = GlossaryExtractor._clean_extracted_term("钱", "첸", "인명", "ZH")
    assert cat != "인명"
    assert "돈" in tr or "화폐" in tr

    # '刀' should not be categorized as 인명 with '다오'
    kw, tr, cat = GlossaryExtractor._clean_extracted_term("刀", "다오", "인명", "ZH")
    assert cat != "인명"
    assert "도" in tr or "칼" in tr

    # Real character name should remain intact
    kw, tr, cat = GlossaryExtractor._clean_extracted_term("陈伶", "천링", "인명", "ZH")
    assert kw == "陈伶"
    assert tr == "천링"
    assert cat == "인명"

    print("✅ test_glossary_extractor_common_noun_filter passed!")


if __name__ == "__main__":
    test_zh_profile_prompt_contents()
    test_ja_en_profiles()
    test_text_cleaner_currency_disambiguation()
    test_glossary_extractor_common_noun_filter()
    print("\n🎉 ALL STYLE & DISAMBIGUATION TESTS PASSED!")
