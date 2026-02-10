"""Recipe routes for retrieving extracted recipes."""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from api.models.schemas import JobStatusResponse
from shared.models import Recipe

router = APIRouter()


@router.get("/recipe/{job_id}", response_model=Recipe)
async def get_recipe(request: Request, job_id: str):
    """Get the extracted recipe for a completed job."""
    queue = request.app.state.queue
    
    # Get job status
    job = await queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job["status"] != "completed":
        raise HTTPException(
            status_code=400, 
            detail=f"Recipe not ready. Job status: {job['status']}"
        )
    
    # Get recipe from Redis
    recipe_data = await queue.get_recipe(job_id)
    if not recipe_data:
        raise HTTPException(status_code=404, detail="Recipe not found")
    
    return Recipe(**recipe_data)


@router.get("/recipes")
async def list_recipes(
    request: Request,
    search: Optional[str] = Query(None, description="Search in recipe titles"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List extracted recipes with filtering."""
    queue = request.app.state.queue
    recipes = await queue.list_recipes(search=search, tag=tag, limit=limit, offset=offset)
    
    return {
        "recipes": recipes,
        "total": len(recipes),
    }


@router.get("/recipe/{job_id}/status")
async def get_recipe_status(request: Request, job_id: str):
    """Get both job status and recipe (if available)."""
    queue = request.app.state.queue
    
    job = await queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    recipe_data = None
    if job["status"] == "completed":
        recipe_data = await queue.get_recipe(job_id)
    
    return {
        "job": JobStatusResponse(**job),
        "recipe": Recipe(**recipe_data) if recipe_data else None,
    }