"""Shared Pydantic models for Reel to Recipe API."""
from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl


class JobStatus(str, Enum):
    """Job processing status."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PROCESSING_VIDEO = "processing_video"
    EXTRACTING_OCR = "extracting_ocr"
    TRANSCRIBING_AUDIO = "transcribing_audio"
    AI_PROCESSING = "ai_processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ExtractRequest(BaseModel):
    """Request to extract recipe from video."""
    url: HttpUrl = Field(..., description="URL of the Instagram Reel or TikTok video")
    platform: Optional[str] = Field(None, description="Source platform (auto-detected if not provided)")
    preferred_language: str = Field("en", description="Preferred language for recipe extraction")


class JobResponse(BaseModel):
    """Job status response."""
    job_id: str
    status: JobStatus
    url: str
    created_at: datetime
    updated_at: datetime
    progress: int = Field(0, ge=0, le=100)
    error_message: Optional[str] = None


class FrameData(BaseModel):
    """Extracted frame data."""
    timestamp: float = Field(..., description="Timestamp in seconds")
    frame_path: str = Field(..., description="Path to extracted frame image")
    ocr_text: Optional[str] = Field(None, description="Text extracted from this frame via OCR")
    is_keyframe: bool = Field(False, description="Whether this is a scene change keyframe")


class VideoData(BaseModel):
    """Processed video data from Rust worker."""
    job_id: str
    video_path: str
    duration_seconds: Optional[float] = None
    resolution: Optional[dict] = None
    fps: Optional[float] = None
    frames: List[FrameData] = Field(default_factory=list)
    audio_path: Optional[str] = None
    transcription: Optional[str] = None


class Ingredient(BaseModel):
    """Recipe ingredient."""
    name: str
    quantity: Optional[str] = None
    unit: Optional[str] = None
    optional: bool = False
    notes: Optional[str] = None


class Instruction(BaseModel):
    """Recipe instruction step."""
    step_number: int
    description: str
    timestamp_start: Optional[float] = Field(None, description="Video timestamp where this step begins")
    timestamp_end: Optional[float] = Field(None, description="Video timestamp where this step ends")


class Recipe(BaseModel):
    """Extracted recipe."""
    job_id: str
    title: str
    description: Optional[str] = None
    ingredients: List[Ingredient] = Field(default_factory=list)
    instructions: List[Instruction] = Field(default_factory=list)
    cook_time_minutes: Optional[int] = None
    prep_time_minutes: Optional[int] = None
    servings: Optional[int] = None
    difficulty: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    source_url: str
    thumbnail_url: Optional[str] = None
    confidence_score: float = Field(0.0, ge=0, le=1)


class RecipeResponse(BaseModel):
    """Recipe response with job status."""
    job: JobResponse
    recipe: Optional[Recipe] = None