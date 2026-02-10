"""
Background Tasks Module
Handles async processing of reels and batches
"""

import json
import httpx
import asyncio
from typing import Dict, Any, Optional
from pathlib import Path

from ..src.main_v2 import ReelExtractorV2
from .database import Database
from .cache import Cache

db = Database()
cache = Cache()


async def process_reel_task(
    job_id: str,
    url: str,
    options: Dict[str, Any],
    webhook: Optional[str] = None,
    user_id: Optional[str] = None
):
    """
    Process reel in background
    
    Args:
        job_id: Unique job ID
        url: Instagram reel URL
        options: Extraction options
        webhook: Webhook URL for callback
        user_id: User ID for tracking
    """
    try:
        # Update job status
        await cache.set_job_status(job_id, {
            "status": "processing",
            "progress": 0
        })
        
        # Initialize extractor
        extractor = ReelExtractorV2(
            output_dir=Path(f"./output/{job_id}"),
            use_cache=True
        )
        
        # Process reel
        result = extractor.extract_reel(
            url=url,
            extract_recipe=options.get("extract_recipe", True),
            num_frames=options.get("num_frames", 8),
            use_ai=True,
            transcribe=options.get("transcribe", True)
        )
        
        # Save to database
        if user_id:
            await db.save_extraction(
                job_id=job_id,
                user_id=user_id,
                url=url,
                result=result,
                status="completed" if result.get("success") else "failed"
            )
        
        # Update cache
        await cache.set_job_status(job_id, {
            "status": "completed" if result.get("success") else "failed",
            "result": result
        })
        
        # Send webhook if configured
        if webhook:
            await send_webhook(webhook, {
                "job_id": job_id,
                "status": "completed",
                "result": result
            })
        
    except Exception as e:
        error_result = {
            "status": "failed",
            "error": str(e)
        }
        
        await cache.set_job_status(job_id, error_result)
        
        if user_id:
            await db.save_extraction(
                job_id=job_id,
                user_id=user_id,
                url=url,
                result={},
                status="failed",
                error=str(e)
            )
        
        if webhook:
            await send_webhook(webhook, {
                "job_id": job_id,
                "status": "failed",
                "error": str(e)
            })


async def process_batch_task(
    job_id: str,
    urls: list,
    options: Dict[str, Any],
    webhook: str,
    user_id: Optional[str] = None
):
    """
    Process batch of reels
    
    Args:
        job_id: Unique job ID
        urls: List of Instagram reel URLs
        options: Extraction options
        webhook: Webhook URL for results
        user_id: User ID for tracking
    """
    total = len(urls)
    completed = 0
    failed = 0
    results = []
    
    try:
        extractor = ReelExtractorV2(
            output_dir=Path(f"./output/{job_id}"),
            use_cache=True
        )
        
        for i, url in enumerate(urls):
            try:
                # Update progress
                await cache.set_job_status(job_id, {
                    "status": "processing",
                    "progress": int((i / total) * 100),
                    "completed": completed,
                    "failed": failed
                })
                
                # Process reel
                result = extractor.extract_reel(
                    url=url,
                    extract_recipe=options.get("extract_recipe", True),
                    num_frames=options.get("num_frames", 8),
                    use_ai=True,
                    transcribe=options.get("transcribe", True)
                )
                
                results.append({"url": url, "result": result, "success": True})
                completed += 1
                
            except Exception as e:
                results.append({
                    "url": url,
                    "success": False,
                    "error": str(e)
                })
                failed += 1
        
        final_result = {
            "job_id": job_id,
            "status": "completed",
            "total": total,
            "completed": completed,
            "failed": failed,
            "results": results
        }
        
        await cache.set_job_status(job_id, final_result)
        
        # Send webhook
        await send_webhook(webhook, final_result)
        
    except Exception as e:
        error_result = {
            "job_id": job_id,
            "status": "failed",
            "error": str(e)
        }
        await cache.set_job_status(job_id, error_result)
        await send_webhook(webhook, error_result)


async def send_webhook(webhook_url: str, payload: Dict[str, Any]):
    """Send webhook notification"""
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30.0
            )
    except Exception as e:
        print(f"Webhook delivery failed: {e}")
