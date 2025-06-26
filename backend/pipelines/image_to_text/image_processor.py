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
import logging

logger = logging.getLogger(__name__)

def enhance_for_character_recognition(
    image_path: str,
    contrast: float = 2.0,
    sharpness: float = 2.0,
    brightness: float = 1.5,
    color: float = 1.0
) -> Tuple[str, str]:
    """Enhanced with bulletproof error handling"""
    
    # Validate and clamp parameters
    contrast = max(0.1, min(5.0, float(contrast)))
    sharpness = max(0.1, min(5.0, float(sharpness)))
    brightness = max(0.1, min(3.0, float(brightness)))
    color = max(0.0, min(3.0, float(color)))
    
    try:
        # Validate image path exists and is readable
        if not Path(image_path).exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")
        
        # CRITICAL: Load image with explicit error handling
        with Image.open(image_path) as img:
            # CRITICAL: Ensure RGB mode for consistent processing
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Validate image isn't corrupted
            img.verify()
            
            # Reload image after verify (verify() can't be undone)
            with Image.open(image_path) as img:
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Apply enhancements with individual error handling
                try:
                    if brightness != 1.0:
                        brightness_enhancer = ImageEnhance.Brightness(img)
                        img = brightness_enhancer.enhance(brightness)
                except Exception as e:
                    logger.warning(f"Brightness enhancement failed: {e}")
                
                try:
                    if contrast != 1.0:
                        contrast_enhancer = ImageEnhance.Contrast(img)
                        img = contrast_enhancer.enhance(contrast)
                except Exception as e:
                    logger.warning(f"Contrast enhancement failed: {e}")
                
                try:
                    if color != 1.0:
                        color_enhancer = ImageEnhance.Color(img)
                        img = color_enhancer.enhance(color)
                except Exception as e:
                    logger.warning(f"Color enhancement failed: {e}")
                
                try:
                    if sharpness != 1.0:
                        sharpness_enhancer = ImageEnhance.Sharpness(img)
                        img = sharpness_enhancer.enhance(sharpness)
                except Exception as e:
                    logger.warning(f"Sharpness enhancement failed: {e}")
                
                # CRITICAL: Save with multiple format fallbacks
                img_byte_arr = io.BytesIO()
                
                # Try JPEG first (preferred by OpenAI)
                try:
                    img.save(img_byte_arr, format='JPEG', quality=95, optimize=True)
                    format_used = 'jpeg'
                except Exception:
                    # Fallback to PNG if JPEG fails
                    img_byte_arr = io.BytesIO()
                    img.save(img_byte_arr, format='PNG', optimize=True)
                    format_used = 'png'
                
                img_byte_arr.seek(0)
                
                # CRITICAL: Return clean base64 string
                base64_encoded = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
                
                # Validate base64 is not empty
                if not base64_encoded:
                    raise ValueError("Base64 encoding resulted in empty string")
                
                return base64_encoded, format_used
                
    except Exception as e:
        logger.error(f"Enhancement failed, using original image: {e}")
        # CRITICAL: Bulletproof fallback to original image
        try:
            with open(image_path, "rb") as image_file:
                image_data = base64.b64encode(image_file.read()).decode('utf-8')
                if not image_data:
                    raise ValueError("Original image encoding failed")
                return image_data, 'jpeg'
        except Exception as fallback_error:
            logger.error(f"Fallback also failed: {fallback_error}")
            raise RuntimeError(f"Complete image processing failure: {e}, fallback: {fallback_error}") 