"""
OmniTranslator Pro - Plain Text File I/O
"""

from pathlib import Path

class TxtIO:
    """Reads and writes plain text files with UTF-8 encoding."""

    @classmethod
    def read_text_file(cls, path: Path) -> str:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

    @classmethod
    def write_text_file(cls, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
