"""
Base LLM Service Interface
All LLM providers must implement this interface for plug-and-play functionality
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class LLMService(ABC):
    """Base class for all LLM providers (OpenAI, Anthropic, etc.)"""
    
    name: str = ""
    models: Dict[str, Dict[str, Any]] = {}
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this LLM provider is configured and available"""
        pass
    
    @abstractmethod
    def call_text(self, prompt: str, model: str, **kwargs) -> Dict[str, Any]:
        """
        Make a text-only API call
        
        Args:
            prompt: Text prompt to send
            model: Model name to use
            **kwargs: Additional parameters (temperature, max_tokens, etc.)
            
        Returns:
            {
                "success": bool,
                "text": str,
                "tokens_used": int,
                "model": str,
                "error": str (if success=False)
            }
        """
        pass
    
    @abstractmethod
    def call_vision(self, prompt: str, image_data: str, model: str, **kwargs) -> Dict[str, Any]:
        """
        Make a vision API call with image
        
        Args:
            prompt: Text prompt to send
            image_data: Base64 encoded image data
            model: Model name to use
            **kwargs: Additional parameters
            
        Returns:
            {
                "success": bool,
                "text": str,
                "tokens_used": int,
                "model": str,
                "error": str (if success=False)
            }
        """
        pass
    
    def get_models(self) -> Dict[str, Dict[str, Any]]:
        """Get all models for this provider"""
        if not self.is_available():
            return {}
        return self.models
    
    def supports_vision(self, model: str) -> bool:
        """Check if a model supports vision capabilities"""
        model_info = self.models.get(model, {})
        capabilities = model_info.get("capabilities", [])
        return "vision" in capabilities 