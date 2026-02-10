"""Pydantic models for API requests/responses."""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl


class ExtractRequest(BaseModel):
    """Request to extract recipe from video."""
    url: HttpUrl = Field(..., description="URL of the Instagram Reel or TikTok video")
    platform: Optional[str] = Field(None, description="Source platform (auto-detected if not provided)")
    preferred_language: str = Field("en", description="Preferred language for recipe extraction")


class JobStatusResponse(BaseModel):
    """Job status response."""
    job_id: str
    status: str
    url: str
    created_at: datetime
    updated_at: datetime
    progress: int = Field(0, ge=0, le=100)
    error_message: Optional[str] = None


class JobListResponse(BaseModel):
    """List of jobs response."""
    jobs: List[JobStatusResponse]
    total: int


class ExtractResponse(BaseModel):
    """Extract request response."""
    job_id: str
    status: str
    message: str = "Video extraction queued successfully"
    check_status_url: str