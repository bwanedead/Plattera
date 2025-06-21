"""
Vision Processor Module
Handles o3 Vision API integration for image-to-text extraction
"""
import base64
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from services.llm_service import get_llm_service
from services.llm_profiles import LLMProfile

class VisionProcessor:
    def __init__(self):
        self.llm_service = get_llm_service("openai")
    
    def extract_text_from_image(self, image_path: str, extraction_mode: str = "legal_document") -> Tuple[bool, Optional[str], Optional[dict]]:
        """
        Extract text from image using o3 Vision API
        
        Args:
            image_path: Path to the processed image
            extraction_mode: Type of extraction to perform
        
        Returns:
            Tuple of (success, error_message, extraction_result)
        """
        if not self.llm_service.is_configured():
            return False, "OpenAI client not configured", None
        
        try:
            # Encode image to base64
            image_base64 = self._encode_image_to_base64(image_path)
            if not image_base64:
                return False, "Failed to encode image", None
            
            # Get appropriate prompt for extraction mode
            system_prompt, user_prompt = self._get_prompts(extraction_mode)
            
            # Make vision API call using the service
            success, error, result = self.llm_service.make_vision_call(
                text_prompt=user_prompt,
                image_base64=image_base64,
                profile=LLMProfile.VISION_LEGAL_EXTRACTION,
                system_prompt=system_prompt
            )
            
            if not success:
                return False, error, None
            
            # Extract response data
            extracted_text = result['content']
            usage_info = result['usage']
            
            extraction_result = {
                'extracted_text': extracted_text,
                'extraction_mode': extraction_mode,
                'confidence': self._estimate_confidence(extracted_text),
                'usage': usage_info,
                'word_count': len(extracted_text.split()) if extracted_text else 0,
                'character_count': len(extracted_text) if extracted_text else 0
            }
            
            return True, None, extraction_result
            
        except Exception as e:
            return False, f"Vision API error: {str(e)}", None
    
    def _encode_image_to_base64(self, image_path: str) -> Optional[str]:
        """Encode image file to base64 string"""
        try:
            with open(image_path, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                return encoded_string
        except Exception:
            return None
    
    def _get_prompts(self, extraction_mode: str) -> Tuple[str, str]:
        """Get appropriate prompts based on extraction mode"""
        
        if extraction_mode == "legal_document":
            system_prompt = """You are an expert legal document text extraction specialist. Your task is to extract ALL text from legal property documents with perfect accuracy and formatting preservation.

Key requirements:
1. Extract EVERY word, number, and punctuation mark exactly as shown
2. Preserve the original formatting, line breaks, and paragraph structure
3. Include ALL legal descriptions, measurements, bearings, and technical details
4. Maintain proper spacing and indentation
5. Do not summarize, interpret, or modify any text
6. If text is unclear, mark it as [UNCLEAR: best_guess] but still include your best reading
7. Include headers, footers, page numbers, and any marginal notes
8. Preserve special characters, fractions, and symbols exactly as shown"""

            user_prompt = """Please extract ALL text from this legal document image. 

Extract everything you see - every word, number, punctuation mark, and formatting detail. This is a legal property document where accuracy is critical.

Return only the extracted text with original formatting preserved. Do not add any commentary or explanations."""
        
        elif extraction_mode == "property_description_only":
            system_prompt = """You are a specialist in extracting legal property descriptions from documents. Focus specifically on the legal description portions that describe property boundaries, measurements, and locations."""

            user_prompt = """Extract ONLY the legal property description portions from this document. Look for:
- Property boundary descriptions
- Measurements and distances 
- Bearings and directions
- Township, range, and section references
- "Beginning at..." and similar legal description language

Ignore headers, signatures, witness information, and other non-property-description content. Return only the legal description text with original formatting preserved."""
        
        elif extraction_mode == "full_ocr":
            system_prompt = """You are a high-accuracy OCR system. Extract ALL visible text from the image exactly as it appears."""

            user_prompt = """Perform complete OCR extraction of all text visible in this image. Extract everything exactly as shown, preserving formatting and structure."""
        
        else:  # Default to legal_document
            return self._get_prompts("legal_document")
        
        return system_prompt, user_prompt
    
    def _estimate_confidence(self, extracted_text: str) -> float:
        """Estimate confidence level based on extracted text characteristics"""
        if not extracted_text:
            return 0.0
        
        confidence = 0.8  # Base confidence
        
        # Increase confidence for legal document indicators
        legal_indicators = [
            "beginning at", "thence", "township", "range", "section",
            "feet", "degrees", "minutes", "north", "south", "east", "west",
            "bearing", "distance", "boundary", "parcel", "lot", "block"
        ]
        
        text_lower = extracted_text.lower()
        matches = sum(1 for indicator in legal_indicators if indicator in text_lower)
        
        # Boost confidence based on legal terminology
        confidence += min(matches * 0.02, 0.15)
        
        # Reduce confidence for very short extractions
        if len(extracted_text) < 50:
            confidence -= 0.2
        
        # Reduce confidence if many [UNCLEAR] markers
        unclear_count = extracted_text.count('[UNCLEAR')
        confidence -= min(unclear_count * 0.1, 0.3)
        
        return max(0.1, min(1.0, confidence))
    
    def test_vision_connection(self) -> Tuple[bool, Optional[str], Optional[dict]]:
        """Test o3 Vision API connection with a simple request"""
        if not self.llm_service.is_configured():
            return False, "OpenAI client not configured", None
        
        try:
            # Create a simple test image (1x1 white pixel)
            import io
            from PIL import Image
            
            # Create test image
            test_img = Image.new('RGB', (100, 50), color='white')
            img_buffer = io.BytesIO()
            test_img.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            
            # Encode to base64
            test_image_b64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
            
            # Use the service for the test call
            success, error, result = self.llm_service.make_vision_call(
                text_prompt="What do you see in this image? Respond with 'Vision API working' if you can see the image.",
                image_base64=test_image_b64,
                profile=LLMProfile.FAST_PROCESSING,  # Use fast processing for test
                max_tokens=50,
                temperature=0
            )
            
            if not success:
                return False, error, None
            
            test_result = {
                'status': 'success',
                'response': result['content'],
                'model': result['usage']['model'] if 'model' in result['usage'] else result.get('model', 'o3'),
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