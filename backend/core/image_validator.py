"""
Image Validator Module
Handles file validation, format detection, and basic integrity checks
"""
import os
import mimetypes
from pathlib import Path
from typing import Tuple, Optional
from PIL import Image
import magic

class ImageValidator:
    # Supported file formats
    SUPPORTED_FORMATS = {
        'image/jpeg': ['.jpg', '.jpeg'],
        'image/png': ['.png'],
        'image/webp': ['.webp'],
        'application/pdf': ['.pdf']
    }
    
    # Maximum file size (20MB as per OpenAI limits)
    MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB in bytes
    
    def __init__(self):
        self.magic = magic.Magic(mime=True)
    
    def validate_file(self, file_path: str) -> Tuple[bool, Optional[str], Optional[dict]]:
        """
        Validate uploaded file for processing
        
        Returns:
            Tuple of (is_valid, error_message, file_info)
        """
        try:
            file_path = Path(file_path)
            
            # Check if file exists
            if not file_path.exists():
                return False, "File does not exist", None
            
            # Check file size
            file_size = file_path.stat().st_size
            if file_size > self.MAX_FILE_SIZE:
                return False, f"File too large: {file_size / (1024*1024):.1f}MB (max 20MB)", None
            
            if file_size == 0:
                return False, "File is empty", None
            
            # Detect MIME type
            mime_type = self.magic.from_file(str(file_path))
            
            # Check if format is supported
            if mime_type not in self.SUPPORTED_FORMATS:
                return False, f"Unsupported file format: {mime_type}", None
            
            # Additional validation for image files
            file_info = {
                'path': str(file_path),
                'size_bytes': file_size,
                'size_mb': file_size / (1024*1024),
                'mime_type': mime_type,
                'extension': file_path.suffix.lower()
            }
            
            if mime_type.startswith('image/'):
                is_valid, error, image_info = self._validate_image(file_path)
                if not is_valid:
                    return False, error, None
                file_info.update(image_info)
            
            elif mime_type == 'application/pdf':
                is_valid, error, pdf_info = self._validate_pdf(file_path)
                if not is_valid:
                    return False, error, None
                file_info.update(pdf_info)
            
            return True, None, file_info
            
        except Exception as e:
            return False, f"Validation error: {str(e)}", None
    
    def _validate_image(self, file_path: Path) -> Tuple[bool, Optional[str], Optional[dict]]:
        """Validate image-specific properties"""
        try:
            with Image.open(file_path) as img:
                # Check if image can be opened (not corrupted)
                img.verify()
                
            # Reopen for getting info (verify() closes the image)
            with Image.open(file_path) as img:
                width, height = img.size
                format_name = img.format
                mode = img.mode
                
                # Check reasonable dimensions
                if width < 10 or height < 10:
                    return False, "Image dimensions too small (minimum 10x10)", None
                
                if width > 10000 or height > 10000:
                    return False, "Image dimensions too large (maximum 10000x10000)", None
                
                image_info = {
                    'width': width,
                    'height': height,
                    'format': format_name,
                    'mode': mode,
                    'aspect_ratio': width / height
                }
                
                return True, None, image_info
                
        except Exception as e:
            return False, f"Image validation failed: {str(e)}", None
    
    def _validate_pdf(self, file_path: Path) -> Tuple[bool, Optional[str], Optional[dict]]:
        """Validate PDF-specific properties"""
        try:
            # Basic PDF validation - just check if it's a valid PDF
            # More detailed PDF processing will be handled in preprocessor
            with open(file_path, 'rb') as f:
                header = f.read(8)
                if not header.startswith(b'%PDF-'):
                    return False, "Invalid PDF file", None
            
            pdf_info = {
                'type': 'pdf',
                'pages': 'unknown'  # Will be determined during preprocessing
            }
            
            return True, None, pdf_info
            
        except Exception as e:
            return False, f"PDF validation failed: {str(e)}", None
    
    def get_file_info(self, file_path: str) -> Optional[dict]:
        """Get basic file information without full validation"""
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                return None
            
            file_size = file_path.stat().st_size
            mime_type = self.magic.from_file(str(file_path))
            
            return {
                'path': str(file_path),
                'name': file_path.name,
                'size_bytes': file_size,
                'size_mb': file_size / (1024*1024),
                'mime_type': mime_type,
                'extension': file_path.suffix.lower()
            }
        except Exception:
            return None 