"""Chinese Web Novel Translation Profile."""
from domain.profiles.base_profile import BaseLanguageProfile

class ChineseProfile(BaseLanguageProfile):
    def __init__(self):
        super().__init__("ZH")
