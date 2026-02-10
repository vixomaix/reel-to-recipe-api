"""Extraction routes for video processing jobs."""
from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request

from api.models.schemas import ExtractRequest, ExtractResponse, JobListResponse, JobStatusResponse

router = APIRouter()


def detect_platform(url: str) -> str:
    """Auto-detect platform from URL."""
    url_lower = url.lower()
    if "instagram.com" in url_lower or "instagr.am" in url_lower:
        return "instagram"
    elif "tiktok.com" in url_lower or "vm.tiktok" in url_lower:
        return "tiktok"
    elif "youtube.com/shorts" in url_lower or "youtu.be" in url_lower:
        return "youtube_shorts"
    return "unknown"


@router.post("/extract", response_model=ExtractResponse)
async def create_extraction_job(request: Request, extract_req: ExtractRequest):
    """Create a new video extraction job.
    
    This will:
    1. Download the video
    2. Extract frames and perform OCR
    3. Extract and transcribe audio
    4. Use AI to extract the recipe
    """
    queue = request.app.state.queue
    
    job_id = str(uuid4())
    platform = extract_req.platform or detect_platform(str(extract_req.url))
    
    job_data = {
        "job_id": job_id,
        "url": str(extract_req.url),
        "platform": platform,
        "preferred_language": extract_req.preferred_language,
        "status": "pending",
        "progress": 0,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "error_message": None,
    }
    
    # Store job in Redis
    await queue.set_job(job_id, job_data)
    
    # Queue the job for Rust worker
    await queue.enqueue_video_processing(job_id, job_data)
    
    return ExtractResponse(
        job_id=job_id,
        status="pending",
        check_status_url=f"/api/v1/jobs/{job_id}",
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(request: Request, job_id: str):
    """Get the status of a job."""
    queue = request.app.state.queue
    job = await queue.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return JobStatusResponse(**job)


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    request: Request,
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List jobs with optional filtering."""
    queue = request.app.state.queue
    jobs = await queue.list_jobs(status=status, limit=limit, offset=offset)
    total = await queue.count_jobs(status=status)
    
    return JobListResponse(
        jobs=[JobStatusResponse(**job) for job in jobs],
        total=total,
    )


@router.delete("/jobs/{job_id}")
async def cancel_job(request: Request, job_id: str):
    """Cancel a pending job."""
    queue = request.app.state.queue
    job = await queue.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job["status"] == "completed":
        raise HTTPException(status_code=400, detail="Cannot cancel completed job")
    
    await queue.update_job(job_id, {"status": "failed", "error_message": "Cancelled by user"})
    
    return {"message": "Job cancelled successfully"}