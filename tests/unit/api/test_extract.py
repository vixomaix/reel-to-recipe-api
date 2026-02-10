"""Unit tests for extraction routes."""
import pytest
from fastapi import status


class TestExtractRoutes:
    """Tests for video extraction endpoints."""
    
    async def test_create_extraction_job(self, test_app, sample_job_data):
        """Test creating a new extraction job."""
        response = await test_app.post(
            "/api/v1/extract",
            json={
                "url": "https://www.instagram.com/reel/test123/",
                "preferred_language": "en",
            }
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "pending"
        assert "/api/v1/jobs/" in data["check_status_url"]
    
    async def test_create_extraction_job_auto_detect_platform(self, test_app):
        """Test platform auto-detection from URL."""
        test_cases = [
            ("https://www.instagram.com/reel/ABC123/", "instagram"),
            ("https://www.tiktok.com/@user/video/123456", "tiktok"),
            ("https://youtube.com/shorts/ABC123", "youtube_shorts"),
        ]
        
        for url, expected_platform in test_cases:
            response = await test_app.post(
                "/api/v1/extract",
                json={"url": url}
            )
            
            assert response.status_code == status.HTTP_200_OK
    
    async def test_create_extraction_job_invalid_url(self, test_app):
        """Test validation of invalid URLs."""
        response = await test_app.post(
            "/api/v1/extract",
            json={"url": "not-a-valid-url"}
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    async def test_get_job_status(self, test_app, sample_job_data):
        """Test getting job status."""
        # First create a job
        create_response = await test_app.post(
            "/api/v1/extract",
            json={"url": "https://www.instagram.com/reel/test123/"}
        )
        job_id = create_response.json()["job_id"]
        
        # Mock the job data
        test_app.app.state.queue.get_job.return_value = sample_job_data
        
        # Get job status
        response = await test_app.get(f"/api/v1/jobs/{job_id}")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["job_id"] == sample_job_data["job_id"]
        assert data["status"] == sample_job_data["status"]
    
    async def test_get_job_status_not_found(self, test_app):
        """Test getting status of non-existent job."""
        test_app.app.state.queue.get_job.return_value = None
        
        response = await test_app.get("/api/v1/jobs/non-existent-job")
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    async def test_list_jobs(self, test_app, sample_job_data):
        """Test listing jobs."""
        test_app.app.state.queue.list_jobs.return_value = [sample_job_data]
        test_app.app.state.queue.count_jobs.return_value = 1
        
        response = await test_app.get("/api/v1/jobs")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 1
        assert len(data["jobs"]) == 1
    
    async def test_list_jobs_with_status_filter(self, test_app, sample_job_data):
        """Test listing jobs with status filter."""
        test_app.app.state.queue.list_jobs.return_value = [sample_job_data]
        test_app.app.state.queue.count_jobs.return_value = 1
        
        response = await test_app.get("/api/v1/jobs?status=pending")
        
        assert response.status_code == status.HTTP_200_OK
        test_app.app.state.queue.list_jobs.assert_called_once_with(
            status="pending", limit=20, offset=0
        )
    
    async def test_cancel_job(self, test_app, sample_job_data):
        """Test cancelling a pending job."""
        # Create job
        create_response = await test_app.post(
            "/api/v1/extract",
            json={"url": "https://www.instagram.com/reel/test123/"}
        )
        job_id = create_response.json()["job_id"]
        
        # Mock job data
        test_app.app.state.queue.get_job.return_value = sample_job_data
        
        # Cancel job
        response = await test_app.delete(f"/api/v1/jobs/{job_id}")
        
        assert response.status_code == status.HTTP_200_OK
        assert "cancelled" in response.json()["message"].lower()
    
    async def test_cancel_completed_job(self, test_app):
        """Test cancelling a completed job fails."""
        test_app.app.state.queue.get_job.return_value = {
            "job_id": "test",
            "status": "completed"
        }
        
        response = await test_app.delete("/api/v1/jobs/test")
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestRecipeRoutes:
    """Tests for recipe endpoints."""
    
    async def test_get_recipe(self, test_app, mock_recipe_data):
        """Test getting an extracted recipe."""
        test_app.app.state.queue.get_recipe.return_value = mock_recipe_data
        
        response = await test_app.get("/api/v1/recipe/test-job-123")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["job_id"] == mock_recipe_data["job_id"]
        assert data["title"] == mock_recipe_data["title"]
        assert len(data["ingredients"]) == len(mock_recipe_data["ingredients"])
    
    async def test_get_recipe_not_found(self, test_app):
        """Test getting non-existent recipe."""
        test_app.app.state.queue.get_recipe.return_value = None
        
        response = await test_app.get("/api/v1/recipe/non-existent")
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
