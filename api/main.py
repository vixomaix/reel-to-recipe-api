"""Reel to Recipe API - FastAPI main application."""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import extract, recipe
from api.services.queue import RedisQueue


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    app.state.queue = RedisQueue(redis_url)
    await app.state.queue.connect()
    
    yield
    
    # Shutdown
    await app.state.queue.close()


app = FastAPI(
    title="Reel to Recipe API",
    description="Extract recipes from Instagram Reels and TikTok videos",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(extract.router, prefix="/api/v1", tags=["extraction"])
app.include_router(recipe.router, prefix="/api/v1", tags=["recipes"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "reel-to-recipe-api"}


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "Reel to Recipe API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }