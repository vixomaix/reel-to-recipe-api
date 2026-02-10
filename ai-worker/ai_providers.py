"""AI Provider implementations for recipe extraction."""
import os
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional


class AIProvider(ABC):
    """Abstract base class for AI providers."""
    
    @abstractmethod
    async def generate_completion(
        self, 
        system_prompt: str, 
        user_prompt: str,
        temperature: float = 0.3
    ) -> str:
        """Generate completion from AI provider."""
        pass
    
    @abstractmethod
    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3
    ) -> Dict[str, Any]:
        """Generate JSON response from AI provider."""
        pass


class OpenAIProvider(AIProvider):
    """OpenAI API provider."""
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        import openai
        
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o")
        self.client = openai.AsyncOpenAI(api_key=self.api_key)
    
    async def generate_completion(
        self, 
        system_prompt: str, 
        user_prompt: str,
        temperature: float = 0.3
    ) -> str:
        """Generate completion using OpenAI."""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temperature,
            max_tokens=4000,
        )
        return response.choices[0].message.content
    
    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3
    ) -> Dict[str, Any]:
        """Generate JSON response using OpenAI."""
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temperature,
            max_tokens=4000,
            response_format={"type": "json_object"}
        )
        import json
        return json.loads(response.choices[0].message.content)


class AnthropicProvider(AIProvider):
    """Anthropic Claude API provider."""
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        import anthropic
        
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model or os.getenv("ANTHROPIC_MODEL", "claude-3-opus-20240229")
        self.client = anthropic.AsyncAnthropic(api_key=self.api_key)
    
    async def generate_completion(
        self, 
        system_prompt: str, 
        user_prompt: str,
        temperature: float = 0.3
    ) -> str:
        """Generate completion using Anthropic Claude."""
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=4000,
            temperature=temperature,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ]
        )
        return response.content[0].text
    
    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3
    ) -> Dict[str, Any]:
        """Generate JSON response using Anthropic Claude."""
        json_prompt = f"""{user_prompt}

You must respond with valid JSON only. Do not include any other text."""
        
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=4000,
            temperature=temperature,
            system=system_prompt,
            messages=[
                {"role": "user", "content": json_prompt}
            ]
        )
        
        import json
        content = response.content[0].text
        
        # Try to extract JSON if wrapped in markdown
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        return json.loads(content)