"""
OmniTranslator Pro - Postprocessing Text Cleaner
Removes thinking tags, site ad spam, and cleans format artifacts.
"""

import re
import html
from typing import List

class TextCleaner:
    """Cleans LLM response text using regex patterns and HTML filter rules."""

    @classmethod
    def strip_html_tags(cls, text: str) -> str:
        """
        Strips residual HTML/XML tags, converts block tags to newlines,
        and unescapes HTML entities for pure text (TXT) output.
        """
        if not text:
            return ""

        # 1. Remove known virtual wrapper tags explicitly
        cleaned = re.sub(r'</?(?:main|body|html|head)[^>]*>', '', text, flags=re.IGNORECASE)

        # 2. Replace paragraph / line break tags with newlines to preserve readable paragraph structure
        cleaned = re.sub(r'<br\s*/?>', '\n', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'</?(?:p|div|h[1-6]|li|blockquote|section|article)[^>]*>', '\n', cleaned, flags=re.IGNORECASE)

        # 3. Remove all remaining tags (inline tags like <span>, <b>, <i>, <a>, <ruby>, <rt>, etc.)
        cleaned = re.sub(r'<[^>]+>', '', cleaned)

        # 4. Decode HTML entities (&nbsp;, &lt;, &gt;, &amp;, &quot;, &#39;, etc.)
        cleaned = html.unescape(cleaned)

        # 5. Clean trailing/leading whitespace per line and normalize multiple blank lines
        lines = [line.strip() for line in cleaned.splitlines()]
        cleaned = "\n".join(lines)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

        return cleaned.strip()

    @classmethod
    def clean_html_response(cls, text: str) -> str:
        """Ported directly from seamarine: strips markdown codeblocks."""
        if not text:
            return ""
        cleaned = text.strip()
        if cleaned.startswith("```html"):
            cleaned = cleaned[7:].strip()
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:].strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
        return cleaned

    @classmethod
    def deduplicate_repetitions(cls, text: str, max_consecutive: int = 1) -> str:
        """Removes runaway consecutive duplicate lines/paragraphs caused by repetition hallucinations."""
        if not text:
            return ""
        lines = text.splitlines()
        deduped_lines = []
        repeat_count = 0
        prev_line = None

        for line in lines:
            trimmed = line.strip()
            if trimmed and trimmed == prev_line:
                repeat_count += 1
                if repeat_count < max_consecutive:
                    deduped_lines.append(line)
            else:
                repeat_count = 0
                prev_line = trimmed
                deduped_lines.append(line)

        return "\n".join(deduped_lines)

    @classmethod
    def clean_text(cls, text: str, extra_patterns: List[str] = None) -> str:
        if not text:
            return ""

        cleaned = cls.clean_html_response(text)

        # 1. Remove <think>...</think>, <thought>...</thought>, <thinking>...</thinking>, <reflection>...</reflection> blocks
        cleaned = re.sub(r'<(?:think|thought|thinking|reflection)>[\s\S]*?</(?:think|thought|thinking|reflection)>', '', cleaned, flags=re.IGNORECASE)

        # 2. Remove '*+ *Final check on.*?(\n|$)' and similar asterisk/bracket header lines
        cleaned = re.sub(r'\*+\s*Final check.*?(?:\n|$)', '\n', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\[Final check.*?(?:\]|\n|$)', '\n', cleaned, flags=re.IGNORECASE)

        # 3. Remove Markdown checklist logs (- [x] ..., * [ ] ...)
        cleaned = re.sub(r'^\s*[-*+]\s*\[[ xX]\]\s*.*$(?:\n)?', '', cleaned, flags=re.MULTILINE)

        # 4. Remove verification traces like -> `...` (Correct|Fixed)
        cleaned = re.sub(r'^[^\n<]*->\s*`?[^`\n]+`?\s*\((?:Correct|Fixed|Pass|OK)\)[^\n]*$(?:\n)?', '', cleaned, flags=re.MULTILINE | re.IGNORECASE)
        cleaned = re.sub(r'->\s*`?[^`\n]+`?\s*\((?:Correct|Fixed|Pass|OK)\)', '', cleaned, flags=re.IGNORECASE)

        # 5. Remove bracket/asterisk verification phrases (e.g., [검토 메모], *검토 완료*, *Self-Correction*)
        cleaned = re.sub(r'^\s*\[(?:Final check|검토|자가검증|자체\s*검토|체크리스트|Checklist|Review|Self-Correction).*?\]\s*$(?:\n)?', '', cleaned, flags=re.MULTILINE | re.IGNORECASE)
        cleaned = re.sub(r'^\s*\*+\s*(?:Final check|검토|체크리스트|Checklist|Self-Correction|Self-check|Verification).*?\*+\s*$(?:\n)?', '', cleaned, flags=re.MULTILINE | re.IGNORECASE)

        # 6. Remove language-specific regex patterns (ads, headers)
        if extra_patterns:
            for pattern in extra_patterns:
                cleaned = re.sub(pattern, '', cleaned, flags=re.MULTILINE | re.IGNORECASE)

        # 7. Clean consecutive empty newlines
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

        return cleaned.strip()
