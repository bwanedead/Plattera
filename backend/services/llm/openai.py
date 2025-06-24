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
        "gpt-o4-mini": {
            "name": "GPT-o4-mini",
            "provider": "openai",
            "cost_tier": "budget",
            "capabilities": ["vision", "text"],
            "description": "Lightweight, fast, and cost-effective model for simple vision tasks",
            "verification_required": False,
            "api_model_name": "o4-mini-2025-04-16"
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
    
    def _get_api_model_name(self, model: str) -> str:
        """Get the actual API model name (some models have different display vs API names)"""
        model_info = self.models.get(model, {})
        return model_info.get("api_model_name", model)
    
    def call_text(self, prompt: str, model: str, **kwargs) -> Dict[str, Any]:
        """Make text-only API call to OpenAI"""
        try:
            api_model_name = self._get_api_model_name(model)
            
            # Build parameters based on model type
            completion_params = {
                "model": api_model_name,
                "messages": [{"role": "user", "content": prompt}]
            }
            
            # o4-mini has specific parameter requirements
            if "o4-mini" in api_model_name:
                # o4-mini only supports default temperature (1), so don't include it
                completion_params["max_completion_tokens"] = kwargs.get("max_tokens", 4000)
                # Set reasoning effort to high for maximum accuracy
                completion_params["reasoning_effort"] = "high"
            else:
                # Other models use standard parameters
                completion_params["temperature"] = kwargs.get("temperature", 0.1)
                completion_params["max_tokens"] = kwargs.get("max_tokens", 4000)
            
            response = self.client.chat.completions.create(**completion_params)
            
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
            api_model_name = self._get_api_model_name(model)
            
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
            
            # Build parameters based on model type
            completion_params = {
                "model": api_model_name,
                "messages": messages
            }
            
            # o4-mini has specific parameter requirements
            if "o4-mini" in api_model_name:
                # o4-mini only supports default temperature (1), so don't include it
                completion_params["max_completion_tokens"] = kwargs.get("max_tokens", 4000)
                # Set reasoning effort to high for maximum accuracy
                completion_params["reasoning_effort"] = "high"
            else:
                # Other models use standard parameters
                completion_params["temperature"] = kwargs.get("temperature", 0.1)
                completion_params["max_tokens"] = kwargs.get("max_tokens", 4000)
            
            response = self.client.chat.completions.create(**completion_params)
            
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
    
    def process_image_with_text(self, image_data: str, prompt: str, model: str, **kwargs) -> Dict[str, Any]:
        """
        Process image with text prompt (wrapper around call_vision for pipeline compatibility)
        
        Args:
            image_data: Base64 encoded image data
            prompt: Text prompt for processing
            model: Model to use
            **kwargs: Additional parameters
        
        Returns:
            Standardized response format for pipelines
        """
        result = self.call_vision(prompt, image_data, model, **kwargs)
        
        # Convert to pipeline-expected format
        if result.get("success"):
            return {
                "success": True,
                "extracted_text": result.get("text", ""),
                "tokens_used": result.get("tokens_used"),
                "model_used": result.get("model"),
                "service_type": "llm",
                "confidence_score": 1.0,  # OpenAI doesn't provide confidence scores
                "metadata": {
                    "provider": "openai",
                    **kwargs
                }
            }
        else:
            return result 