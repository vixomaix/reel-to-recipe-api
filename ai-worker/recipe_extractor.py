"""Recipe extraction logic using AI providers."""
import json
from typing import Any, Dict, List, Optional

from ai_providers import AIProvider


class RecipeExtractor:
    """Extracts recipes from video data using AI."""
    
    SYSTEM_PROMPT = """You are an expert recipe extraction AI. Your task is to analyze video content data and extract a complete, well-structured recipe.

You will receive:
1. OCR text extracted from video frames (may include ingredient lists, instructions shown on screen)
2. Audio transcription (spoken instructions and commentary)
3. Video metadata (duration, etc.)

Your goal is to create a complete recipe with:
- A clear, descriptive title
- A list of ingredients with quantities and units
- Step-by-step instructions
- Cooking/prep times if mentioned
- Serving size if mentioned
- Tags for categorization

Respond in valid JSON format matching the Recipe schema."""

    JSON_SCHEMA = """
{
  "title": "Recipe Title",
  "description": "Brief description of the dish",
  "ingredients": [
    {
      "name": "ingredient name",
      "quantity": "amount (e.g., 2, 1/2, 3-4)",
      "unit": "unit (e.g., cups, tbsp, oz, pieces)",
      "optional": false,
      "notes": "any special notes"
    }
  ],
  "instructions": [
    {
      "step_number": 1,
      "description": "Detailed instruction text",
      "timestamp_start": null,
      "timestamp_end": null
    }
  ],
  "cook_time_minutes": null,
  "prep_time_minutes": null,
  "servings": null,
  "difficulty": "easy|medium|hard",
  "tags": ["tag1", "tag2"],
  "confidence_score": 0.95
}
"""
    
    def __init__(self, ai_provider: AIProvider):
        self.ai_provider = ai_provider
    
    async def extract_recipe(self, job_id: str, video_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract recipe from video data."""
        # Build prompt from video data
        user_prompt = self._build_prompt(video_data)
        
        # Get recipe from AI
        recipe_data = await self.ai_provider.generate_json(
            system_prompt=self.SYSTEM_PROMPT + "\n\nJSON Schema:\n" + self.JSON_SCHEMA,
            user_prompt=user_prompt,
            temperature=0.3
        )
        
        # Add job_id and source_url
        recipe_data["job_id"] = job_id
        recipe_data["source_url"] = video_data.get("source_url", "")
        
        # Ensure required fields
        if "ingredients" not in recipe_data:
            recipe_data["ingredients"] = []
        if "instructions" not in recipe_data:
            recipe_data["instructions"] = []
        
        # Add timestamps to instructions if available
        recipe_data = self._add_timestamps(recipe_data, video_data)
        
        return recipe_data
    
    def _build_prompt(self, video_data: Dict[str, Any]) -> str:
        """Build the extraction prompt from video data."""
        parts = []
        
        # Add video metadata
        parts.append("# Video Information")
        parts.append(f"Duration: {video_data.get('duration_seconds', 'Unknown')} seconds")
        if video_data.get('resolution'):
            res = video_data['resolution']
            parts.append(f"Resolution: {res.get('width')}x{res.get('height')}")
        parts.append("")
        
        # Add OCR text from frames
        parts.append("# OCR Text from Video Frames")
        frames = video_data.get('frames', [])
        ocr_texts = []
        
        for frame in frames:
            if frame.get('ocr_text'):
                timestamp = frame.get('timestamp', 0)
                text = frame['ocr_text'].strip()
                if text and len(text) > 3:  # Filter out very short text
                    ocr_texts.append(f"[{timestamp}s] {text}")
        
        if ocr_texts:
            parts.extend(ocr_texts[:50])  # Limit to 50 frames
        else:
            parts.append("(No text detected in frames)")
        parts.append("")
        
        # Add audio transcription
        parts.append("# Audio Transcription")
        transcription = video_data.get('transcription', '').strip()
        if transcription:
            parts.append(transcription[:5000])  # Limit length
        else:
            parts.append("(No audio transcription available)")
        
        parts.append("")
        parts.append("# Task")
        parts.append("Extract a complete recipe from the above information. Return valid JSON.")
        
        return "\n".join(parts)
    
    def _add_timestamps(
        self, 
        recipe: Dict[str, Any], 
        video_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Add video timestamps to recipe instructions if possible."""
        frames = video_data.get('frames', [])
        instructions = recipe.get('instructions', [])
        
        if not frames or not instructions:
            return recipe
        
        duration = video_data.get('duration_seconds', 0)
        if duration <= 0:
            return recipe
        
        # Estimate timestamp for each step based on instruction count
        step_duration = duration / max(len(instructions), 1)
        
        for i, instruction in enumerate(instructions):
            step_number = instruction.get('step_number', i + 1)
            start_time = (step_number - 1) * step_duration
            end_time = step_number * step_duration
            
            instruction['timestamp_start'] = round(start_time, 2)
            instruction['timestamp_end'] = round(end_time, 2)
        
        return recipe
    
    def _fallback_recipe(self, job_id: str, url: str) -> Dict[str, Any]:
        """Create a fallback recipe when extraction fails."""
        return {
            "job_id": job_id,
            "title": "Recipe Extraction Failed",
            "description": "Could not extract recipe from this video. The video may not contain a recipe or the content was not recognizable.",
            "ingredients": [],
            "instructions": [],
            "source_url": url,
            "confidence_score": 0.0,
            "tags": ["extraction-failed"],
        }