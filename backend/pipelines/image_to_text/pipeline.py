"""
Image to Text Processing Pipeline
Pure business logic - no API endpoints
"""
from services.registry import get_registry
from prompts.image_to_text import get_image_to_text_prompt
import base64
from pathlib import Path
import logging
from typing import Tuple
from .image_processor import enhance_for_character_recognition

logger = logging.getLogger(__name__)

class ImageToTextPipeline:
    """
    Clean, decoupled pipeline for image-to-text processing
    """
    
    def __init__(self):
        self.registry = get_registry()
    
    def process(self, image_path: str, model: str = "gpt-4o", extraction_mode: str = "legal_document") -> dict:
        """
        Process an image to extract text
        
        Args:
            image_path: Path to the image file
            model: Model identifier to use for processing
            extraction_mode: Mode of extraction (legal_document, simple_ocr, etc.)
            
        Returns:
            dict: Processing result with extracted text and metadata
        """
        try:
            # Get the appropriate service for this model
            service = self._get_service_for_model(model)
            if not service:
                return {
                    "success": False,
                    "error": f"No service available for model: {model}"
                }
            
            # Prepare the enhanced image
            image_data, image_format = self._prepare_image(image_path)
            if not image_data:
                return {
                    "success": False,
                    "error": "Failed to prepare image data"
                }
            
            # Get the prompt for this extraction mode and model
            prompt = get_image_to_text_prompt(extraction_mode, model)
            
            # Process based on service type
            if hasattr(service, 'process_image_with_text'):
                # LLM service
                result = service.process_image_with_text(
                    image_data=image_data,
                    prompt=prompt,
                    model=model,
                    image_format=image_format
                )
            elif hasattr(service, 'extract_text'):
                # OCR service
                result = service.extract_text(image_path, model)
            else:
                return {
                    "success": False,
                    "error": f"Service {service.__class__.__name__} doesn't support image processing"
                }
            
            # Standardize the response
            return self._standardize_response(result, model, service)
            
        except Exception as e:
            logger.error(f"Pipeline processing failed: {str(e)}")
            return {
                "success": False,
                "error": f"Processing failed: {str(e)}"
            }
    
    def _get_service_for_model(self, model: str):
        """Find the appropriate service for a given model"""
        all_models = self.registry.get_all_models()
        
        if model not in all_models:
            return None
            
        model_info = all_models[model]
        service_type = model_info.get("service_type")
        service_name = model_info.get("service_name")
        
        if service_type == "llm":
            return self.registry.llm_services.get(service_name)
        elif service_type == "ocr":
            return self.registry.ocr_services.get(service_name)
        
        return None
    
    def _prepare_image(self, image_path: str) -> Tuple[str, str]:
        """Prepare and enhance image data for processing"""
        try:
            image_path = Path(image_path)
            if not image_path.exists():
                return None, None
                
            # Use enhanced processing for better character recognition
            enhanced_image_data, image_format = enhance_for_character_recognition(str(image_path))
            return enhanced_image_data, image_format
            
        except Exception as e:
            logger.error(f"Failed to prepare image: {str(e)}")
            return None, None
    
    def _standardize_response(self, result: dict, model: str, service) -> dict:
        """Standardize response format across different services"""
        if not result.get("success", False):
            return result
            
        # Add consistent metadata
        return {
            "success": True,
            "extracted_text": result.get("extracted_text", ""),
            "model_used": model,
            "service_type": "llm" if hasattr(service, 'process_image_with_text') else "ocr",
            "service_name": service.__class__.__name__.lower().replace('service', ''),
            "tokens_used": result.get("tokens_used"),
            "confidence_score": result.get("confidence_score"),
            "metadata": {
                "processing_time": result.get("processing_time"),
                "image_dimensions": result.get("image_dimensions"),
                "file_size": result.get("file_size"),
                **result.get("metadata", {})
            }
        }
    
    def get_available_models(self) -> dict:
        """Get models available for image-to-text processing"""
        all_models = self.registry.get_all_models()
        
        # Filter for models that can process images
        image_models = {}
        for model_id, model_info in all_models.items():
            if model_info.get("capabilities", {}).get("image_processing", False):
                image_models[model_id] = model_info
                
        return image_models
    
    def get_extraction_modes(self) -> dict:
        """Get available extraction modes"""
        return {
            "legal_document": "Optimized for legal documents and contracts",
            "simple_ocr": "Simple text extraction with minimal processing",
            "handwritten": "Specialized for handwritten text recognition",
            "property_deed": "Optimized for property deeds and real estate documents",
            "table_extraction": "Extract structured data from tables"
        } 