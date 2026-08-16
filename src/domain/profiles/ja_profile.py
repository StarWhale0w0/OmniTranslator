"""Japanese Light Novel Translation Profile."""
from domain.profiles.base_profile import BaseLanguageProfile

class JapaneseProfile(BaseLanguageProfile):
    def __init__(self):
        super().__init__("JA")
