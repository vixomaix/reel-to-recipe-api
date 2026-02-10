"""
Database Module
Supports PostgreSQL for persistent storage
"""

import os
from typing import Optional, Dict, Any, List
from datetime import datetime
import asyncpg
from contextlib import asynccontextmanager

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/reel_to_recipe")


class Database:
    """PostgreSQL database handler"""
    
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        """Create connection pool"""
        self.pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=5,
            max_size=20
        )
        await self._create_tables()
    
    async def disconnect(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
    
    async def is_connected(self) -> bool:
        """Check if database is connected"""
        if not self.pool:
            return False
        try:
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except:
            return False
    
    async def _create_tables(self):
        """Create necessary tables"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    email VARCHAR(255) UNIQUE NOT NULL,
                    tier VARCHAR(20) DEFAULT 'free',
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    key_hash VARCHAR(64) UNIQUE NOT NULL,
                    name VARCHAR(100),
                    is_active BOOLEAN DEFAULT TRUE,
                    last_used_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS extractions (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    job_id VARCHAR(36) UNIQUE NOT NULL,
                    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                    url TEXT NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    result JSONB,
                    error TEXT,
                    processing_time_ms INTEGER,
                    created_at TIMESTAMP DEFAULT NOW(),
                    completed_at TIMESTAMP
                )
            """)
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS recipes (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    extraction_id UUID REFERENCES extractions(id) ON DELETE CASCADE,
                    title VARCHAR(255),
                    cuisine_type VARCHAR(100),
                    ingredients JSONB,
                    steps JSONB,
                    metadata JSONB,
                    confidence_score FLOAT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_extractions_user_id 
                ON extractions(user_id)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_extractions_job_id 
                ON extractions(job_id)
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_extractions_created_at 
                ON extractions(created_at DESC)
            """)
    
    async def save_extraction(
        self,
        job_id: str,
        user_id: str,
        url: str,
        result: Dict[str, Any],
        status: str = "completed",
        error: Optional[str] = None
    ):
        """Save extraction result"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO extractions (
                    job_id, user_id, url, status, result, error, completed_at
                ) VALUES ($1, $2, $3, $4, $5, $6, NOW())
            """, job_id, user_id, url, status, json.dumps(result), error)
            
            # Save recipe if found
            if result.get("recipe"):
                extraction_id = await conn.fetchval(
                    "SELECT id FROM extractions WHERE job_id = $1",
                    job_id
                )
                recipe = result["recipe"]
                await conn.execute("""
                    INSERT INTO recipes (
                        extraction_id, title, cuisine_type, ingredients,
                        steps, metadata, confidence_score
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                    extraction_id,
                    recipe.get("title"),
                    recipe.get("cuisine_type"),
                    json.dumps(recipe.get("ingredients", [])),
                    json.dumps(recipe.get("steps", [])),
                    json.dumps(recipe),
                    recipe.get("confidence_score", 0)
                )
    
    async def get_job(self, job_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get job by ID"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM extractions 
                WHERE job_id = $1 AND user_id = $2
            """, job_id, user_id)
            
            if row:
                return dict(row)
            return None
    
    async def get_recipe(self, recipe_id: str) -> Optional[Dict[str, Any]]:
        """Get recipe by ID"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM recipes WHERE id = $1
            """, recipe_id)
            
            if row:
                return dict(row)
            return None
    
    async def list_extractions(
        self,
        user_id: str,
        page: int = 1,
        limit: int = 20
    ) -> Dict[str, Any]:
        """List user extractions with pagination"""
        offset = (page - 1) * limit
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT 
                    job_id,
                    url,
                    status,
                    created_at,
                    completed_at,
                    result->>'recipe' IS NOT NULL as has_recipe
                FROM extractions 
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
            """, user_id, limit, offset)
            
            total = await conn.fetchval("""
                SELECT COUNT(*) FROM extractions WHERE user_id = $1
            """, user_id)
            
            return {
                "items": [dict(row) for row in rows],
                "total": total,
                "page": page,
                "pages": (total + limit - 1) // limit
            }
    
    async def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """Get user statistics"""
        async with self.pool.acquire() as conn:
            total = await conn.fetchval("""
                SELECT COUNT(*) FROM extractions WHERE user_id = $1
            """, user_id)
            
            successful = await conn.fetchval("""
                SELECT COUNT(*) FROM extractions 
                WHERE user_id = $1 AND status = 'completed'
            """, user_id)
            
            recipes = await conn.fetchval("""
                SELECT COUNT(*) FROM recipes r
                JOIN extractions e ON r.extraction_id = e.id
                WHERE e.user_id = $1
            """, user_id)
            
            # API calls this month
            month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0)
            api_calls_month = await conn.fetchval("""
                SELECT COUNT(*) FROM extractions 
                WHERE user_id = $1 AND created_at >= $2
            """, user_id, month_start)
            
            return {
                "total": total,
                "successful": successful,
                "recipes": recipes,
                "api_calls_month": api_calls_month
            }
    
    async def save_api_key(
        self,
        user_id: str,
        key_hash: str,
        name: str,
        created_at: datetime
    ):
        """Save API key"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO api_keys (user_id, key_hash, name, created_at)
                VALUES ($1, $2, $3, $4)
            """, user_id, key_hash, name, created_at)
    
    async def get_api_key(self, key_hash: str) -> Optional[Dict[str, Any]]:
        """Get API key by hash"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT ak.*, u.tier 
                FROM api_keys ak
                JOIN users u ON ak.user_id = u.id
                WHERE ak.key_hash = $1
            """, key_hash)
            
            if row:
                return dict(row)
            return None
    
    async def update_api_key_usage(self, key_hash: str):
        """Update API key last used timestamp"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE api_keys 
                SET last_used_at = NOW() 
                WHERE key_hash = $1
            """, key_hash)
