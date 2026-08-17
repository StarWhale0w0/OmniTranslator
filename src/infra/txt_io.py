"""
OmniTranslator Pro - Plain Text File I/O
"""

from pathlib import Path

class TxtIO:
    """Reads and writes plain text files with automatic multi-encoding detection."""

    @classmethod
    def read_text_file(cls, path: Path) -> str:
        raw_bytes = path.read_bytes()
        encodings = ['utf-8', 'cp949', 'euc-kr', 'utf-16', 'latin-1']
        for enc in encodings:
            try:
                return raw_bytes.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return raw_bytes.decode('utf-8', errors='ignore')

    @classmethod
    def write_text_file(cls, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
