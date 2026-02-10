"""AI Worker for recipe extraction from processed video data."""
import asyncio
import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

import redis.asyncio as redis
from ai_providers import AIProvider, OpenAIProvider, AnthropicProvider
from recipe_extractor import RecipeExtractor


class AIWorker:
    """Worker that processes video data and extracts recipes using AI."""
    
    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.redis: Optional[redis.Redis] = None
        self.group_name = "ai-workers"
        self.consumer_name = f"consumer-{os.getpid()}"
        self.ai_provider = self._create_ai_provider()
        self.recipe_extractor = RecipeExtractor(self.ai_provider)
    
    def _create_ai_provider(self) -> AIProvider:
        """Create AI provider based on environment configuration."""
        provider_type = os.getenv("AI_PROVIDER", "openai").lower()
        
        if provider_type == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY environment variable required")
            return AnthropicProvider(api_key)
        else:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable required")
            return OpenAIProvider(api_key)
    
    async def connect(self):
        """Connect to Redis."""
        self.redis = redis.from_url(self.redis_url, decode_responses=True)
        
        # Create consumer group
        try:
            await self.redis.xgroup_create(
                "queue:ai_processing",
                self.group_name,
                id="$",
                mkstream=True
            )
        except redis.ResponseError as e:
            if "already exists" not in str(e):
                raise
    
    async def close(self):
        """Close Redis connection."""
        if self.redis:
            await self.redis.close()
    
    async def run(self):
        """Main worker loop."""
        print(f"AI Worker started with provider: {type(self.ai_provider).__name__}")
        print(f"Consumer: {self.consumer_name}")
        
        while True:
            try:
                processed = await self.process_next_job()
                if not processed:
                    await asyncio.sleep(1)
            except Exception as e:
                print(f"Error in worker loop: {e}")
                await asyncio.sleep(5)
    
    async def process_next_job(self) -> bool:
        """Process the next job from the queue. Returns True if a job was processed."""
        # Read from stream
        messages = await self.redis.xreadgroup(
            groupname=self.group_name,
            consumername=self.consumer_name,
            streams={"queue:ai_processing": ">"},
            count=1,
            block=5000,
        )
        
        if not messages:
            return False
        
        stream_name, stream_messages = messages[0]
        message_id, fields = stream_messages[0]
        
        try:
            job_id = fields.get("job_id")
            video_data_json = fields.get("video_data")
            
            if not job_id or not video_data_json:
                print(f"Invalid message format: {fields}")
                await self._ack_message(stream_name, message_id)
                return True
            
            print(f"Processing job {job_id}")
            
            video_data = json.loads(video_data_json)
            
            # Extract recipe using AI
            recipe = await self.recipe_extractor.extract_recipe(job_id, video_data)
            
            # Store recipe
            await self._store_recipe(job_id, recipe)
            
            # Update job status
            await self._update_job_status(job_id, "completed", 100)
            
            print(f"Job {job_id} completed successfully")
            
        except Exception as e:
            print(f"Failed to process job: {e}")
            if job_id:
                await self._fail_job(job_id, str(e))
        
        finally:
            # Acknowledge message
            await self._ack_message(stream_name, message_id)
        
        return True
    
    async def _update_job_status(self, job_id: str, status: str, progress: int):
        """Update job status in Redis."""
        job_key = f"job:{job_id}"
        job_data = await self.redis.get(job_key)
        
        if job_data:
            job = json.loads(job_data)
            job["status"] = status
            job["progress"] = progress
            job["updated_at"] = datetime.utcnow().isoformat()
            await self.redis.set(job_key, json.dumps(job))
    
    async def _fail_job(self, job_id: str, error: str):
        """Mark job as failed."""
        await self._update_job_status(job_id, "failed", 0)
        
        job_key = f"job:{job_id}"
        job_data = await self.redis.get(job_key)
        
        if job_data:
            job = json.loads(job_data)
            job["error_message"] = error
            await self.redis.set(job_key, json.dumps(job))
    
    async def _store_recipe(self, job_id: str, recipe: Dict[str, Any]):
        """Store extracted recipe in Redis."""
        recipe_key = f"recipe:{job_id}"
        await self.redis.set(recipe_key, json.dumps(recipe))
    
    async def _ack_message(self, stream: str, message_id: str):
        """Acknowledge message processing."""
        await self.redis.xack(stream, self.group_name, message_id)


async def main():
    """Main entry point."""
    worker = AIWorker()
    await worker.connect()
    
    try:
        await worker.run()
    finally:
        await worker.close()


if __name__ == "__main__":
    asyncio.run(main())