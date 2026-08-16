"""
OmniTranslator Pro - DTOs & Event Models
"""

from pydantic import BaseModel
from typing import Optional

class TranslationJobProgressDTO(BaseModel):
    total_chunks: int
    processed_chunks: int
    current_status: str
