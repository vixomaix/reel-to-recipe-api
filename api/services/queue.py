"""Redis queue service for job management."""
import json
from typing import Dict, List, Optional

import redis.asyncio as redis


class RedisQueue:
    """Redis-based job queue using Redis Streams."""
    
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.client: Optional[redis.Redis] = None
    
    async def connect(self):
        """Connect to Redis."""
        self.client = redis.from_url(self.redis_url, decode_responses=True)
    
    async def close(self):
        """Close Redis connection."""
        if self.client:
            await self.client.close()
    
    def _job_key(self, job_id: str) -> str:
        return f"job:{job_id}"
    
    def _recipe_key(self, job_id: str) -> str:
        return f"recipe:{job_id}"
    
    async def set_job(self, job_id: str, job_data: Dict) -> None:
        """Store job data in Redis."""
        await self.client.set(self._job_key(job_id), json.dumps(job_data))
    
    async def get_job(self, job_id: str) -> Optional[Dict]:
        """Get job data from Redis."""
        data = await self.client.get(self._job_key(job_id))
        return json.loads(data) if data else None
    
    async def update_job(self, job_id: str, updates: Dict) -> None:
        """Update job data in Redis."""
        job = await self.get_job(job_id)
        if job:
            job.update(updates)
            await self.set_job(job_id, job)
    
    async def enqueue_video_processing(self, job_id: str, job_data: Dict) -> None:
        """Add job to video processing queue."""
        await self.client.xadd(
            "queue:video_processing",
            {"job_id": job_id, "data": json.dumps(job_data)},
        )
    
    async def enqueue_ai_processing(self, job_id: str, video_data: Dict) -> None:
        """Add job to AI processing queue."""
        await self.client.xadd(
            "queue:ai_processing",
            {"job_id": job_id, "video_data": json.dumps(video_data)},
        )
    
    async def store_recipe(self, job_id: str, recipe_data: Dict) -> None:
        """Store extracted recipe in Redis."""
        await self.client.set(self._recipe_key(job_id), json.dumps(recipe_data))
    
    async def get_recipe(self, job_id: str) -> Optional[Dict]:
        """Get recipe from Redis."""
        data = await self.client.get(self._recipe_key(job_id))
        return json.loads(data) if data else None
    
    async def list_jobs(
        self, 
        status: Optional[str] = None, 
        limit: int = 20, 
        offset: int = 0
    ) -> List[Dict]:
        """List jobs with optional filtering."""
        keys = await self.client.keys("job:*")
        jobs = []
        
        for key in keys:
            data = await self.client.get(key)
            if data:
                job = json.loads(data)
                if status is None or job.get("status") == status:
                    jobs.append(job)
        
        # Sort by created_at descending
        jobs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        return jobs[offset:offset + limit]
    
    async def count_jobs(self, status: Optional[str] = None) -> int:
        """Count jobs with optional filtering."""
        if status is None:
            return await self.client.dbsize()
        
        keys = await self.client.keys("job:*")
        count = 0
        for key in keys:
            data = await self.client.get(key)
            if data:
                job = json.loads(data)
                if job.get("status") == status:
                    count += 1
        return count
    
    async def list_recipes(
        self,
        search: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict]:
        """List recipes with optional filtering."""
        keys = await self.client.keys("recipe:*")
        recipes = []
        
        for key in keys:
            data = await self.client.get(key)
            if data:
                recipe = json.loads(data)
                
                # Apply filters
                if search:
                    search_lower = search.lower()
                    if search_lower not in recipe.get("title", "").lower():
                        continue
                
                if tag and tag not in recipe.get("tags", []):
                    continue
                
                recipes.append(recipe)
        
        return recipes[offset:offset + limit]