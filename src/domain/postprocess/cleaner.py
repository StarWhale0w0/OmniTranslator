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
    def clean_thinking_and_meta(cls, text: str) -> str:
        """
        Strips explicit reasoning tags (<think>...</think>) as well as untagged LLM meta thinking / monologue preambles
        (e.g., 'Ah, I see!...', 'Final Polish of Korean Text:', 'Ready to output.', 'The prompt got cut off...').
        """
        if not text:
            return ""

        # 1. Remove explicit XML/HTML thinking tags
        cleaned = re.sub(
            r'<(?:think|thought|thinking|reflection)>[\s\S]*?</(?:think|thought|thinking|reflection)>',
            '',
            text,
            flags=re.IGNORECASE
        )

        # 2. Remove multi-line untagged English thinking monologue at the beginning
        cleaned = re.sub(
            r'^(?:'
            r'Ah[!,.]?\s*(?:I\s*see!?|The\s*prompt|let\s*me)?|'
            r'Oh[!,.]?\s*(?:I\s*understand|I\s*see)?|'
            r'Okay,\s*(?:let\'?s|I\s*will|here)|'
            r'Let\'?s\s*(?:look|analyze|translate|carefully|review|break|check|do)|'
            r'Wait,\s*(?:let\s*me|I\s*need)|'
            r'Here(?:\'s|\s+is)\s+(?:the\s+)?(?:Korean\s+)?(?:translation|translated\s+text):?|'
            r'Below\s+is\s+(?:the\s+)?(?:Korean\s+)?translation:?|'
            r'Final\s*Polish(?:\s*of\s*Korean\s*(?:Text)?)?(?:\s*\(.*?\))?:?|'
            r'Ready\s*to\s*output\.?:?|'
            r'Sure!?,?\s*(?:here\s+is\s+the\s+translation)?|'
            r'Certainly!?,?\s*(?:here\s+is\s+the\s+translation)?|'
            r'The\s+prompt\s+got\s+cut\s+off[\s\S]*?(?:text\s+is|section):?|'
            r'Thought\s*Process:?|Thinking\s*Process:?|Chain\s*of\s*Thought:?|'
            r'Draft\s*(?:Translation)?:?|Step\s*\d+:?'
            r')[\s\S]*?(?=(?:<div|<p|<span|\[TAG_|\n\n\s*[가-힣<]|\Z))',
            '',
            cleaned,
            flags=re.IGNORECASE
        )

        # 3. Remove single/multi-line meta headers & monologue lines anywhere
        meta_line_patterns = [
            r'^\s*Ah[!,.]?\s*(?:I\s*see!?|The\s*prompt\s*got\s*cut\s*off|let\s*me\s*check).*$',
            r'^\s*Wait,\s*(?:let\s*me\s*check|let\s*me\s*look|I\s*need).*$',
            r'^\s*Final\s*Polish(?:\s*of\s*Korean\s*Text)?.*$',
            r'^\s*Ready\s*to\s*output\.?.*$',
            r'^\s*Here(?:\'s|\s+is)\s+(?:the\s+)?(?:Korean\s+)?(?:translation|translated\s+text):?.*$',
            r'^\s*(?:Korean\s+)?Translation\s*(?:Result|Output)?:?.*$',
            r'^\s*Translated\s+Text:?.*$',
            r'^\s*Output:?.*$',
            r'^\s*Notes?(?:\s*on\s*translation)?:?.*$',
            r'^\s*Let\'?s\s*(?:check|review|verify|do\s*a\s*final\s*check).*$',
            r'^\s*Everything\s*looks\s*good\.?.*$',
            r'^\s*The\s+prompt\s+got\s+cut\s+off.*$',
            r'^\s*(?:Thinking|Thought)\s*Process:?.*$',
            r'^\s*Chain\s*of\s*Thought:?.*$'
        ]
        for pat in meta_line_patterns:
            cleaned = re.sub(pat, '', cleaned, flags=re.MULTILINE | re.IGNORECASE)

        # 4. Remove trailing assistant conversational sign-offs
        cleaned = re.sub(
            r'\n+\s*(?:'
            r'Note:.*|'
            r'Hope\s+this\s+helps!?.*|'
            r'Let\s+me\s+know\s+if\s+you\s+need.*|'
            r'This\s+concludes\s+the\s+translation.*'
            r')\s*$',
            '',
            cleaned,
            flags=re.IGNORECASE
        )

        return cleaned

    @classmethod
    def clean_text(cls, text: str, extra_patterns: List[str] = None) -> str:
        if not text:
            return ""

        cleaned = cls.clean_html_response(text)

        # 1. Clean explicit and untagged thinking / reasoning monologues
        cleaned = cls.clean_thinking_and_meta(cleaned)

        # 2. Remove '*+ *Final check on.*?(\n|$)' and similar asterisk/bracket header lines
        cleaned = re.sub(r'\*+\s*Final check.*?(?:\n|$)', '\n', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\[Final check.*?(?:\]|\n|$)', '\n', cleaned, flags=re.IGNORECASE)

        # 3. Remove Markdown checklist logs (- [x] ..., * [ ] ...)
        cleaned = re.sub(r'^\s*[-*+]\s*\[[ xX]\]\s*.*$(?:\n)?', '', cleaned, flags=re.MULTILINE)

        # 4. Remove verification traces like -> `...` (Correct|Fixed)
        cleaned = re.sub(r'^[^\n<]*->\s*`?[^`\n]+`?\s*\((?:Correct|Fixed|Pass|OK)\)[^\n]*$(?:\n)?', '', cleaned, flags=re.MULTILINE | re.IGNORECASE)
        cleaned = re.sub(r'->\s*`?[^`\n]+`?\s*\((?:Correct|Fixed|Pass|OK)\)', '', cleaned, flags=re.IGNORECASE)

        # 5. Remove bracket/asterisk verification phrases and system pollution markers
        cleaned = re.sub(r'^\s*\[(?:Final check|검토|자가검증|자체\s*검토|체크리스트|Checklist|Review|Self-Correction).*?\]\s*$(?:\n)?', '', cleaned, flags=re.MULTILINE | re.IGNORECASE)
        cleaned = re.sub(r'^\s*\*+\s*(?:Final check|검토|체크리스트|Checklist|Self-Correction|Self-check|Verification).*?\*+\s*$(?:\n)?', '', cleaned, flags=re.MULTILINE | re.IGNORECASE)
        
        # 5.5. Remove system pollution tags ([구글 폴백], [2차 폴백], [Gemini 차단], [GoogleTranslator 폴백], etc.)
        cleaned = re.sub(r'\[\s*(?:구글\s*폴백|2차\s*폴백|Gemini\s*차단|GoogleTranslator\s*폴백|본문\s*누락\s*방지|최후\s*폴백)\s*\]', '', cleaned, flags=re.IGNORECASE)

        # 5.6. Correct common phonetic transliteration artifacts for Chinese web novels (e.g. 小声/出声 mistranslated as '샤오리')
        cleaned = re.sub(r'끙\s*하는\s*샤오리를?\s*(?:냈고|내며|내더니)', '낮은 신음을 흘렸고', cleaned)
        cleaned = re.sub(r'감히\s*샤오리를?\s*내지\s*못', '감히 숨소리조차 내지 못', cleaned)
        cleaned = re.sub(r'샤오리거거', '샤오리 오빠', cleaned)

        # 6. Remove language-specific regex patterns (ads, headers)
        if extra_patterns:
            for pattern in extra_patterns:
                cleaned = re.sub(pattern, '', cleaned, flags=re.MULTILINE | re.IGNORECASE)

        # 7. Clean consecutive empty newlines
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

        return cleaned.strip()
