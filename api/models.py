"""
API Models and Schemas
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl, validator


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AIProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OLLAMA = "ollama"
    AUTO = "auto"


class OutputFormat(str, Enum):
    JSON = "json"
    MARKDOWN = "markdown"
    JSON_LD = "json-ld"


class ReelExtractionRequest(BaseModel):
    """Request model for reel extraction"""
    url: HttpUrl = Field(..., description="Instagram Reel URL")
    extract_recipe: bool = Field(True, description="Extract recipe if cooking content detected")
    transcribe: bool = Field(True, description="Transcribe audio")
    num_frames: Optional[int] = Field(8, ge=1, le=30, description="Number of frames to extract")
    provider: AIProvider = Field(AIProvider.AUTO, description="AI provider to use")
    webhook: Optional[HttpUrl] = Field(None, description="Webhook URL for async processing")
    force_refresh: bool = Field(False, description="Force re-processing even if cached")
    output_format: OutputFormat = Field(OutputFormat.JSON, description="Output format")
    
    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://www.instagram.com/reel/ABC123/",
                "extract_recipe": True,
                "transcribe": True,
                "num_frames": 8,
                "provider": "auto"
            }
        }


class ReelExtractionResponse(BaseModel):
    """Response model for reel extraction"""
    job_id: str
    status: ProcessingStatus
    cached: bool = False
    result: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    processing_time: Optional[float] = None


class BatchExtractionRequest(BaseModel):
    """Request model for batch extraction"""
    urls: List[HttpUrl] = Field(..., min_items=1, max_items=100, description="List of Instagram Reel URLs")
    options: Optional[Dict[str, Any]] = Field(None, description="Extraction options")
    webhook: HttpUrl = Field(..., description="Webhook URL for results")
    
    @validator('urls')
    def validate_urls(cls, v):
        if len(v) > 100:
            raise ValueError("Maximum 100 URLs per batch")
        return v


class BatchExtractionResponse(BaseModel):
    """Response model for batch extraction"""
    job_id: str
    status: ProcessingStatus
    total: int
    completed: int
    failed: int
    results: Optional[List[Dict[str, Any]]] = None
    message: Optional[str] = None


class Ingredient(BaseModel):
    """Recipe ingredient"""
    name: str
    quantity: Optional[str] = None
    unit: Optional[str] = None
    notes: Optional[str] = None


class CookingStep(BaseModel):
    """Cooking step"""
    step_number: int
    instruction: str
    duration: Optional[str] = None
    temperature: Optional[str] = None


class RecipeResponse(BaseModel):
    """Recipe response model"""
    id: str
    title: str
    description: Optional[str] = None
    cuisine_type: Optional[str] = None
    meal_type: Optional[str] = None
    dish_type: Optional[str] = None
    diet_type: List[str] = []
    difficulty: Optional[str] = None
    prep_time: Optional[str] = None
    cook_time: Optional[str] = None
    total_time: Optional[str] = None
    servings: Optional[int] = None
    ingredients: List[Ingredient] = []
    steps: List[CookingStep] = []
    tips: List[str] = []
    variations: List[str] = []
    confidence_score: float = 0.0
    source_url: Optional[str] = None
    created_at: datetime


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    version: str
    timestamp: str
    services: Dict[str, bool]


class ErrorResponse(BaseModel):
    """Error response model"""
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None
    request_id: Optional[str] = None


class WebhookConfig(BaseModel):
    """Webhook configuration"""
    url: HttpUrl
    secret: Optional[str] = None
    events: List[str] = ["extraction.completed", "extraction.failed"]


class UserStats(BaseModel):
    """User statistics"""
    user_id: str
    tier: str
    total_extractions: int
    successful_extractions: int
    recipes_found: int
    api_calls_this_month: int
    rate_limit: int


class ExtractionHistoryItem(BaseModel):
    """Single extraction history item"""
    job_id: str
    url: str
    status: ProcessingStatus
    created_at: datetime
    completed_at: Optional[datetime] = None
    has_recipe: bool


class ExtractionHistory(BaseModel):
    """Extraction history response"""
    items: List[ExtractionHistoryItem]
    total: int
    page: int
    pages: int
