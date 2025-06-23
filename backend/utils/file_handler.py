"""
File Handling Utilities
Simple, clean file operations for uploads and temp files
"""
import os
import tempfile
import base64
from pathlib import Path
from typing import Tuple, Optional

def save_uploaded_file(file_content: bytes, filename: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Save uploaded file to temporary location
    
    Args:
        file_content: File content as bytes
        filename: Original filename
        
    Returns:
        (success, error_message, temp_file_path)
    """
    try:
        # Get file extension
        file_ext = Path(filename).suffix.lower()
        
        # Create temporary file with proper extension
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
            temp_file.write(file_content)
            temp_path = temp_file.name
        
        return True, None, temp_path
        
    except Exception as e:
        return False, f"Failed to save file: {str(e)}", None

def cleanup_temp_file(file_path: str) -> None:
    """
    Clean up temporary file
    
    Args:
        file_path: Path to temporary file
    """
    try:
        if file_path and os.path.exists(file_path):
            os.unlink(file_path)
    except Exception:
        pass  # Fail silently for cleanup

def encode_image_to_base64(image_path: str) -> Optional[str]:
    """
    Encode image file to base64 string
    
    Args:
        image_path: Path to image file
        
    Returns:
        Base64 encoded string or None if failed
    """
    try:
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            return encoded_string
    except Exception:
        return None

def is_valid_image_file(filename: str) -> bool:
    """
    Check if filename has valid image extension
    
    Args:
        filename: Filename to check
        
    Returns:
        True if valid image file
    """
    valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}
    file_ext = Path(filename).suffix.lower()
    return file_ext in valid_extensions 