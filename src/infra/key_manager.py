"""
OmniTranslator Pro - Multi-API Key Rotation & Cooldown Manager
"""

import time
import asyncio
from typing import List, Optional, Dict
from common.logger import setup_logger

logger = setup_logger("KeyManager")

class KeyManager:
    """Manages pool of Gemini API keys, key rotation, and rate-limiting."""

    COOLDOWN_SECONDS = 100.0  # 100s penalty on RateLimit / QuotaExceeded error

    def __init__(self, api_keys: Optional[List[str]] = None, requests_per_minute: float = 60.0):
        self.api_keys: List[str] = [k.strip() for k in api_keys if k.strip()] if api_keys else []
        self.current_index: int = 0
        self.key_cooldowns: Dict[str, float] = {}  # key -> timestamp when available again
        
        self.rpm = requests_per_minute
        self.delay_between_requests = 60.0 / self.rpm if self.rpm > 0 else 0.0
        self.last_request_time = 0.0
        self._rpm_lock = asyncio.Lock()

    def set_api_keys(self, keys: List[str]) -> None:
        self.api_keys = [k.strip() for k in keys if k.strip()]
        self.current_index = 0
        logger.info(f"API Key pool updated. Total keys: {len(self.api_keys)}")

    def get_active_key(self) -> str:
        """Returns the next available non-cooldown API key."""
        if not self.api_keys:
            raise RuntimeError("No API keys provided in KeyManager.")

        now = time.time()
        start_index = self.current_index

        for _ in range(len(self.api_keys)):
            key = self.api_keys[self.current_index]
            cooldown_until = self.key_cooldowns.get(key, 0.0)

            if now >= cooldown_until:
                return key

            # Advance index to inspect next key
            self.current_index = (self.current_index + 1) % len(self.api_keys)

        # All keys in cooldown
        wait_time = min(self.key_cooldowns.values()) - now
        logger.warning(f"All API keys exhausted/cooldown. Shortest wait: {max(wait_time, 1.0):.1f}s")
        return self.api_keys[start_index]

    def mark_key_failed(self, key: str, is_rate_limit: bool = True) -> str:
        """Puts a failing key into cooldown and rotates to the next available key."""
        if is_rate_limit:
            self.key_cooldowns[key] = time.time() + self.COOLDOWN_SECONDS
            logger.warning(f"Key (...{key[-6:]}) rate limited. Cooldown applied ({self.COOLDOWN_SECONDS}s).")

        if self.api_keys:
            self.current_index = (self.current_index + 1) % len(self.api_keys)
            next_key = self.get_active_key()
            logger.info(f"Rotated to API Key (...{next_key[-6:]}).")
            return next_key
        return key

    async def acquire_rpm_slot(self) -> None:
        """Enforces requests per minute (RPM) rate limits."""
        if self.delay_between_requests <= 0:
            return

        async with self._rpm_lock:
            now = time.time()
            elapsed = now - self.last_request_time
            if elapsed < self.delay_between_requests:
                wait_duration = self.delay_between_requests - elapsed
                await asyncio.sleep(wait_duration)
            self.last_request_time = time.time()
