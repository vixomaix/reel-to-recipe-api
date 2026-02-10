"""
API Configuration
"""

import os

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Cache configuration
CACHE_TTL = int(os.getenv("CACHE_TTL", "86400"))  # 24 hours

# Database configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/reel_to_recipe"
)

# API configuration
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Webhook configuration
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

# AI Provider configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# File upload limits
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", "50")) * 1024 * 1024  # MB to bytes
MAX_BATCH_SIZE = int(os.getenv("MAX_BATCH_SIZE", "100"))
