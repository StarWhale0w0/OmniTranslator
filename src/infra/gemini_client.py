"""
OmniTranslator Pro - Gemini API Client with Async Support & Model Refresh
"""

import asyncio
from typing import Dict, Any, Optional, List
from google import genai
from google.genai import types as genai_types
from infra.key_manager import KeyManager
from common.logger import setup_logger

logger = setup_logger("GeminiClient")

class GeminiClient:
    """High-level async Gemini client wrapping SDK calls, key rotation, and model discovery."""

    DEFAULT_FALLBACK_MODELS = [
        "gemini-2.5-flash",
        "gemini-3-pro-preview",
        "gemini-2.0-flash",
        "gemini-2.0-pro"
    ]

    def __init__(self, key_manager: KeyManager):
        self.key_manager = key_manager
        self.client_pool: Dict[str, genai.Client] = {}

    def _get_sdk_client(self, api_key: str) -> genai.Client:
        if api_key not in self.client_pool:
            self.client_pool[api_key] = genai.Client(api_key=api_key)
        return self.client_pool[api_key]

    @classmethod
    def list_available_models(cls, api_key: str) -> List[str]:
        """Queries Gemini API for available text generation models."""
        if not api_key:
            return cls.DEFAULT_FALLBACK_MODELS
        try:
            client = genai.Client(api_key=api_key)
            models = []
            for m in client.models.list():
                name = m.name.replace("models/", "") if hasattr(m, "name") else str(m)
                if "gemini" in name.lower() and "vision" not in name.lower():
                    models.append(name)
            logger.info(f"Successfully fetched {len(models)} models from Gemini API.")
            return models if models else cls.DEFAULT_FALLBACK_MODELS
        except Exception as e:
            logger.warning(f"Failed to query model list from API ({e}). Using fallback list.")
            return cls.DEFAULT_FALLBACK_MODELS

    async def generate_text_async(
        self,
        prompt_contents: List[genai_types.Content],
        model_name: str = "gemini-2.5-flash",
        temperature: float = 0.7,
        top_p: float = 0.9,
        thinking_level: str = "high",
        system_instruction: Optional[str] = None
    ) -> str:
        """Performs async text generation with key rotation retries."""
        max_retries = max(len(self.key_manager.api_keys), 3)

        for attempt in range(max_retries):
            api_key = self.key_manager.get_active_key()
            await self.key_manager.acquire_rpm_slot()

            try:
                sdk_client = self._get_sdk_client(api_key)
                config = genai_types.GenerateContentConfig(
                    temperature=temperature,
                    top_p=top_p,
                    system_instruction=system_instruction
                )

                loop = asyncio.get_running_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: sdk_client.models.generate_content(
                        model=model_name,
                        contents=prompt_contents,
                        config=config
                    )
                )

                if response and response.text:
                    return response.text.strip()
                raise ValueError("Empty response received from Gemini API.")

            except Exception as e:
                err_msg = str(e)
                logger.error(f"Gemini API call failed (Attempt {attempt+1}/{max_retries}) using key (...{api_key[-6:]}): {err_msg}")
                
                if "429" in err_msg or "QUOTA" in err_msg or "RESOURCE_EXHAUSTED" in err_msg:
                    self.key_manager.mark_key_failed(api_key, is_rate_limit=True)
                else:
                    await asyncio.sleep(2.0 * (attempt + 1))

        raise RuntimeError("Failed to generate content after exhausting all retries and API keys.")
