"""
Rate Limiter Module
Supports Redis-based rate limiting with multiple time windows
"""

import time
from typing import Tuple, Optional
import redis.asyncio as redis

from .config import REDIS_URL


class RateLimiter:
    """Redis-based rate limiter"""
    
    def __init__(self):
        self.redis: Optional[redis.Redis] = None
        
    async def connect(self):
        """Connect to Redis"""
        self.redis = await redis.from_url(REDIS_URL)
    
    async def check_limit(self, user_id: str, tier: str) -> Tuple[bool, int, int]:
        """
        Check if user is within rate limit
        
        Returns:
            (allowed, limit, remaining)
        """
        if not self.redis:
            return True, 0, 0
        
        # Get tier limits
        limits = self._get_limits(tier)
        
        # Check multiple windows
        now = int(time.time())
        
        # Per minute
        minute_key = f"rate_limit:{user_id}:minute"
        minute_window = 60
        
        # Use Redis sorted set for sliding window
        pipe = self.redis.pipeline()
        
        # Remove old entries
        pipe.zremrangebyscore(minute_key, 0, now - minute_window)
        
        # Count current entries
        pipe.zcard(minute_key)
        
        # Add current request
        pipe.zadd(minute_key, {str(now): now})
        
        # Set expiry
        pipe.expire(minute_key, minute_window)
        
        results = await pipe.execute()
        current_count = results[1]
        
        limit = limits["requests_per_minute"]
        remaining = max(0, limit - current_count)
        
        allowed = current_count <= limit
        
        return allowed, limit, remaining
    
    def _get_limits(self, tier: str) -> dict:
        """Get rate limits for tier"""
        limits = {
            "free": {
                "requests_per_minute": 10,
                "requests_per_hour": 100,
                "requests_per_day": 500
            },
            "basic": {
                "requests_per_minute": 30,
                "requests_per_hour": 500,
                "requests_per_day": 2000
            },
            "pro": {
                "requests_per_minute": 100,
                "requests_per_hour": 2000,
                "requests_per_day": 10000
            },
            "enterprise": {
                "requests_per_minute": 500,
                "requests_per_hour": 10000,
                "requests_per_day": 100000
            }
        }
        return limits.get(tier, limits["free"])
    
    async def get_usage_stats(self, user_id: str) -> dict:
        """Get usage statistics for user"""
        if not self.redis:
            return {}
        
        now = int(time.time())
        
        # Get counts for different windows
        minute_key = f"rate_limit:{user_id}:minute"
        hour_key = f"rate_limit:{user_id}:hour"
        day_key = f"rate_limit:{user_id}:day"
        
        pipe = self.redis.pipeline()
        pipe.zcount(minute_key, now - 60, now)
        pipe.zcount(hour_key, now - 3600, now)
        pipe.zcount(day_key, now - 86400, now)
        
        results = await pipe.execute()
        
        return {
            "requests_last_minute": results[0],
            "requests_last_hour": results[1],
            "requests_last_day": results[2]
        }
