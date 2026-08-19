"""
OmniTranslator Pro - Postprocessing Proper Noun & Korean Josa (조사) Corrector
Guarantees 100% glossary consistency by:
1. Detecting and replacing un-transliterated Chinese terms, traditional characters,
   and Sino-Korean Hanja-eum readings (e.g. 钟九 -> 종구, 张小华 -> 장소화, 萧炎 -> 소염, 林动 -> 임동)
   with the confirmed glossary translations (e.g. 종지우, 장샤오화, 샤오옌, 린둥).
2. Recalculating Korean final consonants (받침 / Jongseong) and fixing following particles
   (은/는, 이/가, 을/를, 과/와, 으로/로, 아/야, 이나/나, 이란/란, 이라/라, 이며/며, 이든/든, 이었/였, 이에요/예요).
"""

import re
import unicodedata
from typing import List, Dict, Any, Set, Tuple
from common.logger import setup_logger

logger = setup_logger("GlossaryCorrector")

# Comprehensive Hanja-to-Hangul reading map (covers Simplified & Traditional CJK characters used in novels)
HANJA_READINGS: Dict[str, str] = {
    # Common surnames and names
    '钟': '종', '鍾': '종', '九': '구', '张': '장', '張': '장', '小': '소', '华': '화', '華': '화',
    '萧': '소', '蕭': '소', '炎': '염', '林': '림', '动': '동', '動': '동', '顾': '고', '顧': '고',
    '夜': '야', '白': '백', '楚': '초', '风': '풍', '風': '풍', '叶': '엽', '葉': '엽', '修': '수',
    '唐': '당', '三': '삼', '石': '석', '昊': '호', '王': '왕', '纯': '순', '純': '순', '韩': '한',
    '韓': '한', '立': '립', '孟': '맹', '浩': '호', '罗': '라', '羅': '라', '峰': '봉', '陈': '진',
    '陳': '진', '平': '평', '安': '안', '李': '리', '火': '화', '旺': '왕', '天': '천', '月': '월',
    '云': '운', '雲': '운', '清': '청', '雪': '설', '剑': '검', '劍': '검', '仙': '선', '尊': '존',
    '帝': '제', '君': '군', '皇': '황', '霸': '패', '绝': '절', '絕': '절', '神': '신', '魔': '마',
    '龙': '룡', '龍': '룡', '凤': '봉', '鳳': '봉', '虎': '호', '雀': '작', '武': '무', '道': '도',
    '玄': '현', '天': '천', '地': '지', '人': '인', '山': '산', '海': '해', '江': '강', '河': '하',
    '星': '성', '辰': '진', '宇': '우', '宙': '주', '乾': '건', '坤': '곤', '阴': '음', '陰': '음',
    '阳': '양', '陽': '양', '金': '금', '木': '목', '水': '수', '土': '토', '雷': '뢰', '电': '전',
    '電': '전', '光': '광', '暗': '암', '影': '영', '灵': '령', '靈': '령', '魂': '혼', '魄': '백',
    '生': '생', '死': '사', '轮': '륜', '輪': '륜', '回': '회', '宗': '종', '门': '문', '門': '문',
    '派': '파', '帮': '방', '幫': '방', '谷': '곡', '峰': '봉', '阁': '각', '閣': '각', '殿': '전',
    '城': '성', '国': '국', '國': '국', '府': '부', '院': '원', '界': '계', '域': '역', '海': '해',
    '荒': '황', '古': '고', '圣': '성', '聖': '성', '皇': '황', '王': '왕', '侯': '후', '将': '장',
    '帅': '수', '帥': '수', '相': '상', '师': '사', '師': '사', '徒': '도', '兄': '형', '弟': '제',
    '姐': '저', '妹': '매', '父': '부', '母': '모', '子': '자', '女': '녀', '老': '로', '少': '소',
    '赵': '조', '趙': '조', '钱': '전', '錢': '전', '孙': '손', '孫': '손', '周': '주', '吴': '오',
    '吳': '오', '郑': '정', '鄭': '정', '冯': '풍', '馮': '풍', '卫': '위', '衛': '위', '蒋': '장',
    '蔣': '장', '沈': '심', '杨': '양', '楊': '양', '朱': '주', '秦': '진', '尤': '우', '许': '허',
    '許': '허', '何': '하', '吕': '려', '呂': '려', '施': '시', '严': '엄', '嚴': '엄', '孔': '공',
    '曹': '조', '姜': '강', '金': '금', '魏': '위', '陶': '도', '姜': '강', '戚': '척', '谢': '사',
    '謝': '사', '邹': '추', '鄒': '추', '喻': '유', '柏': '백', '水': '수', '窦': '두', '竇': '두',
    '章': '장', '苏': '소', '蘇': '소', '潘': '반', '葛': '갈', '奚': '해', '范': '범', '範': '범',
    '彭': '팽', '郎': '랑', '魯': '로', '鲁': '로', '韦': '위', '韋': '위', '昌': '창', '马': '마',
    '馬': '마', '苗': '묘', '凤': '봉', '花': '화', '方': '방', '俞': '유', '任': '임', '袁': '원',
    '柳': '류', '酆': '풍', '鲍': '포', '鮑': '포', '史': '사', '唐': '당', '费': '비', '費': '비',
    '廉': '렴', '岑': '잠', '薛': '설', '雷': '뢰', '贺': '하', '賀': '하', '倪': '예', '汤': '탕',
    '湯': '탕', '滕': '등', '殷': '은', '毕': '필', '畢': '필', '郝': '학', '邬': '오', '鄔': '오',
    '安': '안', '常': '상', '乐': '악', '樂': '악', '于': '우', '时': '시', '時': '시', '傅': '부',
    '皮': '피', '卞': '변', '齐': '제', '齊': '제', '康': '강', '伍': '오', '余': '여', '元': '원',
    '卜': '복', '顾': '고', '孟': '맹', '平': '평', '黄': '황', '黃': '황', '和': '화', '穆': '목',
    '萧': '소', '尹': '윤', '姚': '요', '邵': '소', '湛': '담', '汪': '왕', '祁': '기', '毛': '모',
    '禹': '우', '狄': '적', '米': '미', '贝': '패', '貝': '패', '明': '명', '臧': '장', '计': '계',
    '計': '계', '伏': '복', '成': '성', '戴': '대', '谈': '담', '談': '담', '宋': '송', '茅': '모',
    '庞': '방', '龐': '방', '熊': '웅', '纪': '기', '紀': '기', '舒': '서', '屈': '굴', '项': '항',
    '項': '항', '祝': '축', '董': '동', '梁': '량', '杜': '두', '阮': '완', '蓝': '남', '藍': '남',
    '闵': '민', '閔': '민', '席': '석', '季': '계', '麻': '마', '强': '강', '強': '강', '贾': '가',
    '賈': '가', '路': '로', '娄': '루', '婁': '루', '危': '위', '江': '강', '童': '동', '颜': '안',
    '顏': '안', '郭': '곽', '梅': '매', '盛': '성', '林': '림', '刁': '조', '钟': '종', '徐': '서',
    '丘': '구', '骆': '락', '駱': '락', '高': '고', '夏': '하', '蔡': '채', '田': '전', '樊': '번',
    '胡': '호', '凌': '릉', '霍': '곽', '虞': '우', '万': '만', '萬': '만', '支': '지', '柯': '가',
    '昝': '잠', '管': '관', '卢': '로', '盧': '로', '莫': '막', '经': '경', '房': '방', '裘': '구',
    '缪': '무', '繆': '무', '干': '간', '解': '해', '应': '응', '應': '응', '宗': '종', '丁': '정',
    '宣': '선', '贲': '분', '賁': '분', '邓': '등', '鄧': '등', '郁': '욱', '鬱': '욱', '单': '단',
    '單': '단', '杭': '항', '洪': '홍', '包': '포', '诸': '제', '諸': '제', '左': '좌', '石': '석',
    '崔': '최', '吉': '길', '钮': '뉴', '鈕': '뉴', '龚': '공', '龔': '공', '程': '정', '嵇': '혜',
    '邢': '형', '滑': '활', '裴': '배', '陆': '륙', '陸': '륙', '荣': '영', '榮': '영', '翁': '옹',
    '荀': '순', '羊': '양', '於': '어', '惠': '혜', '甄': '견', '曲': '곡', '家': '가', '封': '봉',
    '芮': '예', '羿': '예', '储': '저', '儲': '저', '靳': '근', '汲': '급', '邴': '병', '糜': '미',
    '松': '송', '井': '정', '段': '단', '富': '부', '巫': '무', '乌': '오', '烏': '오', '焦': '초',
    '巴': '파', '弓': '궁', '牧': '목', '隗': '외', '山': '산', '谷': '곡', '车': '차', '車': '차',
    '侯': '후', '宓': '복', '蓬': '봉', '全': '전', '郗': '치', '班': '반', '仰': '앙', '秋': '추',
    '仲': '중', '伊': '이', '宫': '궁', '宮': '궁', '宁': '녕', '寧': '녕', '仇': '구', '栾': '란',
    '欒': '란', '暴': '폭', '甘': '감', '钭': '두', '厲': '려', '厉': '려', '戎': '융', '祖': '조',
    '武': '무', '符': '부', '刘': '류', '劉': '류', '景': '경', '詹': '첨', '束': '속', '龙': '룡',
    '葉': '엽', '幸': '행', '司': '사', '韶': '소', '郜': '고', '黎': '려', '蓟': '계', '薊': '계',
    '薄': '박', '印': '인', '宿': '숙', '白': '백', '怀': '회', '懷': '회', '蒲': '포', '邰': '태',
    '从': '종', '從': '종', '鄂': '악', '索': '색', '咸': '함', '籍': '적', '赖': '뢰', '賴': '뢰',
    '卓': '탁', '蔺': '린', '藺': '린', '屠': '도', '蒙': '몽', '池': '지', '乔': '교', '喬': '교',
    '阴': '음', '鬱': '욱', '胥': '서', '能': '능', '苍': '창', '蒼': '창', '双': '쌍', '雙': '쌍',
    '闻': '문', '聞': '문', '莘': '신', '党': '당', '黨': '당', '翟': '적', '谭': '담', '譚': '담',
    '贡': '공', '貢': '공', '劳': '로', '勞': '로', '逄': '봉', '姬': '희', '申': '신', '扶': '부',
    '堵': '도', '冉': '염', '宰': '재', '郦': '력', '酈': '력', '雍': '옹', '郤': '극', '璩': '거',
    '桑': '상', '桂': '계', '濮': '복', '牛': '우', '寿': '수', '壽': '수', '通': '통', '边': '변',
    '邊': '변', '扈': '호', '燕': '연', '冀': '기', '郏': '협', '郟': '협', '浦': '포', '尚': '상',
    '农': '농', '農': '농', '温': '온', '溫': '온', '别': '별', '別': '별', '庄': '장', '莊': '장',
    '晏': '안', '柴': '채', '瞿': '구', '阎': '염', '閻': '염', '充': '충', '慕': '모', '连': '련',
    '連': '련', '茹': '여', '习': '습', '習': '습', '宦': '환', '艾': '애', '鱼': '어', '魚': '어',
    '容': '용', '向': '향', '古': '고', '易': '역', '慎': '신', '戈': '과', '廖': '료', '庾': '유',
    '终': '종', '終': '종', '暨': '기', '居': '거', '衡': '형', '步': '보', '都': '도', '耿': '경',
    '满': '만', '滿': '만', '弘': '홍', '匡': '광', '国': '국', '文': '문', '寇': '구', '广': '광',
    '廣': '광', '禄': '록', '祿': '록', '阙': '궐', '闕': '궐', '东': '동', '東': '동', '欧': '구',
    '歐': '구', '殳': '수', '沃': '옥', '利': '리', '蔚': '울', '越': '월', '夔': '기', '隆': '륭',
    '师': '사', '巩': '공', '鞏': '공', '聂': '섭', '聶': '섭', '晁': '조', '勾': '구', '敖': '오',
    '融': '융', '冷': '랭', '訾': '자', '辛': '신', '阚': '감', '闞': '감', '那': '나', '简': '간',
    '簡': '간', '饶': '요', '饒': '요', '空': '공', '曾': '증', '毋': '무', '沙': '사', '乜': '야',
    '养': '양', '養': '양', '鞠': '국', '须': '수', '須': '수', '丰': '풍', '巢': '소', '关': '관',
    '關': '관', '蒯': '괴', '相': '상', '查': '사', '后': '후', '後': '후', '荆': '형', '荊': '형',
    '红': '홍', '紅': '홍', '游': '유', '竺': '축', '权': '권', '權': '권', '逯': '록', '盖': '개',
    '蓋': '개', '益': '익', '桓': '환', '公': '공', '万俟': '모기', '司马': '사마', '司馬': '사마',
    '上官': '상관', '欧阳': '구양', '歐陽': '구양', '夏侯': '하후', '诸葛': '제갈', '諸葛': '제갈',
    '闻人': '문인', '聞人': '문인', '东方': '동방', '東方': '동방', '赫连': '혁련', '赫連': '혁련',
    '皇甫': '황보', '尉迟': '위지', '尉遲': '위지', '公羊': '공양', '澹台': '담대', '澹臺': '담대',
    '公冶': '공야', '宗政': '종정', '濮阳': '복양', '濮陽': '복양', '淳于': '순우', '单于': '선우',
    '太叔': '태숙', '申屠': '신도', '公孙': '공손', '公孫': '공손', '仲孙': '중손', '仲孫': '중손',
    '轩辕': '헌원', '軒轅': '헌원', '令狐': '령호', '钟离': '종리', '鍾離': '종리', '宇文': '우문',
    '长孙': '장손', '長孫': '장손', '慕容': '모용', '鲜于': '선우', '鮮于': '선우', '闾丘': '려구',
    '司徒': '사도', '司空': '사공', '亓官': '기관', '司寇': '사구', '仉督': '장독', '子车': '자차',
    '颛孙': '전손', '端木': '단목', '巫马': '무마', '公西': '공서', '漆雕': '칠조', '乐正': '악정',
    '壤驷': '양사', '公良': '공량', '拓跋': '탁발', '夹谷': '협곡', '宰父': '재부', '谷梁': '곡량',
    '晋楚': '진초', '阎法': '염법', '汝鄢': '여언', '涂钦': '도흠', '段干': '단간', '百里': '백리',
    '东郭': '동곽', '南门': '남문', '呼延': '호연', '归海': '귀해', '羊舌': '양설', '微生': '미생',
    '岳': '악', '帅': '수', '缑': '구', '亢': '항', '况': '황', '后': '후', '有': '유', '琴': '금',
    '梁丘': '량구', '左丘': '좌구', '东门': '동문', '西门': '서문', '西門': '서문', '南宫': '남궁',
    '南宮': '남궁', '第五': '제오'
}

INITIAL_SOUND_RULES: Dict[str, str] = {
    '림': '임', '리': '이', '라': '나', '류': '유', '량': '양', '륙': '육', '룡': '용', '뢰': '뇌', '로': '노',
    '련': '연', '렬': '열', '렴': '염', '령': '영', '례': '예', '록': '녹', '론': '논', '롱': '농', '루': '누',
    '려': '여', '력': '역', '람': '남', '랍': '납', '랑': '낭', '래': '내', '랭': '냉', '략': '약', '립': '입'
}

class GlossaryCorrector:
    """Postprocessing engine that enforces exact glossary terminology and fixes Korean particles."""

    @classmethod
    def has_jongseong(cls, ch: str) -> bool:
        """Returns True if the Hangul character has a final consonant (받침)."""
        if not ch or ord(ch) < 0xAC00 or ord(ch) > 0xD7A3:
            return False
        return ((ord(ch) - 0xAC00) % 28) != 0

    @classmethod
    def is_rieul_jongseong(cls, ch: str) -> bool:
        """Returns True if the Hangul character's final consonant is 'ㄹ' (Jongseong index 8)."""
        if not ch or ord(ch) < 0xAC00 or ord(ch) > 0xD7A3:
            return False
        return ((ord(ch) - 0xAC00) % 28) == 8

    @classmethod
    def to_hanja_reading(cls, hanja_str: str) -> str:
        """Converts Chinese character string to Sino-Korean reading (한국 한자음)."""
        if not hanja_str:
            return ""
        norm_str = unicodedata.normalize('NFKC', hanja_str)
        return "".join(HANJA_READINGS.get(c, c) for c in norm_str)

    @classmethod
    def get_candidate_variants(cls, chinese_term: str) -> List[str]:
        """Generates possible erroneous representations (raw term, Sino-Korean reading, initial sound variants)."""
        if not chinese_term:
            return []
        
        variants = [chinese_term]
        norm = unicodedata.normalize('NFKC', chinese_term)
        if norm != chinese_term:
            variants.append(norm)

        hanja_base = cls.to_hanja_reading(chinese_term)
        if hanja_base and hanja_base != chinese_term:
            variants.append(hanja_base)
            # Check Korean initial sound rule on 1st syllable
            if hanja_base[0] in INITIAL_SOUND_RULES:
                initial_fixed = INITIAL_SOUND_RULES[hanja_base[0]] + hanja_base[1:]
                variants.append(initial_fixed)

        return list(set(v for v in variants if v))

    @classmethod
    def fix_josa_after_word(cls, word: str, text: str) -> str:
        """
        Recalculates and corrects Korean particles (조사) immediately following the given word
        based on the final syllable's Jongseong (받침).
        """
        if not word or not text:
            return text

        last_char = word[-1]
        has_jong = cls.has_jongseong(last_char)
        is_rieul = cls.is_rieul_jongseong(last_char)
        escaped_word = re.escape(word)

        # 1. 으로/로 variants: 으로써/로써, 으로서/로서, 으로부터/로부터, 으로/로
        def fix_ro(m):
            prefix = m.group(1)
            suffix = m.group(2) or ''
            josa = '로' if (not has_jong or is_rieul) else '으로'
            return f'{prefix}{josa}{suffix}'
        text = re.compile(rf'({escaped_word})(?:으로|로)(서|써|부터|(?=[^가-힣]|$))').sub(fix_ro, text)

        # 2. 이었/였 variants: 이었던/였던, 이었다/였다, 이었고/였고, 이었/였
        def fix_yeot(m):
            prefix = m.group(1)
            suffix = m.group(2) or ''
            josa = '이었' if has_jong else '였'
            return f'{prefix}{josa}{suffix}'
        text = re.compile(rf'({escaped_word})(?:이었|였)([다전자고지음습].*?|(?=[^가-힣]|$))').sub(fix_yeot, text)

        # 3. 이에요/예요
        def fix_eyo(m):
            prefix = m.group(1)
            josa = '이에요' if has_jong else '예요'
            return f'{prefix}{josa}'
        text = re.compile(rf'({escaped_word})(?:이에요|예요)(?=[^가-힣]|$)').sub(fix_eyo, text)

        # 4. 이라/라 variants (이라고/라고, 이라는/라는, 이라며/라며, 이라면/라면, 이라도/라도, 이라서/라서, 이라니/라니)
        def fix_ira(m):
            prefix = m.group(1)
            particle_type = m.group(2) or ''
            josa = '이라' if has_jong else '라'
            return f'{prefix}{josa}{particle_type}'
        text = re.compile(rf'({escaped_word})(?:이라|라)([고는며면도서니]|(?=[^가-힣]|$))').sub(fix_ira, text)

        # 5. 이란/란, 이나/나, 이든/든, 이며/며
        def fix_iran(m):
            prefix = m.group(1)
            josa = '이란' if has_jong else '란'
            return f'{prefix}{josa}'
        text = re.compile(rf'({escaped_word})(?:이란|란)(?=[^가-힣]|$)').sub(fix_iran, text)

        def fix_ina(m):
            prefix = m.group(1)
            josa = '이나' if has_jong else '나'
            return f'{prefix}{josa}'
        text = re.compile(rf'({escaped_word})(?:이나|나)(?=[^가-힣]|$)').sub(fix_ina, text)

        def fix_ideun(m):
            prefix = m.group(1)
            suffix = m.group(2) or ''
            josa = '이든' if has_jong else '든'
            return f'{prefix}{josa}{suffix}'
        text = re.compile(rf'({escaped_word})(?:이든|든)(지|(?=[^가-힣]|$))').sub(fix_ideun, text)

        def fix_imyeo(m):
            prefix = m.group(1)
            suffix = m.group(2) or ''
            josa = '이며' if has_jong else '며'
            return f'{prefix}{josa}{suffix}'
        text = re.compile(rf'({escaped_word})(?:이며|며)(서|(?=[^가-힣]|$))').sub(fix_imyeo, text)

        # 6. 은/는
        def fix_eun(m):
            prefix = m.group(1)
            josa = '은' if has_jong else '는'
            return f'{prefix}{josa}'
        text = re.compile(rf'({escaped_word})(?:은|는)(?=[^가-힣]|$)').sub(fix_eun, text)

        # 7. 이/가
        def fix_i_ga(m):
            prefix = m.group(1)
            josa = '이' if has_jong else '가'
            return f'{prefix}{josa}'
        text = re.compile(rf'({escaped_word})(?:이|가)(?=[^가-힣]|$)').sub(fix_i_ga, text)

        # 8. 을/를
        def fix_eul(m):
            prefix = m.group(1)
            josa = '을' if has_jong else '를'
            return f'{prefix}{josa}'
        text = re.compile(rf'({escaped_word})(?:을|를)(?=[^가-힣]|$)').sub(fix_eul, text)

        # 9. 과/와
        def fix_gwa(m):
            prefix = m.group(1)
            josa = '과' if has_jong else '와'
            return f'{prefix}{josa}'
        text = re.compile(rf'({escaped_word})(?:과|와)(?=[^가-힣]|$)').sub(fix_gwa, text)

        # 10. 아/야 (Vocative / 호칭 조사)
        def fix_ah(m):
            prefix = m.group(1)
            josa = '아' if has_jong else '야'
            return f'{prefix}{josa}'
        text = re.compile(rf'({escaped_word})(?:아|야)(?=[!?,.~^\s]|$)').sub(fix_ah, text)

        return text

    @classmethod
    def correct_text(
        cls,
        source_text: str,
        translated_text: str,
        glossary_entries: List[Dict[str, Any]],
        lang_code: str = "ZH"
    ) -> str:
        """
        Executes complete proper noun correction and Josa repair:
        1. Identifies glossary terms occurring in source_text.
        2. Replaces erroneous Hanja readings or untranslated Chinese terms with designated translation.
        3. Recalculates and fixes Korean particles (은/는, 이/가, 을/를, 과/와, etc.) for all glossary terms.
        """
        if not translated_text or not glossary_entries:
            return translated_text

        norm_src = unicodedata.normalize('NFKC', source_text)
        result = translated_text

        # 1. Find glossary entries present in source text
        matched_entries = []
        for entry in glossary_entries:
            raw_kw = str(entry.get("keyword", "")).strip()
            raw_tr = str(entry.get("translated_keyword", "")).strip()
            if not raw_kw or not raw_tr:
                continue

            kw = unicodedata.normalize('NFKC', raw_kw)
            tr = unicodedata.normalize('NFKC', raw_tr)

            if kw in norm_src or raw_kw in source_text:
                matched_entries.append({
                    "keyword": kw,
                    "translated_keyword": tr,
                    "category": entry.get("category", "고유명사")
                })

        if not matched_entries:
            return result

        # 2. Sort matched entries by Longest Match First
        matched_entries.sort(key=lambda x: len(x["keyword"]), reverse=True)

        # 3. Build replacement pairs (search_pattern, target_word)
        # Prioritize longer search patterns first
        replacement_map: List[Tuple[str, str]] = []
        target_words: Set[str] = set()

        for item in matched_entries:
            kw = item["keyword"]
            tr = item["translated_keyword"]
            target_words.add(tr)

            # Candidate A: Raw Chinese keyword (e.g. 钟九, 萧炎)
            if kw != tr:
                replacement_map.append((kw, tr))

            # Candidate B: Hanja readings and variations (e.g. 종구, 소염, 임동)
            if lang_code.upper() == "ZH":
                candidates = cls.get_candidate_variants(kw)
                for cand in candidates:
                    # Avoid 1-character replacements to prevent aggressive false positives
                    if cand and cand != tr and (len(cand) >= 2 or cand == kw):
                        replacement_map.append((cand, tr))

        # Sort replacement patterns by length descending to prevent substring collisions
        replacement_map.sort(key=lambda x: len(x[0]), reverse=True)

        # 4. Perform replacements
        for pattern, target in replacement_map:
            if pattern in result:
                result = result.replace(pattern, target)

        # 5. Fix Korean particles (조사) for all target words present in the translation
        sorted_targets = sorted(target_words, key=lambda x: len(x), reverse=True)
        for tr in sorted_targets:
            if tr in result:
                result = cls.fix_josa_after_word(tr, result)

        return result
