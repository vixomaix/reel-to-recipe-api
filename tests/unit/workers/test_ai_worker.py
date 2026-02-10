"""Unit tests for the AI recipe extractor."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from ai_worker.recipe_extractor import RecipeExtractor


class TestRecipeExtractor:
    """Tests for RecipeExtractor class."""
    
    @pytest.fixture
    def extractor(self, mock_ai_provider):
        """Create a RecipeExtractor instance with mock provider."""
        return RecipeExtractor(mock_ai_provider)
    
    @pytest.mark.asyncio
    async def test_extract_recipe_success(self, extractor, mock_ai_provider, mock_video_data):
        """Test successful recipe extraction."""
        mock_ai_provider.generate_json.return_value = {
            "title": "Test Recipe",
            "description": "A test recipe",
            "ingredients": [
                {"name": "flour", "quantity": "2", "unit": "cups", "optional": False}
            ],
            "instructions": [
                {"step_number": 1, "description": "Mix ingredients"}
            ],
            "confidence_score": 0.95,
        }
        
        result = await extractor.extract_recipe("test-job-123", mock_video_data)
        
        assert result["job_id"] == "test-job-123"
        assert result["title"] == "Test Recipe"
        assert len(result["ingredients"]) == 1
        mock_ai_provider.generate_json.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_extract_recipe_with_timestamps(self, extractor, mock_ai_provider):
        """Test that timestamps are added to instructions."""
        video_data = {
            "duration_seconds": 60,
            "frames": [],
            "transcription": "",
        }
        
        mock_ai_provider.generate_json.return_value = {
            "title": "Timed Recipe",
            "ingredients": [],
            "instructions": [
                {"step_number": 1, "description": "Step 1"},
                {"step_number": 2, "description": "Step 2"},
                {"step_number": 3, "description": "Step 3"},
            ],
        }
        
        result = await extractor.extract_recipe("test", video_data)
        
        # Each step should have estimated timestamps
        for instruction in result["instructions"]:
            assert "timestamp_start" in instruction
            assert "timestamp_end" in instruction
            assert instruction["timestamp_start"] < instruction["timestamp_end"]
    
    @pytest.mark.asyncio
    async def test_extract_recipe_empty_ocr(self, extractor, mock_ai_provider):
        """Test extraction with empty OCR data."""
        video_data = {
            "duration_seconds": 30,
            "frames": [],  # No frames
            "transcription": "Cook for 10 minutes",
        }
        
        mock_ai_provider.generate_json.return_value = {
            "title": "Simple Recipe",
            "ingredients": [],
            "instructions": [{"step_number": 1, "description": "Cook for 10 minutes"}],
        }
        
        result = await extractor.extract_recipe("test", video_data)
        
        assert result["title"] == "Simple Recipe"
        mock_ai_provider.generate_json.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_extract_recipe_ocr_filtering(self, extractor, mock_ai_provider):
        """Test that short OCR text is filtered out."""
        video_data = {
            "duration_seconds": 30,
            "frames": [
                {"timestamp": 1, "ocr_text": "a"},  # Too short, should be filtered
                {"timestamp": 2, "ocr_text": "1 cup flour"},  # Valid
                {"timestamp": 3, "ocr_text": "ok"},  # Too short
            ],
            "transcription": "",
        }
        
        mock_ai_provider.generate_json.return_value = {"title": "Test"}
        
        await extractor.extract_recipe("test", video_data)
        
        # Check that the prompt was built with filtered OCR
        call_args = mock_ai_provider.generate_json.call_args
        user_prompt = call_args[1]["user_prompt"]
        assert "1 cup flour" in user_prompt
        assert "a" not in user_prompt  # Short text filtered
        assert "ok" not in user_prompt  # Short text filtered
    
    def test_build_prompt_structure(self, extractor, mock_video_data):
        """Test that prompts are built with correct structure."""
        prompt = extractor._build_prompt(mock_video_data)
        
        # Should contain sections
        assert "# Video Information" in prompt
        assert "# OCR Text from Video Frames" in prompt
        assert "# Audio Transcription" in prompt
        assert "# Task" in prompt
        
        # Should contain video info
        assert str(mock_video_data["duration_seconds"]) in prompt
        
        # Should contain frame data
        assert "2 cups flour" in prompt
        
        # Should contain transcription
        assert mock_video_data["transcription"] in prompt
    
    def test_add_timestamps(self, extractor):
        """Test timestamp estimation for instructions."""
        video_data = {"duration_seconds": 90}
        recipe = {
            "instructions": [
                {"step_number": 1, "description": "Step 1"},
                {"step_number": 2, "description": "Step 2"},
                {"step_number": 3, "description": "Step 3"},
            ]
        }
        
        result = extractor._add_timestamps(recipe, video_data)
        
        # 90 seconds / 3 steps = 30 seconds per step
        assert result["instructions"][0]["timestamp_start"] == 0
        assert result["instructions"][0]["timestamp_end"] == 30
        assert result["instructions"][1]["timestamp_start"] == 30
        assert result["instructions"][1]["timestamp_end"] == 60
        assert result["instructions"][2]["timestamp_start"] == 60
        assert result["instructions"][2]["timestamp_end"] == 90
    
    def test_fallback_recipe(self, extractor):
        """Test fallback recipe generation."""
        result = extractor._fallback_recipe("job-123", "https://example.com/video")
        
        assert result["job_id"] == "job-123"
        assert "failed" in result["title"].lower()
        assert result["confidence_score"] == 0.0
        assert result["source_url"] == "https://example.com/video"
