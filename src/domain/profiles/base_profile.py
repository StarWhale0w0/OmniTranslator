"""Base Language Profile Interface."""

class BaseLanguageProfile:
    def __init__(self, lang_code: str):
        self.lang_code = lang_code
