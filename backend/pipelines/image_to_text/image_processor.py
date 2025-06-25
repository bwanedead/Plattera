"""
Image Processing for Better Character Recognition
Focused on enhancing images for better OCR/LLM text extraction

CRITICAL WIRING DOCUMENTATION:
==============================

🔴 THIS MODULE IS PART OF A CRITICAL CHAIN - PRESERVE ALL WIRING BELOW 🔴

DATA FLOW CHAIN:
1. API Endpoint receives image file
2. Pipeline calls enhance_for_character_recognition() 
3. Returns (base64_encoded_image, image_format) tuple
4. Pipeline passes this to OpenAI service
5. OpenAI service expects base64 string for vision API
6. Text extraction happens and flows back through chain

CRITICAL RETURN FORMAT:
- MUST return tuple: (base64_string, format_string)
- base64_string MUST be clean base64 without data URI prefix
- format_string MUST be valid image format (jpeg, png, etc.)
- OpenAI service expects exactly this format for image_data parameter

CRITICAL WIRING POINTS:
- Pipeline calls: enhance_for_character_recognition(str(image_path))
- OpenAI service expects: image_data as base64 string
- Response flows: base64 → OpenAI → extracted_text → API response

ENHANCEMENT SAFETY RULES:
- NEVER change the return signature: Tuple[str, str]
- NEVER add data URI prefix to base64 string
- ALWAYS have fallback to original image if enhancement fails
- ALWAYS return valid base64 string
- ALWAYS return valid image format string

FUTURE ENHANCEMENT GUIDELINES:
- Add parameters to function signature, not return signature
- Preserve base64 encoding flow
- Test with OpenAI service integration
- Maintain fallback behavior
"""
from PIL import Image, ImageEnhance, ImageFilter
import io
import base64
from pathlib import Path
from typing import Tuple, Optional

def enhance_for_character_recognition(
    image_path: str,
    contrast: float = 1.3,
    sharpness: float = 1.2,
    brightness: float = 1.0,
    color: float = 1.0
) -> Tuple[str, str]:
    """
    Enhance image specifically for better character recognition
    Focus on contrast and sharpness to help distinguish ambiguous characters
    
    🔴 CRITICAL WIRING: DO NOT MODIFY RETURN SIGNATURE 🔴
    
    Args:
        image_path: Path to the original image
        contrast: Contrast enhancement factor (1.0 = no change, >1.0 = more contrast)
        sharpness: Sharpness enhancement factor (1.0 = no change, >1.0 = sharper)
        brightness: Brightness enhancement factor (1.0 = no change, >1.0 = brighter)
        color: Color saturation factor (1.0 = no change, >1.0 = more saturated)
        
    Returns:
        Tuple[str, str]: (base64_encoded_image, image_format)
        - base64_encoded_image: Clean base64 string (NO data URI prefix)
        - image_format: Image format string (jpeg, png, etc.)
    
    CRITICAL CHAIN POSITION:
    - Called by: pipeline._prepare_image()
    - Used by: OpenAI service call_vision() method
    - OpenAI expects: base64 string as image_data parameter
    """
    try:
        # CRITICAL: Load image and validate
        with Image.open(image_path) as img:
            # CRITICAL: Ensure RGB mode for consistent processing
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # CONFIGURABLE ENHANCEMENT VALUES - RESPECTING USER SETTINGS
            # Default values provide optimal character recognition improvement
            # without degrading image quality for OpenAI vision API
            
            # Apply brightness adjustment first (affects overall exposure)
            if brightness != 1.0:
                brightness_enhancer = ImageEnhance.Brightness(img)
                img = brightness_enhancer.enhance(brightness)
            
            # Apply contrast boost to help character disambiguation
            if contrast != 1.0:
                contrast_enhancer = ImageEnhance.Contrast(img)
                img = contrast_enhancer.enhance(contrast)
            
            # Apply color saturation adjustment
            if color != 1.0:
                color_enhancer = ImageEnhance.Color(img)
                img = color_enhancer.enhance(color)
            
            # Apply sharpness increase for character edges (do this last)
            if sharpness != 1.0:
                sharpness_enhancer = ImageEnhance.Sharpness(img)
                img = sharpness_enhancer.enhance(sharpness)
            
            # CRITICAL: Save as high-quality JPEG for OpenAI compatibility
            # OpenAI vision API works best with JPEG format
            # Quality 95 ensures minimal compression artifacts
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=95, optimize=True)
            img_byte_arr.seek(0)
            
            # CRITICAL: Return clean base64 string - NO data URI prefix
            # OpenAI service adds its own data URI prefix in call_vision()
            base64_encoded = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
            
            # CRITICAL: Return tuple format expected by pipeline
            return base64_encoded, 'jpeg'
            
    except Exception as e:
        # CRITICAL: Fallback to original image if enhancement fails
        # This ensures the pipeline never fails due to enhancement errors
        # Maintains system reliability while attempting improvements
        with open(image_path, "rb") as image_file:
            image_data = base64.b64encode(image_file.read()).decode('utf-8')
            # CRITICAL: Return same tuple format even in fallback
            return image_data, 'jpeg' 