"""
Cache Module
Redis-based caching for API responses
"""

import json
import pickle
from typing import Optional, Any
import redis.asyncio as redis

from .config import REDIS_URL, CACHE_TTL


class Cache:
    """Redis cache handler"""
    
    def __init__(self):
        self.redis: Optional[redis.Redis] = None
    
    async def connect(self):
        """Connect to Redis"""
        self.redis = await redis.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=False
        )
    
    async def disconnect(self):
        """Disconnect from Redis"""
        if self.redis:
            await self.redis.close()
    
    async def is_connected(self) -> bool:
        """Check if Redis is connected"""
        if not self.redis:
            return False
        try:
            await self.redis.ping()
            return True
        except:
            return False
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if not self.redis:
            return None
        
        try:
            data = await self.redis.get(key)
            if data:
                return pickle.loads(data)
            return None
        except Exception as e:
            print(f"Cache get error: {e}")
            return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set value in cache"""
        if not self.redis:
            return
        
        try:
            data = pickle.dumps(value)
            await self.redis.setex(key, ttl or CACHE_TTL, data)
        except Exception as e:
            print(f"Cache set error: {e}")
    
    async def delete(self, key: str):
        """Delete value from cache"""
        if not self.redis:
            return
        
        try:
            await self.redis.delete(key)
        except Exception as e:
            print(f"Cache delete error: {e}")
    
    async def get_reel(self, reel_id: str) -> Optional[Any]:
        """Get cached reel result"""
        return await self.get(f"reel:{reel_id}")
    
    async def save_reel(self, reel_id: str, result: Any, ttl: Optional[int] = None):
        """Cache reel result"""
        await self.set(f"reel:{reel_id}", result, ttl)
    
    async def get_job_status(self, job_id: str) -> Optional[Any]:
        """Get cached job status"""
        return await self.get(f"job:{job_id}")
    
    async def set_job_status(self, job_id: str, status: Any, ttl: int = 3600):
        """Cache job status"""
        await self.set(f"job:{job_id}", status, ttl)
