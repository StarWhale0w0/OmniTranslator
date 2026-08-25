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

    PROMPT_TEMPLATE = (
        "당신은 {lang_code} 원작 소설/문학의 최고 전문 번역가이자 고유명사 용어집 구축 전문가입니다.\n"
        "제공된 본문 블록을 면밀히 분석하여 한국어 번역 시 일관성을 유지해야 하는 모든 고유명사를 빠짐없이 전부 추출하십시오.\n\n"
        "## 추출 대상 카테고리:\n"
        "1. 인명 (주인공, 조연, 엑스트라, 별명, 풀네임 등)\n"
        "2. 문파/세력/단체 (문파, 길드, 학원, 군단, 기업, 종족, 조직 등)\n"
        "3. 지명/장소 (국가, 도시, 건물, 지형, 차원, 영역 등)\n"
        "4. 무공/기술/아이템/설정 (무공, 기술, 마법, 아이템, 유물, 특수 용어, 랭크 등)\n\n"
        "## {lang_code} 용어 추출 및 번역/음역 절대 원칙:\n"
        "{rules}\n\n"
        "## 필수 준수 지침:\n"
        "- 요약하지 말고, 본 블록에 등장하는 모든 등장인물(주인공, 조연, 엑스트라, 별명, 풀네임), 문파, 지명, 무공, 고유명사를 빠짐없이 전부 추출하십시오 (블록당 가능한 한 많이, 최소 20~40개 이상).\n"
        "- 본문에 실제로 등장한 횟수(occurrence_count)를 최소 1 이상으로 기재하십시오.\n"
        "- 반드시 아래 JSON 배열 형식으로만 응답하고, 마크다운 코드블록이나 부가 설명/사고 과정을 일체 포함하지 마십시오.\n\n"
        "## 소설 본문 블록:\n"
        "```\n{text}\n```\n\n"
        "## JSON 출력 형식:\n"
        "[\n"
        '  {{"keyword": "원문단어", "translated_keyword": "한국어번역", "category": "인명/문파/지명/무공/고유명사", "occurrence_count": 1}}\n'
        "]"
    )

    LANG_RULES = {
        "ZH": (
            "1. [인명(등장인물) -> 표준 중국어 병음 음역(Pinyin Transliteration) 필수 원칙]:\n"
            "   - 중국 소설 인명 및 등장인물 고유명사는 절대로 한국식 한자 독음(Hanja-eum, 예: 钟九->종구 X, 张小华->장소화 X, 萧炎->소염 X, 林动->임동 X, 顾夜白->고야백 X, 楚风->초풍 X, 韩立->한립 X, 孟浩->맹호 X)으로 변환하지 마십시오.\n"
            "   - 반드시 표준 중국어 외래어 표기법 및 병음 발음(Pinyin Transliteration) 음역을 최우선 원칙으로 적용하여 추출하십시오.\n"
            "   * 표준 인명 음역 예시: 钟九 -> 종지우, 张小华 -> 장샤오화, 萧炎 -> 샤오옌, 林动 -> 린둥, 顾夜白 -> 구예바이, 楚风 -> 추펑, 叶修 -> 예슈, 唐三 -> 탕싼, 韩立 -> 한리, 孟浩 -> 멍하오, 白小纯 -> 바이샤오춘, 李火旺 -> 리훠왕\n"
            "   * 인명 호칭 분리: 인물 이름 뒤나 앞에 붙는 호칭(哥, 姐, 师兄, 师姐, 师弟, 师妹, 叔, 伯, 爷, 弟, 妹, 宗主, 掌门, 前辈, 先生, 小姐 등)은 분리하여 '순수 이름 본체'만 keyword 및 translated_keyword로 추출하십시오. (예: '钟九哥' -> keyword: '钟九', translated_keyword: '종지우', category: '인명')\n\n"
            "2. [문파/지명/무공/기술/아이템/설정 -> 한국식 한자 독음(음차) 준수 원칙]:\n"
            "   - 무협/선협/판타지의 문파·세력, 지명·장소, 무공·기술, 아이템·도구, 크툴루/SF 설정 등은 한국식 한자 독음(음차) 및 장르 관례에 맞는 한국어 용어를 준수하여 매핑하십시오.\n"
            "   * 올바른 문파 예시: 少林寺 -> 소림사, 华山派 -> 화산파, 武当派 -> 무당파, 峨眉派 -> 아미파, 魔教 -> 마교, 青云门 -> 청운문\n"
            "   * 올바른 지명 예시: 洛阳 -> 낙양, 长安 -> 장안, 金陵 -> 금릉, 泰山 -> 태산, 中原 -> 중원, 蜀山 -> 촉산\n"
            "   * 올바른 무공/기술 예시: 降龙十八掌 -> 항룡십팔장, 独孤九剑 -> 독고구검, 九阳神功 -> 구양신공, 辟邪剑法 -> 벽사검법, 金钟罩 -> 금종조, 凌波微步 -> 능파미보\n"
            "   * 올바른 설정/세력 예시: 天机局 -> 천기국, 黄昏社 -> 황혼사, 界域 -> 계역, 灭世 -> 멸세, 筑基 -> 축기, 金丹 -> 금단, 元婴 -> 원영\n\n"
            "3. [외래어/브랜드]:\n"
            "   - 외래어 브랜드 및 현대 국가명은 표준 외래어 표기법을 준수하십시오 (예: 巴西 -> 브라질, 宝马 -> BMW)."
        ),
        "JA": (
            "1. 일본어 라이트노벨 인명, 지명, 루비 표기, 호칭(군, 양, 씨 등)을 한국 공식 발매본 형식으로 자연스럽게 번역/음역하십시오.\n"
            "2. 한자 고유명사와 가타카나 외래어 표기법을 정확히 적용하십시오."
        ),
        "EN": (
            "1. 영어 인명, 지명, 판타지/SF 고유명사는 국립국어원 외래어 표기법에 맞춰 한글로 자연스럽게 음역하십시오."
        )
    }



    @classmethod
    def get_tmp_checkpoint_path(cls, file_path: Path) -> Path:
        """Returns the temporary checkpoint path for glossary extraction."""
        return file_path.parent / f"{file_path.name}.glossary.tmp.json"

    @classmethod
    def save_checkpoint(cls, checkpoint_path: Path, data: Dict[str, Any]) -> None:
        """Atomically saves intermediate glossary extraction progress."""
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = checkpoint_path.with_suffix(".tmp_write")
        try:
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            temp_path.replace(checkpoint_path)
            logger.debug(f"Atomic glossary checkpoint saved: {checkpoint_path} ({len(data.get('completed_blocks', []))} blocks done)")
        except Exception as e:
            logger.error(f"Failed to save atomic glossary checkpoint ({checkpoint_path}): {e}")

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

    @classmethod
    def _clean_extracted_term(cls, kw: str, tr: str, cat: str, lang_code: str) -> tuple[str, str, str]:
        """Cleans and standardizes extracted terms (NFKC normalization, Chinese honorific stripping)."""
        kw = unicodedata.normalize('NFKC', kw).strip()
        tr = unicodedata.normalize('NFKC', tr).strip()
        cat = cat.strip() if cat else "고유명사"

        if lang_code.upper() == "ZH" and cat in ("인명", "등장인물", "인물", "고유명사"):
            honorific_suffixes = (
                '师兄', '师姐', '师弟', '师妹', '宗主', '掌门', '前辈', '先生', '小姐',
                '大哥', '小哥', '大姐', '小妹', '老弟', '老哥', '老祖', '道友', '道长',
                '师尊', '阁下', '大人', '陛下', '殿下', '哥', '姐', '叔', '伯', '爷', '弟', '妹'
            )
            for suffix in honorific_suffixes:
                if kw.endswith(suffix) and len(kw) - len(suffix) >= 2:
                    kw = kw[:-len(suffix)].strip()
                    break

            # If the keyword itself is a standalone generic honorific, change category to '호칭' and standardize translation
            generic_honorific_map = {
                '先生': '선생님',
                '女士': '여사',
                '小姐': '아가씨',
                '师傅': '사부',
                '师父': '사부님',
                '同志': '동지',
                '阁下': '귀하',
                '前辈': '선배님',
                '道友': '도우',
                '老夫': '노부',
                '本座': '본좌',
                '弟子': '제자'
            }
            if kw in generic_honorific_map:
                cat = "호칭"
                tr = generic_honorific_map[kw]

        return kw, tr, cat

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
        blocks = cls.split_into_blocks(text_content, block_size=block_size)
        total_blocks = len(blocks)
        if total_blocks == 0:
            logger.warning("Empty text provided for glossary extraction.")
            return []

        rules = cls.LANG_RULES.get(lang_code.upper(), cls.LANG_RULES["JA"])
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

            prompt_str = cls.PROMPT_TEMPLATE.format(
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

                # Reduce / Merge into merged_glossary
                for item in extracted_items:
                    raw_kw = str(item.get("keyword", "")).strip()
                    raw_tr = str(item.get("translated_keyword", "")).strip()
                    raw_cat = str(item.get("category", "고유명사")).strip() or "고유명사"
                    kw, tr, cat = cls._clean_extracted_term(raw_kw, raw_tr, raw_cat, lang_code)
                    raw_cnt = item.get("occurrence_count", 1)
                    cnt = int(raw_cnt) if str(raw_cnt).isdigit() and int(raw_cnt) > 0 else 1

                    if not kw or not tr or len(kw) < 1:
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

        # Sort by occurrence_count descending
        final_entries = sorted(
            merged_glossary.values(),
            key=lambda x: x.get("occurrence_count", 1),
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
        """Saves final verified glossary JSON file."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(entries)} glossary entries to {filepath}")

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
