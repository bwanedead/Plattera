"""
Image Preprocessor Module
Handles image resizing, format conversion, and optimization for o3 Vision API
"""
import os
from pathlib import Path
from typing import Tuple, Optional, Dict, Any
from PIL import Image, ImageEnhance, ImageFilter
import uuid

class ImagePreprocessor:
    # Optimal settings for o3 Vision API
    MAX_DIMENSION = 1024  # Cost-optimized max dimension
    TARGET_FORMAT = 'PNG'  # Best for text extraction
    QUALITY_SETTINGS = {
        'dpi': (300, 300),  # High DPI for text clarity
        'optimize': True
    }
    
    def __init__(self, processed_dir: str = "uploads/processed"):
        self.processed_dir = Path(processed_dir)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
    
    def preprocess_image(self, input_path: str, file_info: dict) -> Tuple[bool, Optional[str], Optional[dict]]:
        """
        Preprocess image for optimal o3 Vision API processing
        
        Args:
            input_path: Path to the original image
            file_info: File information from validator
        
        Returns:
            Tuple of (success, error_message, processed_info)
        """
        try:
            input_path = Path(input_path)
            
            # Generate unique filename for processed image
            unique_id = str(uuid.uuid4())[:8]
            output_filename = f"{unique_id}_{input_path.stem}.png"
            output_path = self.processed_dir / output_filename
            
            # Handle different input formats
            if file_info['mime_type'] == 'application/pdf':
                success, error, processed_info = self._process_pdf(input_path, output_path, file_info)
            else:
                success, error, processed_info = self._process_image(input_path, output_path, file_info)
            
            if success:
                processed_info.update({
                    'processed_path': str(output_path),
                    'unique_id': unique_id,
                    'ready_for_api': True
                })
            
            return success, error, processed_info
            
        except Exception as e:
            return False, f"Preprocessing error: {str(e)}", None
    
    def _process_image(self, input_path: Path, output_path: Path, file_info: dict) -> Tuple[bool, Optional[str], Optional[dict]]:
        """Process regular image files"""
        try:
            with Image.open(input_path) as img:
                # Convert to RGB if necessary (for PNG output)
                if img.mode in ('RGBA', 'LA', 'P'):
                    # Preserve transparency by creating white background
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Get original dimensions
                original_width, original_height = img.size
                
                # Calculate optimal dimensions
                new_width, new_height = self._calculate_optimal_size(original_width, original_height)
                
                # Resize if necessary
                if (new_width, new_height) != (original_width, original_height):
                    # Use high-quality resampling for text preservation
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Enhance for text extraction
                img = self._enhance_for_text(img)
                
                # Save optimized image
                img.save(
                    output_path, 
                    format='PNG',
                    dpi=self.QUALITY_SETTINGS['dpi'],
                    optimize=self.QUALITY_SETTINGS['optimize']
                )
                
                processed_info = {
                    'original_dimensions': (original_width, original_height),
                    'processed_dimensions': (new_width, new_height),
                    'format': 'PNG',
                    'optimization': 'text_enhanced',
                    'file_size_mb': output_path.stat().st_size / (1024*1024)
                }
                
                return True, None, processed_info
                
        except Exception as e:
            return False, f"Image processing failed: {str(e)}", None
    
    def _process_pdf(self, input_path: Path, output_path: Path, file_info: dict) -> Tuple[bool, Optional[str], Optional[dict]]:
        """Process PDF files (extract first page as image)"""
        try:
            # Import here to avoid dependency issues if pdf2image not installed
            from pdf2image import convert_from_path
            
            # Convert first page to image
            pages = convert_from_path(input_path, first_page=1, last_page=1, dpi=300)
            
            if not pages:
                return False, "Could not extract page from PDF", None
            
            img = pages[0]
            
            # Convert to RGB
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Get original dimensions
            original_width, original_height = img.size
            
            # Calculate optimal dimensions
            new_width, new_height = self._calculate_optimal_size(original_width, original_height)
            
            # Resize if necessary
            if (new_width, new_height) != (original_width, original_height):
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Enhance for text extraction
            img = self._enhance_for_text(img)
            
            # Save as PNG
            img.save(
                output_path,
                format='PNG',
                dpi=self.QUALITY_SETTINGS['dpi'],
                optimize=self.QUALITY_SETTINGS['optimize']
            )
            
            processed_info = {
                'original_dimensions': (original_width, original_height),
                'processed_dimensions': (new_width, new_height),
                'format': 'PNG',
                'source': 'pdf_page_1',
                'optimization': 'text_enhanced',
                'file_size_mb': output_path.stat().st_size / (1024*1024)
            }
            
            return True, None, processed_info
            
        except ImportError:
            return False, "PDF processing requires pdf2image library", None
        except Exception as e:
            return False, f"PDF processing failed: {str(e)}", None
    
    def _calculate_optimal_size(self, width: int, height: int) -> Tuple[int, int]:
        """Calculate optimal dimensions for o3 API (max 1024px, maintain aspect ratio)"""
        max_dim = max(width, height)
        
        if max_dim <= self.MAX_DIMENSION:
            return width, height
        
        # Calculate scaling factor
        scale_factor = self.MAX_DIMENSION / max_dim
        
        new_width = int(width * scale_factor)
        new_height = int(height * scale_factor)
        
        # Ensure minimum dimensions
        new_width = max(new_width, 100)
        new_height = max(new_height, 100)
        
        return new_width, new_height
    
    def _enhance_for_text(self, img: Image.Image) -> Image.Image:
        """Apply enhancements to improve text extraction quality"""
        try:
            # Slight sharpening for text clarity
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(1.1)
            
            # Slight contrast enhancement
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.05)
            
            # Very light noise reduction
            img = img.filter(ImageFilter.MedianFilter(size=1))
            
            return img
            
        except Exception:
            # If enhancement fails, return original
            return img
    
    def cleanup_processed_file(self, processed_path: str) -> bool:
        """Remove processed file after API call"""
        try:
            Path(processed_path).unlink(missing_ok=True)
            return True
        except Exception:
            return False
    
    def get_processing_info(self, file_info: dict) -> dict:
        """Get estimated processing information before actual processing"""
        width = file_info.get('width', 0)
        height = file_info.get('height', 0)
        
        if width and height:
            new_width, new_height = self._calculate_optimal_size(width, height)
            will_resize = (new_width, new_height) != (width, height)
            
            return {
                'will_resize': will_resize,
                'estimated_dimensions': (new_width, new_height),
                'estimated_tokens': self._estimate_tokens(new_width, new_height),
                'processing_needed': will_resize or file_info.get('mime_type') != 'image/png'
            }
        
        return {
            'will_resize': True,
            'estimated_dimensions': 'unknown',
            'estimated_tokens': 'unknown',
            'processing_needed': True
        }
    
    def _estimate_tokens(self, width: int, height: int) -> int:
        """Estimate token usage for o3 Vision API"""
        # Rough estimation based on OpenAI's token calculation
        # This is approximate - actual tokens may vary
        base_tokens = 85
        
        # Calculate tiles (512x512 each)
        tiles_x = (width + 511) // 512
        tiles_y = (height + 511) // 512
        total_tiles = tiles_x * tiles_y
        
        # Each tile adds ~170 tokens
        estimated_tokens = base_tokens + (total_tiles * 170)
        
        return estimated_tokens 