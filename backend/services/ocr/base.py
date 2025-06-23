"""
Base OCR Service Interface
All OCR providers must implement this interface for plug-and-play functionality
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class OCRService(ABC):
    """Base class for all OCR providers (Tesseract, Azure OCR, etc.)"""
    
    name: str = ""
    models: Dict[str, Dict[str, Any]] = {}
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this OCR provider is configured and available"""
        pass
    
    @abstractmethod
    def extract_text(self, image_path: str, model: str, **kwargs) -> Dict[str, Any]:
        """
        Extract text from image using OCR
        
        Args:
            image_path: Path to image file
            model: Model/language to use for OCR
            **kwargs: Additional parameters (preprocessing, confidence, etc.)
            
        Returns:
            {
                "success": bool,
                "text": str,
                "confidence_score": float,
                "model": str,
                "language": str,
                "word_count": int,
                "character_count": int,
                "ocr_data": dict,  # Provider-specific data
                "error": str (if success=False)
            }
        """
        pass
    
    def get_models(self) -> Dict[str, Dict[str, Any]]:
        """Get all models for this provider"""
        if not self.is_available():
            return {}
        return self.models
    
    def get_supported_languages(self) -> Dict[str, str]:
        """Get mapping of language codes to language names"""
        return {} 