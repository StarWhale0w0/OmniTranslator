"""
OmniTranslator Pro - Multi-API Key Rotation & Cooldown Manager
"""

import time
import asyncio
from typing import List, Optional, Dict
from common.logger import setup_logger

logger = setup_logger("KeyManager")

class KeyManager:
    """Manages pool of Gemini API keys, key rotation, request delay, and rate-limiting."""

    COOLDOWN_SECONDS = 100.0  # 100s penalty on RateLimit / QuotaExceeded error

    def __init__(self, api_keys: Optional[List[str]] = None, requests_per_minute: float = 60.0, request_delay: float = 0.5):
        self.api_keys: List[str] = [k.strip() for k in api_keys if k.strip()] if api_keys else []
        self.current_index: int = 0
        self.key_cooldowns: Dict[str, float] = {}  # key -> timestamp when available again
        
        self.rpm = requests_per_minute
        self.request_delay = max(0.0, request_delay)
        self.last_request_time = 0.0
        self._rpm_lock = asyncio.Lock()

    def set_api_keys(self, keys: List[str]) -> None:
        self.api_keys = [k.strip() for k in keys if k.strip()]
        self.current_index = 0
        self.key_cooldowns.clear()
        logger.info(f"API Key pool updated. Total keys: {len(self.api_keys)}")

    def set_request_delay(self, delay: float) -> None:
        self.request_delay = max(0.0, delay)
        logger.info(f"Request delay updated to: {self.request_delay:.2f}s")

    def get_key_count(self) -> int:
        return len(self.api_keys)

    def all_keys_exhausted(self) -> bool:
        """Returns True if there are keys configured and all of them are currently in cooldown."""
        if not self.api_keys:
            return True
        now = time.time()
        return all(now < self.key_cooldowns.get(k, 0.0) for k in self.api_keys)

    def get_available_key_count(self) -> int:
        now = time.time()
        return sum(1 for k in self.api_keys if now >= self.key_cooldowns.get(k, 0.0))

    def reset_cooldowns(self) -> None:
        self.key_cooldowns.clear()
        logger.info("All key cooldowns reset.")

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

            self.current_index = (self.current_index + 1) % len(self.api_keys)

        # If all keys are in cooldown, pick the one with earliest cooldown expiry
        earliest_key = min(self.api_keys, key=lambda k: self.key_cooldowns.get(k, 0.0))
        wait_time = max(0.0, self.key_cooldowns.get(earliest_key, 0.0) - now)
        logger.warning(
            f"All {len(self.api_keys)} API keys in cooldown. "
            f"Earliest key (...{earliest_key[-6:]}) available in {wait_time:.1f}s."
        )
        return earliest_key

    def rotate_key(
        self,
        current_key: Optional[str] = None,
        is_rate_limit: bool = True,
        cooldown_seconds: Optional[float] = None
    ) -> str:
        """
        Puts current_key into cooldown and advances to the next available key in the pool.
        """
        if not self.api_keys:
            raise RuntimeError("No API keys provided in KeyManager.")

        cd_duration = cooldown_seconds if cooldown_seconds is not None else (self.COOLDOWN_SECONDS if is_rate_limit else 15.0)

        target_key = current_key or (self.api_keys[self.current_index] if self.api_keys else None)
        if target_key:
            self.key_cooldowns[target_key] = time.time() + cd_duration
            logger.warning(
                f"Key (...{target_key[-6:]}) put into cooldown for {cd_duration:.1f}s "
                f"({'RateLimit/Quota' if is_rate_limit else 'Failover'})."
            )

        # Advance to next key index
        self.current_index = (self.current_index + 1) % len(self.api_keys)
        next_key = self.get_active_key()
        logger.info(
            f"Rotated to API Key (...{next_key[-6:]}). "
            f"Available active keys: {self.get_available_key_count()}/{len(self.api_keys)}"
        )
        return next_key

    def mark_key_failed(self, key: str, is_rate_limit: bool = True, cooldown_seconds: Optional[float] = None) -> str:
        """Puts a failing key into cooldown and rotates to the next available key."""
        return self.rotate_key(current_key=key, is_rate_limit=is_rate_limit, cooldown_seconds=cooldown_seconds)

    async def acquire_rpm_slot(self) -> None:
        """Enforces request delay and rate limits."""
        async with self._rpm_lock:
            now = time.time()
            elapsed = now - self.last_request_time
            target_delay = max(self.request_delay, (60.0 / self.rpm) if self.rpm > 0 else 0.0)
            if elapsed < target_delay:
                wait_duration = target_delay - elapsed
                await asyncio.sleep(wait_duration)
            self.last_request_time = time.time()
