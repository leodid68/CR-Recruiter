"""
Async Clash Royale API Client
High-performance API wrapper with rate limiting and connection pooling.
"""

import aiohttp
import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import time


BASE_URL = "https://api.clashroyale.com/v1"


@dataclass
class RateLimitState:
    """Track rate limiting state."""
    last_request: float = 0
    min_delay: float = 0.05  # 50ms minimum between requests
    backoff: float = 1.0


class ClashRoyaleAPI:
    """
    Async Clash Royale API client with:
    - Connection pooling
    - Automatic rate limiting
    - Retry on 429 errors
    """
    
    def __init__(self, api_key: str, max_concurrent: int = 10):
        self.api_key = api_key
        self.max_concurrent = max_concurrent
        self.rate_limit = RateLimitState()
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Stats
        self.requests_made = 0
        self.requests_failed = 0
        self.rate_limited_count = 0
    
    @property
    def headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json"
        }
    
    async def __aenter__(self):
        connector = aiohttp.TCPConnector(limit=self.max_concurrent, limit_per_host=self.max_concurrent)
        timeout = aiohttp.ClientTimeout(total=10)
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=self.headers
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()
    
    def _encode_tag(self, tag: str) -> str:
        """Encode player tag for URL."""
        return tag.replace("#", "%23")
    
    async def _request(self, endpoint: str, retries: int = 3) -> Optional[Dict[str, Any]]:
        """Make a rate-limited request with retries."""
        async with self.semaphore:
            # Respect rate limit
            now = time.time()
            elapsed = now - self.rate_limit.last_request
            if elapsed < self.rate_limit.min_delay * self.rate_limit.backoff:
                await asyncio.sleep(self.rate_limit.min_delay * self.rate_limit.backoff - elapsed)
            
            self.rate_limit.last_request = time.time()
            
            for attempt in range(retries):
                try:
                    self.requests_made += 1
                    async with self._session.get(f"{BASE_URL}{endpoint}") as resp:
                        if resp.status == 200:
                            self.rate_limit.backoff = max(1.0, self.rate_limit.backoff * 0.9)
                            return await resp.json()
                        elif resp.status == 429:
                            self.rate_limited_count += 1
                            self.rate_limit.backoff = min(10.0, self.rate_limit.backoff * 2)
                            await asyncio.sleep(self.rate_limit.backoff)
                        elif resp.status == 404:
                            return None
                        else:
                            self.requests_failed += 1
                            return None
                except asyncio.TimeoutError:
                    self.requests_failed += 1
                    await asyncio.sleep(0.5)
                except Exception:
                    self.requests_failed += 1
                    return None
            
            return None
    
    async def get_player(self, tag: str) -> Optional[Dict[str, Any]]:
        """Fetch player profile."""
        return await self._request(f"/players/{self._encode_tag(tag)}")
    
    async def get_battlelog(self, tag: str) -> List[Dict[str, Any]]:
        """Fetch player battle log."""
        result = await self._request(f"/players/{self._encode_tag(tag)}/battlelog")
        return result if result else []
    
    async def get_player_with_battles(self, tag: str) -> tuple[Optional[Dict], List[Dict]]:
        """Fetch both player and battlelog concurrently."""
        player, battles = await asyncio.gather(
            self.get_player(tag),
            self.get_battlelog(tag)
        )
        return player, battles
    
    def get_stats(self) -> Dict[str, Any]:
        """Return API usage statistics."""
        return {
            "requests_made": self.requests_made,
            "requests_failed": self.requests_failed,
            "rate_limited": self.rate_limited_count,
            "success_rate": (self.requests_made - self.requests_failed) / max(1, self.requests_made) * 100
        }
