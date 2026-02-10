"""
Authentication Module
Supports API key authentication with JWT
"""

import secrets
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import jwt
from passlib.context import CryptContext

from .database import Database

db = Database()

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT settings
JWT_SECRET = secrets.token_urlsafe(32)
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_DAYS = 30


class AuthError(Exception):
    """Authentication error"""
    pass


async def create_api_key(user_id: str, name: str) -> str:
    """Create a new API key for a user"""
    # Generate secure key
    key = "sk_reel_" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    
    await db.save_api_key(
        user_id=user_id,
        key_hash=key_hash,
        name=name,
        created_at=datetime.utcnow()
    )
    
    return key


async def verify_api_key(key: str) -> Optional[Dict[str, Any]]:
    """Verify an API key and return user info"""
    if not key.startswith("sk_reel_"):
        return None
    
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    
    # Get key from database
    api_key = await db.get_api_key(key_hash)
    
    if not api_key:
        return None
    
    # Check if key is active
    if not api_key.get("is_active", True):
        return None
    
    # Update last used
    await db.update_api_key_usage(key_hash)
    
    return {
        "id": api_key["user_id"],
        "tier": api_key.get("tier", "free"),
        "rate_limit": get_rate_limit_for_tier(api_key.get("tier", "free"))
    }


async def get_user_from_key(key: str) -> Optional[Dict[str, Any]]:
    """Get user info from API key"""
    return await verify_api_key(key)


def get_rate_limit_for_tier(tier: str) -> Dict[str, int]:
    """Get rate limits for user tier"""
    limits = {
        "free": {
            "requests_per_minute": 10,
            "requests_per_hour": 100,
            "requests_per_day": 500,
            "batch_max_urls": 10
        },
        "basic": {
            "requests_per_minute": 30,
            "requests_per_hour": 500,
            "requests_per_day": 2000,
            "batch_max_urls": 50
        },
        "pro": {
            "requests_per_minute": 100,
            "requests_per_hour": 2000,
            "requests_per_day": 10000,
            "batch_max_urls": 100
        },
        "enterprise": {
            "requests_per_minute": 500,
            "requests_per_hour": 10000,
            "requests_per_day": 100000,
            "batch_max_urls": 500
        }
    }
    return limits.get(tier, limits["free"])


def create_jwt_token(user_id: str, tier: str = "free") -> str:
    """Create JWT token for user"""
    payload = {
        "user_id": user_id,
        "tier": tier,
        "exp": datetime.utcnow() + timedelta(days=JWT_EXPIRATION_DAYS),
        "iat": datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return {
            "id": payload["user_id"],
            "tier": payload.get("tier", "free")
        }
    except jwt.ExpiredSignatureError:
        raise AuthError("Token has expired")
    except jwt.InvalidTokenError:
        raise AuthError("Invalid token")


def hash_password(password: str) -> str:
    """Hash password"""
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Verify password"""
    return pwd_context.verify(password, hashed)
