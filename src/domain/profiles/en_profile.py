"""English Novel Translation Profile."""
from domain.profiles.base_profile import BaseLanguageProfile

class EnglishProfile(BaseLanguageProfile):
    def __init__(self):
        super().__init__("EN")
