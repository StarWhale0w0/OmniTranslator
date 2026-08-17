"""
OmniTranslator Pro - AI Glossary Extractor (Map-Reduce Full Document Scanner)
Extracts terms (characters, places, items, proper nouns) into JSON format with language rules.
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from google.genai import types as genai_types
from common.logger import setup_logger
from infra.txt_io import TxtIO
from infra.epub_io import EpubIO

logger = setup_logger("GlossaryExtractor")

class GlossaryExtractor:
    """Extracts terms from entire document text into unified JSON glossary using Gemini AI Map-Reduce pipeline."""

    PROMPT_TEMPLATE = (
        "당신은 {lang_code} 원작 소설/문학의 최고 전문 번역가이자 고유명사 용어집 구축 전문가입니다.\n"
        "제공된 본문 블록을 면밀히 분석하여 한국어 번역 시 일관성을 유지해야 하는 모든 고유명사를 빠짐없이 전부 추출하십시오.\n\n"
        "## 추출 대상 카테고리:\n"
        "1. 인명 (주인공, 조연, 엑스트라, 별명, 풀네임, 직함 결합 명칭 등)\n"
        "2. 지명/장소 (국가, 도시, 건물, 지형, 차원, 영역 등)\n"
        "3. 단체/조직/세력 (문파, 길드, 학원, 군단, 기업, 종족 등)\n"
        "4. 고유명사/설정 (무공, 기술, 마법, 아이템, 유물, 특수 용어, 랭크 등)\n\n"
        "## {lang_code} 번역 및 음역 원칙:\n"
        "{rules}\n\n"
        "## 필수 준수 지침:\n"
        "- 요약하지 말고, 본 블록에 등장하는 모든 등장인물(주인공, 조연, 엑스트라, 별명, 풀네임), 지명, 고유명사를 빠짐없이 전부 추출하십시오 (블록당 가능한 한 많이, 최소 20~40개 이상).\n"
        "- 본문에 실제로 등장한 횟수(occurrence_count)를 최소 1 이상으로 기재하십시오.\n"
        "- 반드시 아래 JSON 배열 형식으로만 응답하고, 마크다운 코드블록이나 부가 설명/사고 과정을 일체 포함하지 마십시오.\n\n"
        "## 소설 본문 블록:\n"
        "```\n{text}\n```\n\n"
        "## JSON 출력 형식:\n"
        "[\n"
        '  {{"keyword": "원문단어", "translated_keyword": "한국어번역", "category": "인명/지명/단체/고유명사", "occurrence_count": 1}}\n'
        "]"
    )

    LANG_RULES = {
        "ZH": "1. 일반 인명은 중국어 병음의 한글 표기(음역)를 따르고(예: 첸링, 구쥔), 지명/문파/세력/기술/크툴루·SF 설정은 한국식 한자 독음(음차)을 준수하십시오(예: 황혼사, 계역, 천기국).\n"
              "2. 외래어 브랜드/국가명은 표준 외래어 표기법을 준수하십시오(예: 巴西 -> 브라질, 宝马 -> BMW).",
        "JA": "1. 일본어 라이트노벨 인명, 지명, 루비 표기, 호칭(군, 양, 씨 등)을 한국 공식 발매본 형식으로 자연스럽게 번역/음역하십시오.\n"
              "2. 한자 고유명사와 가타카나 외래어 표기법을 정확히 적용하십시오.",
        "EN": "1. 영어 인명, 지명, 판타지/SF 고유명사는 국립국어원 외래어 표기법에 맞춰 한글로 자연스럽게 음역하십시오."
    }

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
    async def extract_glossary_from_file_async(
        cls,
        gemini_client: Any,
        file_path: Path,
        lang_code: str = "JA",
        model_name: str = "gemini-2.5-flash",
        block_size: int = 18000,
        progress_callback: Optional[Callable[[int, int, int], None]] = None
    ) -> List[Dict[str, Any]]:
        """Full-document Map-Reduce AI glossary extraction from file path."""
        text_content = cls.load_document_text(file_path)
        return await cls.extract_glossary_from_text_async(
            gemini_client=gemini_client,
            text_content=text_content,
            lang_code=lang_code,
            model_name=model_name,
            block_size=block_size,
            progress_callback=progress_callback
        )

    @classmethod
    async def extract_glossary_from_text_async(
        cls,
        gemini_client: Any,
        text_content: str,
        lang_code: str = "JA",
        model_name: str = "gemini-2.5-flash",
        block_size: int = 18000,
        progress_callback: Optional[Callable[[int, int, int], None]] = None
    ) -> List[Dict[str, Any]]:
        """Extracts terms from all text blocks using Map-Reduce and merges by occurrence count."""
        blocks = cls.split_into_blocks(text_content, block_size=block_size)
        total_blocks = len(blocks)
        if total_blocks == 0:
            logger.warning("Empty text provided for glossary extraction.")
            return []

        logger.info(f"Starting full-document glossary extraction: {len(text_content)} chars split into {total_blocks} blocks.")

        rules = cls.LANG_RULES.get(lang_code.upper(), cls.LANG_RULES["JA"])
        merged_glossary: Dict[str, Dict[str, Any]] = {}
        trans_counts: Dict[str, Dict[str, int]] = {}

        for idx, block in enumerate(blocks, start=1):
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

            try:
                logger.info(f"Extracting glossary block {idx}/{total_blocks} ({len(block)} chars)...")
                raw_response = await gemini_client.generate_text_async(
                    prompt_contents=prompt_contents,
                    model_name=model_name,
                    temperature=0.2,
                    top_p=0.8,
                    thinking_budget=0
                )

                extracted_items = cls._parse_terms_json(raw_response)
                logger.info(f"Block {idx}/{total_blocks}: Extracted {len(extracted_items)} raw terms.")

                # Reduce / Merge into merged_glossary
                for item in extracted_items:
                    kw = str(item.get("keyword", "")).strip()
                    tr = str(item.get("translated_keyword", "")).strip()
                    cat = str(item.get("category", "고유명사")).strip() or "고유명사"
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

                        # Elect the translation with the highest aggregate count
                        best_tr = max(trans_counts[kw].items(), key=lambda x: x[1])[0]
                        merged_glossary[kw]["translated_keyword"] = best_tr

                        # Preserve more specific categories if updated
                        if cat != "고유명사" and merged_glossary[kw]["category"] == "고유명사":
                            merged_glossary[kw]["category"] = cat

            except Exception as e:
                logger.error(f"Error extracting terms from block {idx}/{total_blocks}: {e}")

            if progress_callback:
                progress_callback(idx, total_blocks, len(merged_glossary))

        # Sort by occurrence_count descending
        final_entries = sorted(
            merged_glossary.values(),
            key=lambda x: x.get("occurrence_count", 1),
            reverse=True
        )

        logger.info(f"Full-document glossary extraction complete: {len(final_entries)} unique terms aggregated from {total_blocks} blocks.")
        return final_entries

    @classmethod
    async def extract_glossary_async(
        cls,
        gemini_client: Any,
        text_content: str,
        lang_code: str = "JA",
        model_name: str = "gemini-2.5-flash",
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
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(entries)} glossary entries to {filepath}")

    @classmethod
    def load_glossary_json(cls, filepath: Path) -> List[Dict[str, Any]]:
        if not filepath.exists():
            return []
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"Failed to load glossary JSON ({filepath}): {e}")
            return []
