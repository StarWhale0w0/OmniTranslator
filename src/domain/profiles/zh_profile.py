"""
OmniTranslator Pro - Chinese Web Novel Translation Profile
Simplified and censorship-resistant prompt profile.
"""

from typing import List, Dict, Any
from domain.profiles.base_profile import BaseLanguageProfile, STRICT_META_INSTRUCTION

ZH_GLOSSARY_HARD_CONSTRAINT = (
    "CRITICAL MANDATORY RULE:\n"
    "The provided glossary mappings MUST be applied exactly and strictly as written.\n"
    "NEVER translate, transliterate, or alter these terms into Korean Sino-readings (Hanja-eum), literal semantic translations, or other phonetic variations.\n"
    "Glossary mapping takes absolute precedence over any contextual, stylistic, or linguistic reasoning."
)

DEFAULT_SYSTEM_PROMPT = (
    "You are a professional Chinese-to-Korean web novel translator.\n"
    "1. Dialect & Regional Persona (사투리/지역색 및 1:1 충실 번역): Translate faithfully sentence-by-sentence with past tense narrative (~였다, ~했다). Do NOT invent, expand, or omit content. Preserve character tone, dialect, and regional flavor naturally into fluent Korean web novel prose.\n"
    "2. Pinyin Prohibition for Titles/Ranks (칭호/직책 병음 음역 금지): Official titles, ranks, and honorifics (e.g. 官, 帝, 君, 王, 仙, 祖, 皇 등) MUST NOT be transliterated into pinyin. Always translate them into standardized Korean Sino-readings (Hanja-eum) or appropriate title equivalents.\n"
    "3. Locations, Sects, Martial Arts, Titles & Settings (지명/문파/무공/칭호 한자음): 지명/문파/세력/무공/직책/칭호(특히 ~君 계열: 极光君->극광군, 红尘君->홍진군, 幽冥君->유명군 등) MUST follow Korean Sino-readings (Hanja-eum) (e.g. 少林寺 -> 소림사, 华山派 -> 화산파, 洛阳 -> 낙양, 界域 -> 계역, 天机局 -> 천기국, 黄昏社 -> 황혼사).\n"
    "4. Character Names vs Common Nouns (인명 vs 보통명사): Specific character names (고유 인명) MUST follow Standard Pinyin transliteration into Korean (e.g. 钟九 -> 종지우, 张小华 -> 장샤오화, 萧炎 -> 샤오옌, 林动 -> 린둥, 顾夜白 -> 구예바이, 楚风 -> 추펑). CRITICAL: 일반 인물 지칭 보통명사(年轻人->청년/젊은이, 男人->남자/사내, 女人->여자/여인, 老人->노인, 少年->소년, 少女->소녀, 人影->인영/그림자)는 절대로 병음으로 음역하지 말고(니엔칭런, 난런, 뉘런, 라오런, 사오녠, 사오뉘 X) 순수 한국어 보통명사로 번역할 것.\n"
    "5. First-Person Pronouns & Master-Disciple Titles (자칭 대명사 및 사제 호칭): 为师(이 스승이), 为父(이 애비가), 为母(이 어미가), 老夫(노부), 本座(본좌), 本尊(본존), 弟子(제자), 徒儿(제자야) 등 1인칭 자칭 및 사제 호칭은 절대로 인명으로 병음 음역(웨이스, 웨이푸, 라오푸, 번쭤 등)하지 말고 문맥에 맞는 자연스러운 한국어 대명사/호칭으로 번역할 것.\n"
    "6. Xianxia Culture, Idioms & Interjections (선협/무협 관용구, 신체/감각, 감탄사):\n"
    "   - 감각/신체/설정: 识海->식해/의식의 바다, 神识->신식, 丹田->단전, 气血->기혈 (병음 음역 및 직역 금지)\n"
    "   - 호칭: 阁下->귀하/존형/당신, 道友->도우/도형, 前辈->선배님/어르신, 小友->젊은 친구/어린 벗 (병음 음역 금지)\n"
    "   - 관용구: 吃醋->질투하다, 吃瘪->망신당하다/말문이 막히다, 放水->봐주다, 不管三七二十一->앞뒤 잴 것 없이 (문맥적 의역 필수)\n"
    "   - 감탄사: 嘶->흡/씁, 呸->퉷/퉤, 哼->흥 (병음 '스', '페이', '헝' 음역 금지)\n"
    "7. Real-world Brands & Foreign Countries (외래어/브랜드/국가명): Follow Standard Korean Loanword Orthography (e.g. 巴西 -> 브라질, 宝马 -> BMW).\n"
    "8. Interpersonal Titles (호칭): Translate relational titles naturally into Korean based on context (e.g. 师兄 -> 사형, 师妹 -> 사매, 哥/姐 -> 형/누나/오빠/언니).\n"
    "9. Maintain character tone, dialogues, and markdown/tag placeholders (e.g. [TAG_0], [TAG_1]) faithfully.\n"
    "10. Output only the translated text without explanations or markdown blocks."
    + STRICT_META_INSTRUCTION
)

class ChineseProfile(BaseLanguageProfile):
    """Chinese Web Novel profile with simplified, tag-placeholder aware prompts."""

    def __init__(self):
        super().__init__("ZH")

    def get_system_instruction(self, is_epub: bool = True) -> str:
        return DEFAULT_SYSTEM_PROMPT

    def get_prefill_history(self, is_epub: bool = True) -> List[Dict[str, Any]]:
        return [
            {
                "role": "user",
                "parts": ["Translate the web novel text preserving all tag placeholders faithfully."]
            },
            {
                "role": "model",
                "parts": ["Understood. I will provide a fluent Korean web novel translation with past tense narrative preserving tag placeholders."]
            }
        ]

    def get_prompt_template(self, is_epub: bool = True) -> str:
        return (
            f"{ZH_GLOSSARY_HARD_CONSTRAINT}\n\n"
            "{{glossary_context}}\n\n"
            "Text to translate:\n"
            "{{slot}}\n\n"
            "Translation:"
        )

    def get_cleaner_patterns(self) -> List[str]:
        return [
            r'^.*네티즌이?\s*업로드.*$',
            r'^.*전자책.*(?:무료|다운로드|완결본|사이트).*$',
            r'^.*독자들의?\s*(?:보물창고|천국).*$',
            r'\([^)]*www\.[^)]*\)',
            r'^(?:##\s*)?(?:번역\s*결과|Translation|Korean):?$',
            r'```'
        ]