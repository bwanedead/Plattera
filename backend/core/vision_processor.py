"""
Vision Processor Module
Handles Vision API integration for image-to-text extraction with configurable models
"""
import base64
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from services.llm_service import get_llm_service
from services.llm_profiles import LLMProfile, ProfileConfig
import io

class VisionProcessor:
    def __init__(self):
        self.llm_service = get_llm_service("openai")
    
    def extract_text_from_image(self, 
                              image_path: str, 
                              extraction_mode: str = "legal_document",
                              model: str = "gpt-4o") -> Tuple[bool, Optional[str], Optional[dict]]:
        """
        Extract text from image using Vision API - SIMPLE TEXT EXTRACTION ONLY
        """
        if not self.llm_service.is_configured():
            return False, "OpenAI client not configured", None
        
        try:
            # Encode image
            image_base64 = self._encode_image_to_base64(image_path)
            if not image_base64:
                return False, "Failed to encode image", None
            
            # Detect image format for API
            image_format = self._detect_image_format(image_path)
            
            # ULTRA-SIMPLE prompts to minimize reasoning overhead
            system_prompt = "Transcribe all text from this image."
            user_prompt = "Transcribe the text."
            
            print(f"DEBUG: Making vision call with model: {model}")
            
            # Make simple vision API call
            success, error, result = self.llm_service.make_vision_call(
                text_prompt=user_prompt,
                image_base64=image_base64,
                profile=LLMProfile.VISION_LEGAL_EXTRACTION,
                system_prompt=system_prompt,
                model=model,
                image_format=image_format
            )
            
            if not success:
                print(f"DEBUG: Vision call failed: {error}")
                return False, f"Text extraction failed: {error}", None
            
            if not result:
                print("DEBUG: Result is None")
                return False, "No response from vision API", None
            
            print(f"DEBUG: Result keys: {result.keys() if result else 'None'}")
            
            # Check if we have the expected keys
            if 'content' not in result:
                print("DEBUG: No 'content' in result")
                return False, "Invalid response format", None
            
            if 'usage' not in result:
                print("DEBUG: No 'usage' in result")
                return False, "Invalid response format - missing usage data", None
            
            # Just return the extracted text - no complex processing
            extracted_text = result['content'] or ""
            
            # Simple result structure with safe access
            extraction_result = {
                'extracted_text': extracted_text,
                'model_used': model,
                'word_count': len(extracted_text.split()) if extracted_text else 0,
                'character_count': len(extracted_text) if extracted_text else 0,
                'tokens_used': result.get('usage', {}).get('total_tokens', 0)
            }
            
            print(f"DEBUG: Extraction successful, text length: {len(extracted_text)}")
            
            return True, None, extraction_result
            
        except Exception as e:
            print(f"DEBUG: Exception in extract_text_from_image: {str(e)}")
            return False, f"Vision processing error: {str(e)}", None
    
    def get_available_models(self) -> Dict[str, Dict[str, Any]]:
        """Get list of available vision models with their capabilities"""
        # Import here to avoid circular imports
        from services.llm_profiles import ProfileConfig
        
        return ProfileConfig.get_supported_models()
    
    def _encode_image_to_base64(self, image_path: str) -> Optional[str]:
        """Encode image file to base64 string"""
        try:
            with open(image_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                return encoded_string
        except Exception:
            return None
    
    def _detect_image_format(self, image_path: str) -> str:
        """Detect image format for API"""
        # This method needs to be implemented to detect the image format
        # For now, we'll use a default format
        return "png"
    
    def test_vision_connection(self, model: str = "gpt-4o") -> Tuple[bool, Optional[str], Optional[dict]]:
        """Test Vision API connection with a specific model"""
        if not self.llm_service.is_configured():
            return False, "OpenAI client not configured", None
        
        try:
            # Create a simple test image (1x1 white pixel)
            from PIL import Image
            
            # Create test image
            test_img = Image.new('RGB', (100, 50), color='white')
            img_buffer = io.BytesIO()
            test_img.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            
            # Encode to base64
            test_image_b64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
            
            # Create custom profile for the test model
            profile_config = ProfileConfig.get_profile_config("openai", LLMProfile.FAST_PROCESSING)
            profile_config["model"] = model
            profile_config["max_tokens"] = 50
            profile_config["temperature"] = 0
            
            # Use the service for the test call
            success, error, result = self.llm_service.make_vision_call(
                text_prompt="What do you see in this image? Respond with 'Vision API working' if you can see the image.",
                image_base64=test_image_b64,
                profile=LLMProfile.FAST_PROCESSING,
                custom_config=profile_config
            )
            
            if not success:
                return False, error, None
            
            test_result = {
                'status': 'success',
                'response': result['content'],
                'model': model,
                'tokens_used': result['usage']['total_tokens']
            }
            
            return True, None, test_result
            
        except Exception as e:
            return False, f"Vision API test failed: {str(e)}", None
    
    def get_supported_extraction_modes(self) -> Dict[str, str]:
        """Get list of supported extraction modes"""
        return {
            "legal_document": "Complete legal document extraction with formatting preservation",
            "property_description_only": "Extract only legal property descriptions and boundaries", 
            "full_ocr": "Complete OCR extraction of all visible text"
        } 