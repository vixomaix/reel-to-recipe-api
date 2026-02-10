"""
FastAPI Application for Reel to Recipe API
Production-ready with authentication, rate limiting, and comprehensive error handling.
"""

import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, UploadFile, File, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.openapi.docs import get_swagger_ui_html
from pydantic import BaseModel, Field, HttpUrl, validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import structlog
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from ..src.main_v2 import ReelExtractorV2
from ..src.config import AIProvider
from .auth import verify_api_key, create_api_key, get_user_from_key
from .rate_limiter import RateLimiter
from .tasks import process_reel_task
from .models import (
    ReelExtractionRequest,
    ReelExtractionResponse,
    BatchExtractionRequest,
    BatchExtractionResponse,
    RecipeResponse,
    HealthResponse,
    ErrorResponse,
    ProcessingStatus,
    WebhookConfig
)
from .database import Database
from .cache import Cache
from .tracing import setup_tracing, get_tracer

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Prometheus metrics
REQUEST_COUNT = Counter(
    'reel_api_requests_total',
    'Total requests',
    ['method', 'endpoint', 'status']
)
REQUEST_DURATION = Histogram(
    'reel_api_request_duration_seconds',
    'Request duration',
    ['method', 'endpoint']
)
RECIPE_EXTRACTION_COUNT = Counter(
    'reel_recipe_extractions_total',
    'Recipe extractions',
    ['status', 'cuisine_type']
)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Initialize components
db = Database()
cache = Cache()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup
    logger.info("Starting Reel to Recipe API")
    await db.connect()
    await cache.connect()
    setup_tracing()
    yield
    # Shutdown
    logger.info("Shutting down Reel to Recipe API")
    await db.disconnect()
    await cache.disconnect()


# Create FastAPI app
app = FastAPI(
    title="Reel to Recipe API",
    description="AI-powered API for extracting recipes from Instagram Reels",
    version="2.0.0",
    docs_url=None,  # Custom docs endpoint
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# Add rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add middlewares
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://api.reeltorecipe.com", "https://app.reeltorecipe.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining"]
)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=["api.reeltorecipe.com", "*.reeltorecipe.com"])


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses"""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Request-ID"] = str(uuid.uuid4())
    return response


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests with structured logging"""
    start_time = time.time()
    request_id = str(uuid.uuid4())
    
    # Add request ID to context
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        client_ip=get_remote_address(request)
    )
    
    try:
        response = await call_next(request)
        duration = time.time() - start_time
        
        # Record metrics
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status=response.status_code
        ).inc()
        REQUEST_DURATION.labels(
            method=request.method,
            endpoint=request.url.path
        ).observe(duration)
        
        logger.info(
            "Request completed",
            status_code=response.status_code,
            duration=duration
        )
        
        response.headers["X-Request-ID"] = request_id
        return response
        
    except Exception as e:
        logger.error("Request failed", error=str(e))
        raise


security = HTTPBearer()


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Validate API key and return user info"""
    token = credentials.credentials
    user = await verify_api_key(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return user


async def check_rate_limit(request: Request, user: Dict = Depends(get_current_user)):
    """Check user-specific rate limits"""
    rate_limiter = RateLimiter()
    allowed, limit, remaining = await rate_limiter.check_limit(
        user["id"],
        user["tier"]
    )
    
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded"
        )
    
    request.state.rate_limit = limit
    request.state.rate_limit_remaining = remaining
    return user


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    """Custom Swagger UI"""
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="Reel to Recipe API - Documentation",
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css"
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        version="2.0.0",
        timestamp=datetime.utcnow().isoformat(),
        services={
            "database": await db.is_connected(),
            "cache": await cache.is_connected(),
            "ai_providers": True  # TODO: Check AI provider availability
        }
    )


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


@app.post(
    "/api/v2/extract",
    response_model=ReelExtractionResponse,
    responses={
        401: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        500: {"model": ErrorResponse}
    }
)
@limiter.limit("10/minute")
async def extract_reel(
    request: Request,
    extraction_request: ReelExtractionRequest,
    background_tasks: BackgroundTasks,
    user: Dict = Depends(check_rate_limit)
):
    """
    Extract recipe and analysis from an Instagram Reel
    
    - **url**: Instagram Reel URL
    - **extract_recipe**: Whether to extract recipe (default: True)
    - **provider**: AI provider to use (default: auto)
    - **webhook**: Optional webhook URL for async processing
    """
    tracer = get_tracer()
    with tracer.start_as_current_span("extract_reel") as span:
        span.set_attribute("reel.url", str(extraction_request.url))
        span.set_attribute("user.id", user["id"])
        
        job_id = str(uuid.uuid4())
        
        # Check cache first
        cache_key = f"reel:{hash(str(extraction_request.url))}"
        cached_result = await cache.get(cache_key)
        
        if cached_result and not extraction_request.force_refresh:
            logger.info("Cache hit", job_id=job_id)
            return ReelExtractionResponse(
                job_id=job_id,
                status=ProcessingStatus.COMPLETED,
                cached=True,
                result=cached_result
            )
        
        # If webhook provided, process asynchronously
        if extraction_request.webhook:
            background_tasks.add_task(
                process_reel_task,
                job_id=job_id,
                url=str(extraction_request.url),
                options=extraction_request.dict(),
                webhook=extraction_request.webhook,
                user_id=user["id"]
            )
            
            return ReelExtractionResponse(
                job_id=job_id,
                status=ProcessingStatus.PENDING,
                cached=False,
                message="Processing started. Results will be sent to webhook."
            )
        
        # Process synchronously
        try:
            extractor = ReelExtractorV2(
                output_dir=Path(f"./output/{job_id}"),
                use_cache=True
            )
            
            result = extractor.extract_reel(
                url=str(extraction_request.url),
                extract_recipe=extraction_request.extract_recipe,
                num_frames=extraction_request.num_frames or 8,
                use_ai=True,
                transcribe=extraction_request.transcribe
            )
            
            # Cache result
            await cache.set(cache_key, result, ttl=86400)
            
            # Record metrics
            if result.get("recipe"):
                RECIPE_EXTRACTION_COUNT.labels(
                    status="success",
                    cuisine_type=result["recipe"].get("cuisine_type", "unknown")
                ).inc()
            
            # Save to database
            await db.save_extraction(
                job_id=job_id,
                user_id=user["id"],
                url=str(extraction_request.url),
                result=result
            )
            
            return ReelExtractionResponse(
                job_id=job_id,
                status=ProcessingStatus.COMPLETED if result.get("success") else ProcessingStatus.FAILED,
                cached=False,
                result=result
            )
            
        except Exception as e:
            logger.error("Extraction failed", error=str(e), job_id=job_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Extraction failed: {str(e)}"
            )


@app.post(
    "/api/v2/batch",
    response_model=BatchExtractionResponse
)
@limiter.limit("5/hour")
async def batch_extract(
    request: Request,
    batch_request: BatchExtractionRequest,
    background_tasks: BackgroundTasks,
    user: Dict = Depends(check_rate_limit)
):
    """
    Process multiple reels in batch
    
    - **urls**: List of Instagram Reel URLs
    - **options**: Extraction options
    """
    job_id = str(uuid.uuid4())
    
    if batch_request.webhook:
        background_tasks.add_task(
            process_batch_task,
            job_id=job_id,
            urls=[str(u) for u in batch_request.urls],
            options=batch_request.options,
            webhook=batch_request.webhook,
            user_id=user["id"]
        )
        
        return BatchExtractionResponse(
            job_id=job_id,
            status=ProcessingStatus.PENDING,
            total=len(batch_request.urls),
            completed=0,
            failed=0,
            message="Batch processing started"
        )
    
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Batch processing requires webhook URL"
    )


@app.get("/api/v2/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    user: Dict = Depends(get_current_user)
):
    """Get status of a processing job"""
    job = await db.get_job(job_id, user["id"])
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    
    return {
        "job_id": job_id,
        "status": job["status"],
        "created_at": job["created_at"],
        "completed_at": job.get("completed_at"),
        "result": job.get("result")
    }


@app.get("/api/v2/recipes/{recipe_id}", response_model=RecipeResponse)
async def get_recipe(
    recipe_id: str,
    format: str = "json",  # json, markdown, json-ld
    user: Dict = Depends(get_current_user)
):
    """Get a specific recipe in various formats"""
    recipe = await db.get_recipe(recipe_id)
    
    if not recipe:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipe not found"
        )
    
    if format == "markdown":
        return Response(
            content=recipe["markdown"],
            media_type="text/markdown"
        )
    elif format == "json-ld":
        return JSONResponse(content=recipe["json_ld"])
    
    return RecipeResponse(**recipe)


@app.get("/api/v2/user/stats")
async def get_user_stats(user: Dict = Depends(get_current_user)):
    """Get user's usage statistics"""
    stats = await db.get_user_stats(user["id"])
    return {
        "user_id": user["id"],
        "tier": user["tier"],
        "total_extractions": stats["total"],
        "successful_extractions": stats["successful"],
        "recipes_found": stats["recipes"],
        "api_calls_this_month": stats["api_calls_month"],
        "rate_limit": user["rate_limit"]
    }


@app.get("/api/v2/user/extractions")
async def list_extractions(
    page: int = 1,
    limit: int = 20,
    user: Dict = Depends(get_current_user)
):
    """List user's extraction history"""
    extractions = await db.list_extractions(
        user_id=user["id"],
        page=page,
        limit=limit
    )
    return extractions


@app.post("/api/v2/keys")
async def create_api_key_endpoint(
    name: str,
    user: Dict = Depends(get_current_user)
):
    """Create a new API key"""
    key = await create_api_key(user["id"], name)
    return {
        "api_key": key,
        "name": name,
        "created_at": datetime.utcnow().isoformat()
    }


@app.get("/api/v2/providers")
async def list_providers():
    """List available AI providers"""
    return {
        "providers": [
            {"id": "openai", "name": "OpenAI", "models": ["gpt-4o", "gpt-4o-mini"]},
            {"id": "anthropic", "name": "Anthropic", "models": ["claude-3-opus", "claude-3-sonnet"]},
            {"id": "gemini", "name": "Google Gemini", "models": ["gemini-pro-vision"]},
            {"id": "ollama", "name": "Ollama (Local)", "models": ["llava", "llama2"]},
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
