"""
OpenAI LLM Provider
Drop this file in services/llm/ and OpenAI models will automatically appear
"""
import os
import base64
from typing import Dict, Any
from .base import LLMService

# Only import if available
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

class OpenAIService(LLMService):
    """OpenAI LLM service provider"""
    
    name = "openai"
    
    models = {
        "gpt-4o": {
            "name": "GPT-4o",
            "provider": "openai",
            "cost_tier": "standard",
            "capabilities": ["vision", "text"],
            "description": "Fast, cost-effective vision model optimized for document OCR",
            "verification_required": False
        },
        "o3": {
            "name": "o3", 
            "provider": "openai",
            "cost_tier": "premium",
            "capabilities": ["vision", "text", "reasoning"],
            "description": "Most advanced reasoning model with highest accuracy",
            "verification_required": True
        },
        "gpt-4": {
            "name": "GPT-4",
            "provider": "openai", 
            "cost_tier": "standard",
            "capabilities": ["text"],
            "description": "High-quality text processing model",
            "verification_required": False
        }
    }
    
    def __init__(self):
        self.client = None
        if self.is_available():
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    def is_available(self) -> bool:
        """Check if OpenAI is available and configured"""
        return OPENAI_AVAILABLE and os.getenv("OPENAI_API_KEY") is not None
    
    def call_text(self, prompt: str, model: str, **kwargs) -> Dict[str, Any]:
        """Make text-only API call to OpenAI"""
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", 0.1),
                max_tokens=kwargs.get("max_tokens", 4000)
            )
            
            return {
                "success": True,
                "text": response.choices[0].message.content,
                "tokens_used": response.usage.total_tokens,
                "model": model
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "text": None,
                "model": model
            }
    
    def call_vision(self, prompt: str, image_data: str, model: str, **kwargs) -> Dict[str, Any]:
        """Make vision API call to OpenAI with image"""
        try:
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_data}",
                                "detail": kwargs.get("detail", "high")
                            }
                        }
                    ]
                }
            ]
            
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=kwargs.get("temperature", 0.1),
                max_tokens=kwargs.get("max_tokens", 4000)
            )
            
            return {
                "success": True,
                "text": response.choices[0].message.content,
                "tokens_used": response.usage.total_tokens,
                "model": model
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "text": None,
                "model": model
            } 