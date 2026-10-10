"""
OmniTranslator Pro - AI Glossary Extractor (Map-Reduce Full Document Scanner)
Extracts terms (characters, places, items, proper nouns) into JSON format with language rules,
real-time atomic checkpointing, and resume support.
"""

import json
import re
import unicodedata
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from google.genai import types as genai_types
from common.logger import setup_logger
from infra.txt_io import TxtIO
from infra.epub_io import EpubIO

logger = setup_logger("GlossaryExtractor")

class GlossaryExtractor:
    """Extracts terms from entire document text into unified JSON glossary using Gemini AI Map-Reduce pipeline with atomic checkpointing."""

    # NOTE: %PLACEHOLDER% 방식 사용 — str.format()을 쓰면 소설 본문 내 중괄호({})가
    # 템플릿 슬롯으로 오인되어 'NoneType' object has no attribute 'get_template' 등의
    # 예기치 않은 AttributeError / KeyError가 발생하므로 replace() 방식으로 교체함.
    PROMPT_TEMPLATE_PARTS = (
        "당신은 %LANG_CODE% 원작 소설/문학의 최고 전문 번역가이자 고유명사 용어집 구축 전문가입니다.\n"
        "제공된 본문 블록을 면밀히 분석하여 한국어 번역 시 일관성을 유지해야 하는 순수 고유명사만을 엄격하게 추출하십시오.\n\n"
        "## 추출 대상 카테고리 (순수 고유명사 한정):\n"
        "1. 인명 (주인공, 조연, 엑스트라 고유 이름, 풀네임, 고유 닉네임)\n"
        "2. 문파/세력/단체 (문파, 길드, 학원, 군단, 기업, 종족, 결사, 조직 등)\n"
        "3. 지명/장소 (국가, 도시, 고유 건물/던전, 지형, 차원, 영역 등)\n"
        "4. 무공/기술/아이템/설정 (고유 무공, 전용 스킬/마법, 고유 아이템, 유물, 특수 세계관 설정/시스템 등)\n\n"
        "## %LANG_CODE% 용어 추출 및 번역/음역 절대 원칙:\n"
        "%RULES%\n\n"
        "## 필수 준수 지침 (고유명사 정밀 추출 및 불량 오염 절대 방지):\n"
        "1. [진정한 고유명사 한정]: 억지로 개수를 채우려 하지 마십시오. 본문에 실제로 존재하는 엄격한 고유명사만 정밀하게 추출하십시오.\n"
        "2. [추출 절대 금지 대상 - 위반 시 무효 처리]:\n"
        "   - 단일 글자(1음절 한자, 예: '觉', '它', '封', '净', '张', '龙' 등 성씨, 대명사, 무의미 조각) 추출 절대 금지 (최소 2글자 이상 단어만 추출).\n"
        "   - 일상 일반명사/동사/형용사(예: 시간, 공간, 신체부위, 가구, 일상용품, 감정, 동작, 단순 직업/인칭) 추출 절대 금지.\n"
        "   - 구문/문장/퀘스트 지문/에피소드 제목/대련/시구/작가의 말 등 문맥 전체 추출 절대 금지.\n"
        "   - 사자성어, 속담, 일상 관용구 추출 절대 금지.\n"
        "3. 본문에 실제로 등장한 횟수(occurrence_count)를 최소 1 이상으로 정확히 기재하십시오.\n"
        "4. 반드시 아래 JSON 배열 형식으로만 응답하고, 마크다운 코드블록이나 부가 설명/사고 과정을 일체 포함하지 마십시오.\n\n"
        "## 소설 본문 블록:\n"
        "```\n%TEXT%\n```\n\n"
        "## JSON 출력 형식:\n"
        "[\n"
        '  {"keyword": "원문고유명사", "translated_keyword": "한국어번역", "category": "인명/문파/세력/지명/무공/아이템/설정", "occurrence_count": 1}\n'
        "]"
    )

    @classmethod
    def _build_prompt(cls, lang_code: str, rules: str, text: str) -> str:
        """
        소설 본문(text) 안에 중괄호({})가 포함되어 있어도 str.format()이
        오작동하지 않도록 str.replace()로 안전하게 프롬프트를 조립합니다.

        [버그 수정] 기존 PROMPT_TEMPLATE.format(lang_code=..., rules=..., text=block)
        방식에서 block 내 '{variable}' 형태의 중괄호가 있을 경우
        'NoneType' object has no attribute 'get_template' (Jinja2 내부 에러 유사 패턴)
        또는 KeyError 가 발생하는 문제를 해결합니다.
        """
        return (
            cls.PROMPT_TEMPLATE_PARTS
            .replace("%LANG_CODE%", lang_code)
            .replace("%RULES%", rules)
            .replace("%TEXT%", text)
        )

    LANG_RULES = {
        "ZH": (
            "1. [인명(등장인물) -> 표준 중국어 병음 음역(Pinyin Transliteration) 필수 원칙]:\n"
            "   - 중국 소설 인명 및 등장인물 고유명사는 절대로 한국식 한자 독음(Hanja-eum, 예: 钟九->종구 X, 张小华->장소화 X, 萧炎->소염 X, 林动->임동 X, 顾夜白->고야백 X, 楚风->초풍 X, 韩立->한립 X, 孟浩->맹호 X)으로 변환하지 마십시오.\n"
            "   - 반드시 표준 중국어 외래어 표기법 및 병음 발음(Pinyin Transliteration) 음역을 최우선 원칙으로 적용하여 추출하십시오.\n"
            "   * 표준 인명 음역 예시: 钟九 -> 종지우, 张小华 -> 장샤오화, 萧炎 -> 샤오옌, 林动 -> 린둥, 顾夜白 -> 구예바이, 楚风 -> 추펑, 叶修 -> 예슈, 唐三 -> 탕싼, 韩立 -> 한리, 孟浩 -> 멍하오, 白小纯 -> 바이샤오춘, 李火旺 -> 리훠왕\n"
            "   * 단, 삼국지/실존 역사적 인물(예: 诸葛亮->제갈량, 曹操->조조, 关羽->관우 등)은 한국식 한자 독음 관례를 적용하십시오.\n"
            "   * 인명 호칭 분리: 인물 이름 뒤나 앞에 붙는 호칭(哥, 姐, 师兄, 师姐, 师弟, 师妹, 叔, 伯, 爷, 弟, 妹, 宗主, 掌门, 前辈, 先生, 小姐 등)은 분리하여 '순수 이름 본체(최소 2글자 이상)'만 keyword 및 translated_keyword로 추출하십시오. (예: '钟九哥' -> keyword: '钟九', translated_keyword: '종지우', category: '인명')\n\n"
            "2. [문파/지명/무공/기술/아이템/설정 -> 한국식 한자 독음(음차) 및 장르 관례 준수 원칙]:\n"
            "   - 무협/선협/판타지의 문파·세력, 지명·장소, 무공·기술, 아이템·도구, 크툴루/SF 설정 등은 한국식 한자 독음(음차) 및 장르 관례에 맞는 한국어 용어를 준수하여 매핑하십시오.\n"
            "   * 올바른 문파 예시: 少林寺 -> 소림사, 华山派 -> 화산파, 武当派 -> 무당파, 峨眉派 -> 아미파, 魔教 -> 마교, 青云门 -> 청운문\n"
            "   * 올바른 지명 예시: 洛阳 -> 낙양, 长安 -> 장안, 金陵 -> 금릉, 泰山 -> 태산, 中原 -> 중원, 蜀山 -> 촉산\n"
            "   * 올바른 무공/기술 예시: 降龙十八掌 -> 항룡십팔장, 独孤九剑 -> 독고구검, 九阳神功 -> 구양신공, 辟邪剑法 -> 벽사검법, 金钟罩 -> 금종조, 凌波微步 -> 능파미보\n"
            "   * 올바른 설정/세력 예시: 天机局 -> 천기국, 黄昏社 -> 황혼사, 界域 -> 계역, 灭世 -> 멸세, 筑基 -> 축기, 金丹 -> 금단, 元婴 -> 원영\n\n"
            "3. [게임 판타지/가상현실/SF 장르 고유명사 및 외래어 특화 원칙]:\n"
            "   - 소설 및 게임 대표 타이틀: '惊悚乐园' -> '스릴러 파크' (경송낙원 X).\n"
            "   - 게임 시스템 '专精'(전문화/마스터리): 格斗专精->격투 전문화, 射击专精->사격 전문화 등 '전문화'로 통일 (전정 X).\n"
            "   - 게임 개발사: '梦公司' -> '드림사' 또는 '드림 컴퍼니' (몽회사 X).\n"
            "   - 작가 필명: '三天两觉' -> '삼천양각'.\n"
            "   - 외래어 브랜드, 영문 모델명, SCP 코드(예: SCP-500, Anomalous 등)는 원문/외래어 표기법을 준수하십시오.\n\n"
            "4. [일반명사/동사/형용사/사물/화폐 음역 및 추출 절대 금지]:\n"
            "   - 钱(돈/금전), 银/银子(은/은자), 金(금), 刀(도/칼), 剑(검/칼), 枪(창/총), 车(차), 船(배), 酒(술), 茶(차), 肉(고기), 药(약), 符(부적), 文(문), 两(냥) 등 일반 사물·화폐·단위는 절대로 인명으로 추출하거나 병음으로 음역하지 마십시오.\n"
            "   - 男人(남자), 女人(여자), 老人(노인), 年轻人(청년), 少年(소년), 少女(소녀), 医生(의사), 警察(경찰) 등 보통명사는 인명 음역을 엄격히 금지합니다.\n"
            "   - 시간, 방/공간, 신체부위, 가전/가구, 단순 감정/동작, 사자성어는 고유명사가 아니므로 절대 추출하지 마십시오."
        ),
        "JA": (
            "1. 일본어 라이트노벨 인명, 지명, 루비 표기, 호칭(군, 양, 씨 등)을 한국 공식 발매본 형식으로 자연스럽게 번역/음역하십시오.\n"
            "2. 한자 고유명사와 가타카나 외래어 표기법을 정확히 적용하십시오.\n"
            "3. 단일 글자, 일상 보통명사, 문장형 지문은 추출하지 마십시오."
        ),
        "EN": (
            "1. 영어 인명, 지명, 판타지/SF 고유명사는 국립국어원 외래어 표기법에 맞춰 한글로 자연스럽게 음역하십시오.\n"
            "2. 일반 명사, 관용구, 문장형 지문은 추출하지 마십시오."
        )
    }



    @classmethod
    def get_tmp_checkpoint_path(cls, file_path: Path) -> Path:
        """Returns the temporary checkpoint path for glossary extraction."""
        return file_path.parent / f"{file_path.name}.glossary.tmp.json"

    @classmethod
    def save_checkpoint(cls, checkpoint_path: Path, data: Dict[str, Any]) -> None:
        """Atomically and safely saves intermediate glossary extraction progress with fsync."""
        import os
        import time
        import uuid
        
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = checkpoint_path.parent / f"{checkpoint_path.name}.tmp_{os.getpid()}_{uuid.uuid4().hex[:8]}"
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    os.replace(temp_path, checkpoint_path)
                    break
                except (PermissionError, OSError):
                    if attempt < max_retries - 1:
                        time.sleep(0.05 * (2 ** attempt))
                    else:
                        import shutil
                        shutil.copyfile(temp_path, checkpoint_path)
                        try:
                            temp_path.unlink()
                        except Exception:
                            pass
            logger.debug(f"Atomic glossary checkpoint saved: {checkpoint_path} ({len(data.get('completed_blocks', []))} blocks done)")
        except Exception as e:
            logger.error(f"Failed to save atomic glossary checkpoint ({checkpoint_path}): {e}")
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass

    @classmethod
    def load_checkpoint(cls, checkpoint_path: Path) -> Optional[Dict[str, Any]]:
        """Loads intermediate glossary extraction progress."""
        if not checkpoint_path.exists():
            return None
        try:
            with open(checkpoint_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load glossary checkpoint ({checkpoint_path}): {e}")
            return None

    @classmethod
    def remove_checkpoint(cls, checkpoint_path: Path) -> None:
        """Removes the temporary glossary checkpoint file upon clean completion."""
        if checkpoint_path.exists():
            try:
                checkpoint_path.unlink()
                logger.info(f"Removed temporary glossary checkpoint: {checkpoint_path}")
            except Exception as e:
                logger.error(f"Failed to remove temporary glossary checkpoint ({checkpoint_path}): {e}")

    @classmethod
    def load_document_text(cls, file_path: Path) -> str:
        """Loads and converts any supported file (TXT/EPUB) to pure plain text."""
        if not file_path.exists():
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")

        suffix = file_path.suffix.lower()
        if suffix == ".epub":
            return EpubIO.extract_plain_text(file_path)
        else:
            return TxtIO.read_text_file(file_path)

    @classmethod
    def split_into_blocks(cls, text: str, block_size: int = 18000) -> List[str]:
        """Splits full document text into ~15k-20k character chunks preserving paragraph boundaries."""
        if not text or not text.strip():
            return []

        paragraphs = text.split("\n")
        blocks = []
        current_block = []
        current_len = 0

        for p in paragraphs:
            p_len = len(p) + 1
            if current_len + p_len > block_size and current_block:
                blocks.append("\n".join(current_block).strip())
                current_block = [p]
                current_len = p_len
            else:
                current_block.append(p)
                current_len += p_len

        if current_block:
            last_text = "\n".join(current_block).strip()
            if last_text:
                blocks.append(last_text)

        return blocks

    @classmethod
    def _parse_terms_json(cls, raw_response: str) -> List[Dict[str, Any]]:
        """Safely parses JSON array from LLM response, stripping think tags and markdown blocks."""
        if not raw_response:
            return []

        cleaned = re.sub(r'<(?:think|thought|thinking|reflection)>[\s\S]*?</(?:think|thought|thinking|reflection)>', '', raw_response, flags=re.IGNORECASE)
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r'```$', '', cleaned.strip(), flags=re.MULTILINE).strip()

        # 1. Try standard json.loads
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass

        # 2. Try regex extraction of JSON array [ ... ]
        array_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', cleaned)
        if array_match:
            try:
                parsed = json.loads(array_match.group(0))
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass

        # 3. Fallback: extract individual JSON objects using regex
        results = []
        pattern = re.compile(
            r'\{\s*"keyword"\s*:\s*"([^"]+)"\s*,\s*"translated_keyword"\s*:\s*"([^"]+)"'
            r'(?:\s*,\s*"category"\s*:\s*"([^"]+)")?'
            r'(?:\s*,\s*"occurrence_count"\s*:\s*(\d+))?\s*\}',
            re.DOTALL
        )
        for m in pattern.finditer(cleaned):
            kw, tr, cat, cnt = m.groups()
            results.append({
                "keyword": kw.strip(),
                "translated_keyword": tr.strip(),
                "category": cat.strip() if cat else "고유명사",
                "occurrence_count": int(cnt) if cnt else 1
            })

        return results

    # 장르 및 고유명사 표준 정규화 사전
    ZH_GENRE_CORRECTIONS = {
        "惊悚乐园": ("스릴러 파크", "작품명/게임명"),
        "三天两觉": ("삼천양각", "인명/작가"),
        "梦公司": ("드림사", "문파/세력/단체"),
        "格斗专精": ("격투 전문화", "설정/시스템"),
        "射击专精": ("사격 전문화", "설정/시스템"),
        "侦查专精": ("정찰 전문화", "설정/시스템"),
        "器械专精": ("기계 전문화", "설정/시스템"),
        "医疗专精": ("의료 전문화", "설정/시스템"),
        "灵术专精": ("영술 전문화", "설정/시스템"),
        "召唤专精": ("소환 전문화", "설정/시스템"),
        "通用专精": ("통용 전문화", "설정/시스템"),
        "雨姐": ("위 누나", "인명/호칭"),
        "诸葛亮": ("제갈량", "인명"),
        "似雨若雨": ("쓰위뤄위", "인명"),
        "疯不觉": ("펑부쥐에", "인명"),
        "封不觉": ("펑부쥐에", "인명"),
        "王叹之": ("왕탄즈", "인명"),
        "小叹": ("샤오탄", "인명"),
        "觉哥": ("쥐에 형", "인명/호칭"),
        "地狱前线": ("지옥전선", "문파/세력/단체"),
        "惊吓值": ("공포 수치", "설정/시스템"),
    }

    # 신체 부위 보통명사 블랙리스트
    BODY_PARTS = {
        "手腕", "脚踝", "胸口", "后背", "手指", "脚趾", "额头", "下巴", "眉毛", "脖子", "膝盖",
        "肩膀", "牙齿", "舌头", "头发", "肌肉", "骨骼", "血液", "内脏", "皮肤", "腹部", "腰部",
        "大腿", "小腿", "手掌", "脚掌", "脸颊", "嘴唇", "耳朵", "鼻梁", "眼眶"
    }

    # 일상 보통명사 / 동사 / 형용사 / 사자성어 블랙리스트
    COMMON_WORDS_BLACK_LIST = {
        "时间", "地点", "位置", "方向", "距离", "速度", "数量", "程度", "范围", "原因", "结果", "情况", "状况", "问题",
        "事情", "事件", "事实", "真相", "秘密", "消息", "信息", "数据", "记录", "报告", "计划", "方案", "方法", "方式",
        "手段", "目的", "目标", "标准", "规则", "制度", "法律", "命令", "指示", "任务", "工作", "职业", "身份", "地位",
        "关系", "感情", "态度", "心情", "情绪", "感觉", "心理", "思想", "观念", "意识", "记忆", "回忆", "梦境", "幻想",
        "现实", "世界", "社会", "时代", "历史", "未来", "过去", "现在", "今天", "明天", "昨天", "早上", "中午", "晚上",
        "深夜", "黎明", "黄昏", "白天", "黑夜", "春天", "夏天", "秋天", "冬天", "时刻", "瞬间", "片刻", "平时", "日常",
        "生活", "生命", "身体", "头部", "脸部", "眼睛", "耳朵", "鼻子", "嘴巴", "牙齿", "舌头", "头发", "脖子", "肩膀",
        "手臂", "手掌", "手指", "胸口", "腹部", "后背", "腰部", "大腿", "小腿", "脚掌", "脚趾", "肌肉", "骨骼", "血液",
        "内脏", "皮肤", "影子", "声音", "脚步", "呼吸", "心跳", "目光", "眼神", "脸色", "表情", "动作", "姿势", "身形",
        "身材", "男人", "女人", "老人", "老人家", "老头", "老太", "孩子", "小孩", "婴儿", "少年", "少女", "青年", "中年",
        "病人", "医生", "护士", "警察", "军人", "士兵", "司机", "乘客", "读者", "作者", "学生", "老师", "师傅", "徒弟",
        "老板", "员工", "顾客", "客人", "主人", "仆人", "朋友", "同学", "同事", "邻居", "亲戚", "父母", "父亲", "母亲",
        "爸爸", "妈妈", "儿子", "女儿", "兄弟", "姐妹", "哥哥", "弟弟", "姐姐", "妹妹", "丈夫", "妻子", "人类", "动物",
        "植物", "生物", "昆虫", "鸟类", "鱼类", "桌子", "椅子", "床", "柜子", "箱子", "抽屉", "镜子", "灯", "钟",
        "电话", "手机", "电脑", "电视", "纸", "笔", "书", "本子", "信", "照片", "钱包", "钥匙", "衣服", "外套",
        "裤子", "裙子", "鞋子", "袜子", "帽子", "手套", "眼镜", "手表", "首饰", "刀叉", "碗", "盘子", "杯子", "瓶子",
        "筷子", "勺子", "食物", "粮食", "面包", "米饭", "面条", "肉", "菜", "水果", "水", "茶", "咖啡", "酒", "烟",
        "药", "毒药", "房间", "大厅", "走廊", "楼梯", "屋顶", "地下室", "门", "窗户", "墙壁", "天花板", "地板",
        "空调", "冰柜", "冰箱", "洗衣机", "国家", "监狱", "案发现场", "大石头", "钝器", "长棍", "污水", "威慑", "威胁",
        "努力", "愤怒", "悲伤", "高兴", "恐惧", "紧张", "冷静", "普通", "奇怪", "正常", "简单", "复杂", "危险", "安全",
        "重要", "关键", "死亡", "生存", "开始", "结束", "离开", "回来", "进入", "出来", "出现", "消失", "发生", "发现",
        "知道", "认识", "明白", "理解", "思考", "分析", "判断", "推测", "总结", "修改", "重写", "放弃", "继续", "停止",
        "完成", "成功", "失败", "保护", "破坏", "攻击", "防御", "战斗", "移动", "休息", "睡觉", "吃饭", "喝水", "说话",
        "两人", "暴发户", "英国佬儿", "不服", "逼格", "举证", "不良效应", "地震", "恪守原则", "彻底毁灭", "设计好", "主要人物",
        "横向比对", "绑定装备", "果王", "方针", "简谱", "怀疑对象", "网游产品", "破防", "闪电公测", "圣骑士", "压迫测试",
        "空手而归", "见怪不怪", "不了了之", "此地无银三百两", "粗中有细", "输得心服口服", "腿脚不便", "气势凌人", "装的",
        "财势显赫", "强烈自然灾害", "妖魔鬼怪", "天雷", "修改重写", "公式", "神格", "棋局", "时间线", "短篇小说", "大体实力",
        "倒弹如流", "东西", "事情", "东西南北", "上下左右", "前前后后", "里里外外", "得了便宜卖乖", "拉丁裔", "策反", "谷底", "石岸"
    }

    # 한국어 보통명사 일치 블랙리스트
    KR_COMMON_BLACK_LIST = {
        "시간", "위치", "방향", "거리", "속도", "수량", "원인", "결과", "상황", "문제", "사실", "진실", "비밀",
        "정보", "데이터", "기록", "보고", "계획", "방법", "방식", "수단", "목적", "목표", "기준", "규칙", "제도",
        "법률", "명령", "임무", "업무", "직업", "신분", "지위", "관계", "감정", "태도", "기분", "심리", "사상",
        "기억", "현실", "세계", "사회", "시대", "역사", "미래", "과거", "현재", "오늘", "내일", "어제", "순간",
        "평소", "일상", "생활", "생명", "신체", "머리", "얼굴", "눈", "코", "입", "귀", "손", "발", "몸",
        "피부", "그림자", "목소리", "발소리", "호흡", "시선", "표정", "동작", "자세", "남자", "여자", "노인",
        "아이", "소년", "소녀", "청년", "중년", "환자", "의사", "간호사", "경찰", "군인", "병사", "운전사",
        "승객", "독자", "작가", "학생", "선생", "손님", "주인", "하인", "친구", "동료", "부모", "아버지",
        "어머니", "인간", "동물", "식물", "생물", "건물", "집", "방", "거실", "복도", "계단", "지하실", "문",
        "창문", "벽", "천장", "바닥", "탁자", "테이블", "의자", "침대", "상자", "거울", "조명", "전화",
        "휴대폰", "컴퓨터", "종이", "펜", "책", "편지", "사진", "지갑", "열쇠", "옷", "바지", "신발", "모자",
        "장갑", "안경", "시계", "그릇", "접시", "컵", "병", "음식", "밥", "고기", "채소", "과일", "차",
        "커피", "술", "담배", "약", "에어컨", "냉장고", "냉동고", "국가", "감옥", "사건 현장", "큰 돌",
        "둔기", "장곤", "오수", "위협", "노력", "분노", "비명", "슬픔", "기쁨", "공포", "긴장", "냉정",
        "보통", "이상", "특별", "중요", "위험", "안전", "사망", "생존", "시작", "종료", "퇴장", "복귀",
        "진입", "출현", "소멸", "발생", "발견", "이해", "느낌", "생각", "준비", "결정", "선택", "포기",
        "지속", "중지", "완료", "성공", "실패", "확인", "증명", "설명", "소개", "사고", "분석", "판단",
        "추측", "요약", "수정", "보호", "파괴", "공격", "방어", "전투", "이동", "휴식", "수면", "식사",
        "대화", "2명", "졸부", "영국인", "폼", "입증", "지진", "방침", "간보", "의심 대상", "단편 소설",
        "온라인 게임 제품", "방어 파괴", "번개 공개 테스트", "성기사", "압박 테스트", "놀라지 않음", "전문 완료",
        "골짜기 바닥", "돌 제방", "라틴계", "회유", "손목", "긴 깃털", "영상 연결", "단련 방법", "무패 기록",
        "길드 종합 능력", "상해 사고", "기본 속성", "회사의 동료", "3층 창고", "무균실", "금속실"
    }

    GENERIC_COMPOUND_PATTERNS = [
        re.compile(r"^.*(方法|方式|纪录|记录|事故|属性|功能|能力|实力|连接|链接|测试|计划|规则|产品|制品|装置|设施)$"),
        re.compile(r"^.*(储藏室|无菌室|金属室|休息室|更衣室|会议室|办公室|手术室|实验室|配电室|洗手间|厕所|浴室)$"),
        re.compile(r"^.*(大石头|长棍|短棍|木棍|铁棍|长羽毛|大铁扇|小刀|菜刀|水果刀|折凳|椅子|桌子|柜子)$"),
        re.compile(r"^.*的(同事|朋友|同学|家人|父母|敌人|对手|邻居|亲戚|上司|下属)$")
    ]

    @classmethod
    def _validate_and_clean_term(
        cls,
        kw: str,
        tr: str,
        cat: str,
        lang_code: str = "ZH"
    ) -> Optional[tuple[str, str, str]]:
        """
        Thoroughly validates and cleanses extracted glossary terms using heuristic filters,
        length constraints, punctuation checks, common word blacklists, and genre normalizers.
        Returns (keyword, translated_keyword, category) or None if invalid.
        """
        if not kw or not tr:
            return None

        kw = unicodedata.normalize('NFKC', kw).strip()
        tr = unicodedata.normalize('NFKC', tr).strip()
        cat = cat.strip() if cat else "고유명사"

        # 1. 단일 음절 (1글자) 및 무의미 기호/번호 절대 차단
        if len(kw) <= 1:
            return None
        if re.match(r"^\d+号$", kw) or re.match(r"^\d+\-\d+名$", kw) or kw in ["喵", "哼", "啊", "喂", "哈哈", "106号"]:
            return None

        # 2. 문장부호 포함 구문 차단 (영문/코드명 예외)
        has_hanja = bool(re.search(r"[\u4e00-\u9fff]", kw))
        is_ascii_code = bool(re.match(r"^[A-Za-z0-9\.\-\_\s\+\#\:\/]+$", kw))
        if has_hanja and re.search(r"[,，。！？!?；;:：~～…—]", kw):
            return None

        # 3. 과도하게 긴 구문 / 문장형 차단
        if has_hanja and len(kw) >= 12 and not is_ascii_code:
            return None

        # 4. 챕터/회차/부제/작가의 말 서술 차단
        if any(phrase in kw for phrase in ["篇(完)", "篇(上)", "篇(中)", "篇(下)", "全文完", "上架感言", "写在最后", "我是写手", "章 ", "特别篇", "番外篇"]):
            return None
        if re.search(r"\(上\)|\(中\)|\(下\)", kw):
            return None
        if kw.startswith("第") and any(kw.endswith(s) for s in ["章", "节", "回", "卷", "篇"]):
            return None

        # 5. 인용부호 오염 정제
        tr = re.sub(r"['\"`“”‘’]", "", tr).strip()
        if not tr or len(tr) < 1:
            return None

        # 6. 서술어/조사형 종결 번역 차단
        if re.search(r"(하다|되다|이다|였다|했다|한다|된다|있다|없다|에서|으로|에게|한테|스러운|스럽다|않다|모르다|바라다|말하다)$", tr):
            if len(tr) >= 3 and tr not in ["마스터", "안드레이", "발키리", "사이드", "블레이드"]:
                return None

        # 7. 미번역 한자 원문 방치 차단
        if tr == kw and has_hanja and len(kw) > 1 and kw not in ["SCP-500"]:
            return None

        # 8. 신체 부위 및 대표 보통명사 블랙리스트 차단
        if kw in cls.BODY_PARTS or tr in {"손목", "발목", "가슴", "등", "손가락", "발가락", "이마", "턱", "눈썹", "목", "무릎", "어깨"}:
            return None
        if kw in cls.COMMON_WORDS_BLACK_LIST or tr in cls.KR_COMMON_BLACK_LIST:
            return None

        # 9. 일반 복합어 구문 차단
        for p in cls.GENERIC_COMPOUND_PATTERNS:
            if p.match(kw):
                return None

        # 10. 특수 장르 고유명사 보정 사전 적용 (스릴러 파크, 삼천양각, 드림사, 전문화 등)
        if lang_code.upper() == "ZH":
            if kw in cls.ZH_GENRE_CORRECTIONS:
                tr, cat = cls.ZH_GENRE_CORRECTIONS[kw]
            elif kw.endswith("专精") and tr.endswith("전정"):
                tr = kw[:-2] + " 전문화"
                cat = "설정/시스템"

            # 호칭 분리 (이름 뒤의 호칭 제거하되 순수 이름 본체가 최소 2자 이상인 경우만)
            honorific_suffixes = (
                '师兄', '师姐', '师弟', '师妹', '宗主', '掌门', '前辈', '先生', '小姐',
                '大哥', '小哥', '大姐', '小妹', '老弟', '老哥', '老祖', '道友', '道长',
                '师尊', '阁下', '大人', '陛下', '殿下', '哥', '姐', '叔', '伯', '爷', '弟', '妹'
            )
            for suffix in honorific_suffixes:
                if kw.endswith(suffix) and len(kw) - len(suffix) >= 2:
                    kw = kw[:-len(suffix)].strip()
                    break

            # 단독 호칭 정규화
            generic_honorific_map = {
                '先生': '선생님', '女士': '여사', '小姐': '아가씨', '师傅': '사부',
                '师父': '사부님', '同志': '동지', '阁下': '귀하', '前辈': '선배님',
                '道友': '도우', '老夫': '노부', '本座': '본좌', '弟子': '제자'
            }
            if kw in generic_honorific_map:
                cat = "호칭"
                tr = generic_honorific_map[kw]

        return kw, tr, cat

    @classmethod
    def _clean_extracted_term(cls, kw: str, tr: str, cat: str, lang_code: str) -> tuple[str, str, str]:
        """Maintains backward compatibility with older callers."""
        validated = cls._validate_and_clean_term(kw, tr, cat, lang_code)
        if validated:
            return validated
        return unicodedata.normalize('NFKC', kw).strip(), unicodedata.normalize('NFKC', tr).strip(), cat

    @classmethod
    async def extract_glossary_from_file_async(
        cls,
        gemini_client: Any,
        file_path: Path,
        lang_code: str = "JA",
        model_name: str = "gemini-3.1-pro-preview",
        block_size: int = 18000,
        progress_callback: Optional[Callable[[int, int, int], None]] = None,
        resume_existing: bool = True
    ) -> List[Dict[str, Any]]:
        """Full-document Map-Reduce AI glossary extraction from file path with automatic checkpoint recovery."""
        text_content = cls.load_document_text(file_path)
        checkpoint_path = cls.get_tmp_checkpoint_path(file_path) if resume_existing else None
        return await cls.extract_glossary_from_text_async(
            gemini_client=gemini_client,
            text_content=text_content,
            lang_code=lang_code,
            model_name=model_name,
            block_size=block_size,
            progress_callback=progress_callback,
            checkpoint_path=checkpoint_path
        )

    @classmethod
    async def extract_glossary_from_text_async(
        cls,
        gemini_client: Any,
        text_content: str,
        lang_code: str = "JA",
        model_name: str = "gemini-3.1-pro-preview",
        block_size: int = 18000,
        progress_callback: Optional[Callable[[int, int, int], None]] = None,
        checkpoint_path: Optional[Path] = None
    ) -> List[Dict[str, Any]]:
        """Extracts terms from all text blocks with real-time atomic checkpoint saving and resumption."""
        # ── [버그 방어] 입력 파라미터 None 가드 ──────────────────────────────────────
        # lang_code가 None이면 lang_code.upper()에서 AttributeError가 발생하고,
        # gemini_client가 None이면 generate_text_async 호출 시
        # 'NoneType' object has no attribute 'get_template' 등의 오류가 발생함.
        if not lang_code:
            logger.warning(
                "extract_glossary_from_text_async: lang_code가 None/빈값입니다. "
                "기본값 'JA'로 대체합니다."
            )
            lang_code = "JA"
        lang_code = str(lang_code).upper().strip() or "JA"

        if gemini_client is None:
            raise ValueError(
                "extract_glossary_from_text_async: gemini_client가 None입니다. "
                "Orchestrator 초기화 시 GeminiClient가 정상적으로 주입되었는지 확인하세요."
            )

        if not text_content or not str(text_content).strip():
            logger.warning("extract_glossary_from_text_async: 빈 text_content가 전달되었습니다.")
            return []
        # ─────────────────────────────────────────────────────────────────────────────

        blocks = cls.split_into_blocks(text_content, block_size=block_size)
        total_blocks = len(blocks)
        if total_blocks == 0:
            logger.warning("Empty text provided for glossary extraction.")
            return []

        rules = cls.LANG_RULES.get(lang_code, cls.LANG_RULES["JA"])
        merged_glossary: Dict[str, Dict[str, Any]] = {}
        trans_counts: Dict[str, Dict[str, int]] = {}
        completed_blocks: List[int] = []

        # 1. Load existing checkpoint if present
        if checkpoint_path and checkpoint_path.exists():
            ckpt = cls.load_checkpoint(checkpoint_path)
            if ckpt and isinstance(ckpt, dict):
                merged_glossary = ckpt.get("merged_glossary", {})
                trans_counts = ckpt.get("trans_counts", {})
                completed_blocks = ckpt.get("completed_blocks", [])
                logger.info(
                    f"Resuming glossary extraction from checkpoint ({checkpoint_path.name}): "
                    f"{len(completed_blocks)}/{total_blocks} blocks already extracted ({len(merged_glossary)} terms)."
                )
                if progress_callback and completed_blocks:
                    progress_callback(len(completed_blocks), total_blocks, len(merged_glossary))

        logger.info(f"Starting glossary extraction: {total_blocks} total blocks ({len(completed_blocks)} already completed).")

        for idx, block in enumerate(blocks, start=1):
            if idx in completed_blocks:
                logger.info(f"Glossary block {idx}/{total_blocks} already in checkpoint. Bypassing...")
                continue

            prompt_str = cls._build_prompt(
                lang_code=lang_code,
                rules=rules,
                text=block
            )

            prompt_contents = [
                genai_types.Content(
                    role="user",
                    parts=[genai_types.Part.from_text(text=prompt_str)]
                )
            ]

            extraction_sys_instruction = (
                f"당신은 {lang_code} 원작 소설/문학의 최고 전문 번역가이자 고유명사 용어집 구축 전문가입니다.\n"
                f"{rules}"
            )

            try:
                logger.info(f"Extracting glossary block {idx}/{total_blocks} ({len(block)} chars)...")
                raw_response = await gemini_client.generate_text_async(
                    prompt_contents=prompt_contents,
                    model_name=model_name,
                    temperature=0.2,
                    top_p=0.8,
                    thinking_budget=0,
                    system_instruction=extraction_sys_instruction
                )

                extracted_items = cls._parse_terms_json(raw_response)
                logger.info(f"Block {idx}/{total_blocks}: Extracted {len(extracted_items)} raw terms.")

                # Reduce / Merge into merged_glossary with strict heuristic validation
                for item in extracted_items:
                    raw_kw = str(item.get("keyword", "")).strip()
                    raw_tr = str(item.get("translated_keyword", "")).strip()
                    raw_cat = str(item.get("category", "고유명사")).strip() or "고유명사"
                    raw_cnt = item.get("occurrence_count", 1)
                    cnt = int(raw_cnt) if str(raw_cnt).isdigit() and int(raw_cnt) > 0 else 1

                    # Heuristic validation and cleansing
                    cleaned = cls._validate_and_clean_term(raw_kw, raw_tr, raw_cat, lang_code)
                    if not cleaned:
                        continue
                    kw, tr, cat = cleaned

                    if not kw or not tr or len(kw) < 2:
                        continue

                    if kw not in merged_glossary:
                        merged_glossary[kw] = {
                            "keyword": kw,
                            "translated_keyword": tr,
                            "category": cat,
                            "occurrence_count": cnt
                        }
                        trans_counts[kw] = {tr: cnt}
                    else:
                        merged_glossary[kw]["occurrence_count"] += cnt
                        if tr not in trans_counts[kw]:
                            trans_counts[kw][tr] = 0
                        trans_counts[kw][tr] += cnt

                        # Elect translation with highest aggregate count
                        best_tr = max(trans_counts[kw].items(), key=lambda x: x[1])[0]
                        merged_glossary[kw]["translated_keyword"] = best_tr

                        if cat != "고유명사" and merged_glossary[kw]["category"] == "고유명사":
                            merged_glossary[kw]["category"] = cat

                completed_blocks.append(idx)

                # Real-time atomic checkpoint save
                if checkpoint_path:
                    ckpt_data = {
                        "total_blocks": total_blocks,
                        "completed_blocks": completed_blocks,
                        "merged_glossary": merged_glossary,
                        "trans_counts": trans_counts
                    }
                    cls.save_checkpoint(checkpoint_path, ckpt_data)

            except Exception as e:
                logger.error(f"Error extracting terms from block {idx}/{total_blocks}: {e}")

            if progress_callback:
                progress_callback(len(completed_blocks), total_blocks, len(merged_glossary))

        # Sort by occurrence_count descending, then by keyword length descending (Longest Match First)
        final_entries = sorted(
            merged_glossary.values(),
            key=lambda x: (int(x.get("occurrence_count", 1)), len(str(x.get("keyword", "")))),
            reverse=True
        )

        # Remove temporary checkpoint upon 100% completion
        if checkpoint_path and len(completed_blocks) == total_blocks:
            cls.remove_checkpoint(checkpoint_path)

        logger.info(f"Full-document glossary extraction complete: {len(final_entries)} unique terms aggregated from {total_blocks} blocks.")
        return final_entries

    @classmethod
    async def extract_glossary_async(
        cls,
        gemini_client: Any,
        text_content: str,
        lang_code: str = "JA",
        model_name: str = "gemini-3.1-pro-preview",
        progress_callback: Optional[Callable[[int, int, int], None]] = None
    ) -> List[Dict[str, Any]]:
        """Maintains backward compatibility with older callers."""
        return await cls.extract_glossary_from_text_async(
            gemini_client=gemini_client,
            text_content=text_content,
            lang_code=lang_code,
            model_name=model_name,
            progress_callback=progress_callback
        )

    @classmethod
    def save_glossary_json(cls, entries: List[Dict[str, Any]], filepath: Path) -> None:
        """Saves final verified glossary JSON file atomically with fsync."""
        import os
        import time
        import uuid
        
        filepath.parent.mkdir(parents=True, exist_ok=True)
        temp_path = filepath.parent / f"{filepath.name}.tmp_{os.getpid()}_{uuid.uuid4().hex[:8]}"
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(entries, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    os.replace(temp_path, filepath)
                    break
                except (PermissionError, OSError):
                    if attempt < max_retries - 1:
                        time.sleep(0.05 * (2 ** attempt))
                    else:
                        import shutil
                        shutil.copyfile(temp_path, filepath)
                        try:
                            temp_path.unlink()
                        except Exception:
                            pass
            logger.info(f"Saved {len(entries)} glossary entries to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save glossary JSON ({filepath}): {e}")
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass

    @classmethod
    def load_glossary_json(cls, filepath: Path) -> List[Dict[str, Any]]:
        """Loads existing glossary JSON file."""
        if not filepath.exists():
            return []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"Failed to load glossary JSON ({filepath}): {e}")
            return []
