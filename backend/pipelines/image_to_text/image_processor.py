"""
Image Processing for Better Character Recognition
Focused on enhancing images for better OCR/LLM text extraction
"""
from PIL import Image, ImageEnhance, ImageFilter
import io
import base64
from pathlib import Path
from typing import Tuple

def enhance_for_character_recognition(image_path: str) -> Tuple[str, str]:
    """
    Enhance image specifically for better character recognition
    Focus on contrast and sharpness to help distinguish ambiguous characters
    
    Args:
        image_path: Path to the original image
        
    Returns:
        (base64_encoded_image, image_format)
    """
    try:
        with Image.open(image_path) as img:
            # Convert to RGB if needed
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Moderate contrast boost to help character disambiguation
            contrast_enhancer = ImageEnhance.Contrast(img)
            img = contrast_enhancer.enhance(1.3)  # 30% contrast increase
            
            # Slight sharpness increase for character edges
            sharpness_enhancer = ImageEnhance.Sharpness(img)
            img = sharpness_enhancer.enhance(1.2)  # 20% sharpness increase
            
            # Save as high-quality JPEG
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='JPEG', quality=95, optimize=True)
            img_byte_arr.seek(0)
            
            # Return base64 and format
            base64_encoded = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
            return base64_encoded, 'jpeg'
            
    except Exception as e:
        # Fallback to original if enhancement fails
        with open(image_path, "rb") as image_file:
            image_data = base64.b64encode(image_file.read()).decode('utf-8')
            return image_data, 'jpeg' 