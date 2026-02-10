"""pytest configuration and fixtures."""
import asyncio
import json
import os
import tempfile
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient

# Set test environment variables before imports
os.environ["REDIS_URL"] = "redis://localhost:6379/1"  # Use DB 1 for tests
os.environ["TESTING"] = "true"
os.environ["OPENAI_API_KEY"] = "test-key"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_job_data():
    """Return sample job data."""
    return {
        "job_id": "test-job-123",
        "url": "https://www.instagram.com/reel/test123/",
        "platform": "instagram",
        "preferred_language": "en",
        "status": "pending",
        "progress": 0,
        "created_at": "2025-02-10T04:00:00Z",
        "updated_at": "2025-02-10T04:00:00Z",
        "error_message": None,
    }


@pytest.fixture
def mock_video_data():
    """Return mock processed video data."""
    return {
        "job_id": "test-job-123",
        "video_path": "/tmp/videos/test-job-123.mp4",
        "duration_seconds": 45.5,
        "resolution": {"width": 1080, "height": 1920},
        "fps": 30.0,
        "frames": [
            {
                "path": "/tmp/videos/test-job-123/frame_001.jpg",
                "timestamp": 5.0,
                "ocr_text": "2 cups flour\n1 tsp salt",
            },
            {
                "path": "/tmp/videos/test-job-123/frame_002.jpg",
                "timestamp": 15.0,
                "ocr_text": "Mix ingredients",
            },
        ],
        "audio_path": "/tmp/videos/test-job-123/audio.wav",
        "transcription": "First, mix two cups of flour with one teaspoon of salt.",
    }


@pytest.fixture
def mock_recipe_data():
    """Return mock extracted recipe data."""
    return {
        "job_id": "test-job-123",
        "title": "Simple Pasta",
        "description": "A quick and easy pasta recipe",
        "ingredients": [
            {
                "name": "pasta",
                "quantity": "300",
                "unit": "g",
                "optional": False,
                "notes": "",
            },
            {
                "name": "salt",
                "quantity": "1",
                "unit": "tsp",
                "optional": False,
                "notes": "",
            },
        ],
        "instructions": [
            {
                "step_number": 1,
                "description": "Boil water and add salt",
                "timestamp_start": 0.0,
                "timestamp_end": 15.0,
            },
            {
                "step_number": 2,
                "description": "Cook pasta according to package directions",
                "timestamp_start": 15.0,
                "timestamp_end": 45.0,
            },
        ],
        "cook_time_minutes": 10,
        "prep_time_minutes": 5,
        "servings": 4,
        "difficulty": "easy",
        "tags": ["pasta", "quick", "easy"],
        "source_url": "https://www.instagram.com/reel/test123/",
        "confidence_score": 0.95,
    }


@pytest.fixture
def mock_redis_client():
    """Create a mock Redis client."""
    client = MagicMock()
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock(return_value=True)
    client.xadd = AsyncMock(return_value=b"1234567890-0")
    client.keys = AsyncMock(return_value=[])
    client.close = AsyncMock()
    return client


@pytest_asyncio.fixture
async def test_app() -> AsyncGenerator:
    """Create a test FastAPI application."""
    from api.main import app
    from api.services.queue import RedisQueue
    
    # Mock the queue
    mock_queue = MagicMock(spec=RedisQueue)
    mock_queue.client = MagicMock()
    mock_queue.set_job = AsyncMock()
    mock_queue.get_job = AsyncMock(return_value=None)
    mock_queue.update_job = AsyncMock()
    mock_queue.enqueue_video_processing = AsyncMock()
    mock_queue.enqueue_ai_processing = AsyncMock()
    mock_queue.get_recipe = AsyncMock(return_value=None)
    
    app.state.queue = mock_queue
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
def temp_output_dir():
    """Create a temporary output directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_ai_provider():
    """Create a mock AI provider."""
    provider = MagicMock()
    provider.generate_json = AsyncMock(return_value={
        "title": "Test Recipe",
        "ingredients": [],
        "instructions": [],
        "confidence_score": 0.9,
    })
    return provider
