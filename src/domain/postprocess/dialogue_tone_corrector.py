"""
OmniTranslator Pro - Dialogue Tone & Ending Corrector
Refines dialogue endings inside quotes (“ ”, " ", 「 」, 『 』) to enforce natural
Korean web novel conversational flow, eliminating rigid machine-translated honorifics
(~않습니까?, ~그렇습니다) and awkward pseudo-archaic endings (~하오, ~소이다).
"""

import re
from typing import Optional


class DialogueToneCorrector:
    """Post-processing engine to normalize and refine dialogue endings within quoted speech."""

    # Matches quoted dialogue: “...”, "...", 「...」, 『...』
    QUOTE_REGEX = re.compile(r'([“"「『])([^“”"「」『』\n]+)([”"」』])')

    @classmethod
    def refine_dialogue_text(cls, text: str) -> str:
        """Processes and normalizes dialogue endings within quotes while preserving narrative text."""
        if not text:
            return ""

        def _replace_dialogue(m):
            open_q = m.group(1)
            content = m.group(2)
            close_q = m.group(3)

            refined = cls._correct_dialogue_content(content)
            return f"{open_q}{refined}{close_q}"

        return cls.QUOTE_REGEX.sub(_replace_dialogue, text)

    @classmethod
    def _correct_dialogue_content(cls, d: str) -> str:
        res = d

        # 1. Stiff interrogative endings (극존칭 의문형 -> 자연스러운 반말/구어체/해요체)
        res = re.sub(r'하지\s*않습니까\?', '하지 않아?', res)
        res = re.sub(r'그러하지\s*않습니까\?', '그렇지 않아?', res)
        res = re.sub(r'그렇지\s*않습니까\?', '그렇지 않아?', res)
        res = re.sub(r'않지\s*않습니까\?', '않지 않아?', res)
        res = re.sub(r'([가-힣]+)지\s*않습니까\?', r'\1잖아?', res)
        res = re.sub(r'않습니까\?', '않아?', res)
        res = re.sub(r'거\s*아닙니까\?', '거 아니야?', res)
        res = re.sub(r'것\s*아닙니까\?', '거 아니야?', res)
        res = re.sub(r'아닙니까\?', '아니야?', res)
        res = re.sub(r'그렇습니까\?', '그래?', res)
        res = re.sub(r'그런\s*것입니까\?', '그런 거야?', res)
        res = re.sub(r'것입니까\?', '거야?', res)
        res = re.sub(r'있습니까\?', '있어?', res)
        res = re.sub(r'없습니까\?', '없어?', res)
        res = re.sub(r'되겠습니까\?', '되겠어?', res)
        res = re.sub(r'하겠습니까\?', '하겠어?', res)
        res = re.sub(r'가겠습니까\?', '가겠어?', res)
        res = re.sub(r'오겠습니까\?', '오겠어?', res)
        res = re.sub(r'보겠습니까\?', '보겠어?', res)
        res = re.sub(r'주겠습니까\?', '주겠어?', res)
        res = re.sub(r'않겠습니까\?', '않겠어?', res)
        res = re.sub(r'모르겠습니까\?', '모르겠어?', res)
        res = re.sub(r'말입니까\?', '말이야?', res)
        res = re.sub(r'누구입니까\?', '누구야?', res)
        res = re.sub(r'어디입니까\?', '어디야?', res)
        res = re.sub(r'(?:무엇|뭐)입니까\?', '뭐야?', res)
        res = re.sub(r'언제입니까\?', '언제야?', res)
        res = re.sub(r'왜입니까\?', '왜야?', res)
        res = re.sub(r'어떻습니까\?', '어때?', res)
        res = re.sub(r'어찌\s*합니까\?', '어떡해?', res)
        res = re.sub(r'(?:어찌|어떻게)\s*되었습니까\?', '어떻게 됐어?', res)
        res = re.sub(r'어떻게\s*합니까\?', '어떡해?', res)
        res = re.sub(r'(?:보았|봤)습니까\?', '봤어?', res)
        res = re.sub(r'알았습니까\?', '알았어?', res)
        res = re.sub(r'들었습니까\?', '들었어?', res)
        res = re.sub(r'갔습니까\?', '갔어?', res)
        res = re.sub(r'왔습니까\?', '왔어?', res)
        res = re.sub(r'죽었습니까\?', '죽었어?', res)
        res = re.sub(r'살았습니까\?', '살았어?', res)
        res = re.sub(r'했습니까\?', '했어?', res)
        res = re.sub(r'합니까\?', '해?', res)
        res = re.sub(r'됩니까\?', '돼?', res)
        res = re.sub(r'갑니까\?', '가?', res)
        res = re.sub(r'옵니까\?', '와?', res)
        res = re.sub(r'봅니까\?', '봐?', res)

        # 2. Pseudo-archaic endings (뜬금없는 하오체/사극체 -> 자연스러운 구어체)
        res = re.sub(r'그러하지\s*않소\?', '그렇지 않아?', res)
        res = re.sub(r'하지\s*않소\?', '하지 않아?', res)
        res = re.sub(r'않소\?', '않아?', res)
        res = re.sub(r'아니오\?', '아니야?', res)
        res = re.sub(r'있소\?', '있어?', res)
        res = re.sub(r'없소\?', '없어?', res)
        res = re.sub(r'알겠소\?', '알겠어?', res)
        res = re.sub(r'알겠소([.,!?~\s]|$)', r'알겠어\1', res)
        res = re.sub(r'모르겠소([.,!?~\s]|$)', r'모르겠어\1', res)
        res = re.sub(r'좋소([.,!?~\s]|$)', r'좋아\1', res)
        res = re.sub(r'맞소([.,!?~\s]|$)', r'맞아\1', res)
        res = re.sub(r'그렇소([.,!?~\s]|$)', r'그래\1', res)

        # Verb imperative/request in -시오 -> -아/어 or -세요
        res = re.sub(r'내리시오([.,!?~\s]|$)', r'내려\1', res)
        res = re.sub(r'보시오([.,!?~\s]|$)', r'봐\1', res)
        res = re.sub(r'가시오([.,!?~\s]|$)', r'가\1', res)
        res = re.sub(r'오시오([.,!?~\s]|$)', r'와\1', res)
        res = re.sub(r'주시오([.,!?~\s]|$)', r'줘\1', res)
        res = re.sub(r'하시오([.,!?~\s]|$)', r'해\1', res)
        res = re.sub(r'마시오([.,!?~\s]|$)', r'마\1', res)
        res = re.sub(r'멈추시오([.,!?~\s]|$)', r'멈춰\1', res)
        res = re.sub(r'나오시오([.,!?~\s]|$)', r'나와\1', res)
        res = re.sub(r'들어가시오([.,!?~\s]|$)', r'들어가\1', res)
        res = re.sub(r'조심하시오([.,!?~\s]|$)', r'조심해\1', res)
        res = re.sub(r'앉으시오([.,!?~\s]|$)', r'앉아\1', res)
        res = re.sub(r'기다리시오([.,!?~\s]|$)', r'기다려\1', res)

        # Future/intent -겠소 -> -겠어
        res = re.sub(r'([가-힣]+)겠소([.,!?~\s]|$)', r'\1겠어\2', res)

        # Past -하였소 -> -했어, -았소/-었소 -> -았어/-었어
        res = re.sub(r'하였소([.,!?~\s]|$)', r'했어\1', res)
        res = re.sub(r'([가-힣]+)(았|었|였)소([.,!?~\s]|$)', r'\1\2어\3', res)

        # Noun predicate -이오 -> -이야, -하오 -> -해, -소이다 -> -야
        res = re.sub(r'다행이오([.,!?~\s]|$)', r'다행이야\1', res)
        res = re.sub(r'뿐이오([.,!?~\s]|$)', r'뿐이야\1', res)
        res = re.sub(r'것이오([.,!?~\s]|$)', r'거야\1', res)
        res = re.sub(r'말이오([.,!?~\s]|$)', r'말이야\1', res)
        res = re.sub(r'사람이오([.,!?~\s]|$)', r'사람이야\1', res)
        res = re.sub(r'([가-힣]+)하오([.,!?~\s]|$)', r'\1해\2', res)
        res = re.sub(r'([가-힣]+)소이다([.,!?~\s]|$)', r'\1야\2', res)

        # 3. Rigid declaratives inside dialogue
        res = re.sub(r'좋지\s*않습니다([.,!?~\s]|$)', r'좋지 않아\1', res)
        res = re.sub(r'그렇지\s*않습니다([.,!?~\s]|$)', r'그렇지 않아\1', res)
        res = re.sub(r'^그렇습니다([.,!?~\s]|$)', r'그래\1', res)
        res = re.sub(r'([.?!~]\s*)그렇습니다([.,!?~\s]|$)', r'\1그래\2', res)
        res = re.sub(r'……모르겠습니다([.,!?~\s]|$)', r'……모르겠어\1', res)
        res = re.sub(r'\b모르겠습니다([.,!?~\s]|$)', r'모르겠어\1', res)

        return res
