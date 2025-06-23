"""
Image Preprocessor Module
Handles image optimization, format conversion, and preparation for vision API
"""
import os
import shutil
import io
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from PIL import Image
import fitz  # PyMuPDF for PDF handling
import uuid

class ImagePreprocessor:
    def __init__(self, output_dir: str = "uploads/processed"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Optimal settings for vision API
        self.target_format = "PNG"  # PNG is best for OCR/text extraction
        self.max_dimension = 2048   # OpenAI's max for high detail
        self.target_dpi = 300       # Good for text clarity
        
    def preprocess_image(self, input_path: str, file_info: dict) -> Tuple[bool, Optional[str], Optional[dict]]:
        """
        Convert and optimize any input file for vision API processing
        
        Handles: JPEG, PNG, WEBP, GIF, BMP, TIFF, PDF (single/multi-page)
        Outputs: Optimized PNG ready for vision API
        """
        try:
            input_path = Path(input_path)
            unique_id = str(uuid.uuid4())[:8]
            
            # Handle PDF files separately
            if file_info['extension'].lower() == '.pdf':
                return self._process_pdf(input_path, unique_id, file_info)
            
            # Handle image files
            return self._process_image(input_path, unique_id, file_info)
            
        except Exception as e:
            return False, f"Preprocessing failed: {str(e)}", None
    
    def _process_pdf(self, pdf_path: Path, unique_id: str, file_info: dict) -> Tuple[bool, Optional[str], Optional[dict]]:
        """Convert PDF to optimized image(s) for vision processing"""
        try:
            # Open PDF
            pdf_doc = fitz.open(str(pdf_path))
            
            if len(pdf_doc) == 0:
                return False, "PDF contains no pages", None
            
            # For now, process only the first page (can be extended for multi-page)
            page = pdf_doc[0]
            
            # Convert PDF page to image with high DPI for text clarity
            mat = fitz.Matrix(self.target_dpi / 72, self.target_dpi / 72)  # Scale for target DPI
            pix = page.get_pixmap(matrix=mat)
            
            # Convert to PIL Image
            img_data = pix.tobytes("png")
            image = Image.open(io.BytesIO(img_data))
            
            # Process the converted image
            processed_image, processing_info = self._optimize_image_for_vision(image)
            
            # Save processed image
            output_filename = f"{unique_id}_{pdf_path.stem}.png"
            output_path = self.output_dir / output_filename
            processed_image.save(output_path, "PNG", optimize=True)
            
            pdf_doc.close()
            
            # Calculate file size
            file_size_mb = output_path.stat().st_size / (1024 * 1024)
            
            result = {
                'processed_path': str(output_path),
                'unique_id': unique_id,
                'original_format': 'PDF',
                'output_format': 'PNG',
                'original_dimensions': [pix.width, pix.height],
                'processed_dimensions': list(processed_image.size),
                'file_size_mb': file_size_mb,
                'pages_processed': 1,
                'total_pages': len(pdf_doc),
                'optimization': processing_info['optimization'],
                'ready_for_api': True
            }
            
            return True, None, result
            
        except Exception as e:
            return False, f"PDF processing failed: {str(e)}", None
    
    def _process_image(self, image_path: Path, unique_id: str, file_info: dict) -> Tuple[bool, Optional[str], Optional[dict]]:
        """Convert and optimize image files for vision processing"""
        try:
            # Open image with PIL (handles JPEG, PNG, WEBP, GIF, BMP, TIFF, etc.)
            with Image.open(image_path) as image:
                # Convert to RGB if necessary (handles CMYK, grayscale, etc.)
                if image.mode not in ('RGB', 'RGBA'):
                    if image.mode == 'P' and 'transparency' in image.info:
                        # Handle transparent palette images
                        image = image.convert('RGBA')
                    else:
                        image = image.convert('RGB')
                
                # Process and optimize
                processed_image, processing_info = self._optimize_image_for_vision(image)
                
                # Save as PNG (best for OCR/text extraction)
                output_filename = f"{unique_id}_{image_path.stem}.png"
                output_path = self.output_dir / output_filename
                processed_image.save(output_path, "PNG", optimize=True)
                
                # Calculate file size
                file_size_mb = output_path.stat().st_size / (1024 * 1024)
                
                result = {
                    'processed_path': str(output_path),
                    'unique_id': unique_id,
                    'original_format': file_info['extension'].upper().replace('.', ''),
                    'output_format': 'PNG',
                    'original_dimensions': list(image.size),
                    'processed_dimensions': list(processed_image.size),
                    'file_size_mb': file_size_mb,
                    'optimization': processing_info['optimization'],
                    'ready_for_api': True
                }
                
                return True, None, result
                
        except Exception as e:
            return False, f"Image processing failed: {str(e)}", None
    
    def _optimize_image_for_vision(self, image: Image.Image) -> Tuple[Image.Image, Dict[str, Any]]:
        """Optimize image specifically for vision API processing"""
        original_size = image.size
        optimization_applied = []
        
        # 1. Handle transparency (convert RGBA to RGB with white background)
        if image.mode == 'RGBA':
            # Create white background
            background = Image.new('RGB', image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[-1])  # Use alpha channel as mask
            image = background
            optimization_applied.append("transparency_removed")
        
        # 2. Resize if too large (OpenAI max is 2048x2048 for high detail)
        if max(image.size) > self.max_dimension:
            # Calculate new size maintaining aspect ratio
            ratio = self.max_dimension / max(image.size)
            new_size = tuple(int(dim * ratio) for dim in image.size)
            image = image.resize(new_size, Image.Resampling.LANCZOS)
            optimization_applied.append("resized")
        
        # 3. Enhance for text clarity if image is low contrast
        image = self._enhance_text_clarity(image)
        if hasattr(self, '_enhancement_applied') and self._enhancement_applied:
            optimization_applied.append("text_enhanced")
        
        # 4. Ensure minimum size (too small images don't work well)
        min_dimension = 100
        if min(image.size) < min_dimension:
            ratio = min_dimension / min(image.size)
            new_size = tuple(int(dim * ratio) for dim in image.size)
            image = image.resize(new_size, Image.Resampling.LANCZOS)
            optimization_applied.append("upscaled")
        
        processing_info = {
            'optimization': optimization_applied,
            'size_change': f"{original_size} → {image.size}",
            'ready_for_vision_api': True
        }
        
        return image, processing_info
    
    def _enhance_text_clarity(self, image: Image.Image) -> Image.Image:
        """Enhance image for better text recognition"""
        from PIL import ImageEnhance, ImageFilter
        
        self._enhancement_applied = False
        
        try:
            # Convert to grayscale to analyze contrast
            gray = image.convert('L')
            
            # Calculate image statistics
            import numpy as np
            img_array = np.array(gray)
            contrast = img_array.std()
            brightness = img_array.mean()
            
            # Apply enhancements if needed
            enhanced = image
            
            # Increase contrast if low
            if contrast < 50:  # Low contrast threshold
                enhancer = ImageEnhance.Contrast(enhanced)
                enhanced = enhancer.enhance(1.3)  # Increase contrast by 30%
                self._enhancement_applied = True
            
            # Adjust brightness if too dark or too bright
            if brightness < 100:  # Too dark
                enhancer = ImageEnhance.Brightness(enhanced)
                enhanced = enhancer.enhance(1.2)
                self._enhancement_applied = True
            elif brightness > 200:  # Too bright
                enhancer = ImageEnhance.Brightness(enhanced)
                enhanced = enhancer.enhance(0.9)
                self._enhancement_applied = True
            
            # Slight sharpening for text
            enhanced = enhanced.filter(ImageFilter.UnsharpMask(radius=1, percent=120, threshold=3))
            
            return enhanced
            
        except Exception:
            # If enhancement fails, return original
            return image
    
    def get_processing_info(self, file_info: dict) -> Dict[str, Any]:
        """Get information about what processing will be needed"""
        extension = file_info['extension'].lower()
        
        processing_needed = True
        will_resize = False
        estimated_tokens = 85  # Base cost for low detail
        
        # Check if resizing will be needed
        if 'width' in file_info and 'height' in file_info:
            max_dim = max(file_info['width'], file_info['height'])
            if max_dim > self.max_dimension:
                will_resize = True
                # Calculate estimated dimensions after resize
                ratio = self.max_dimension / max_dim
                estimated_width = int(file_info['width'] * ratio)
                estimated_height = int(file_info['height'] * ratio)
            else:
                estimated_width = file_info['width']
                estimated_height = file_info['height']
        else:
            # Default estimates for unknown dimensions
            estimated_width = 1024
            estimated_height = 768
        
        # Estimate token usage for high detail mode
        # OpenAI: 170 tokens per 512px tile + 85 base
        tiles_x = (estimated_width + 511) // 512
        tiles_y = (estimated_height + 511) // 512
        estimated_tokens = (tiles_x * tiles_y * 170) + 85
        
        return {
            'processing_needed': processing_needed,
            'will_resize': will_resize,
            'estimated_dimensions': [estimated_width, estimated_height],
            'estimated_tokens': estimated_tokens,
            'target_format': self.target_format,
            'supports_format': extension in ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff', '.pdf']
        }
    
    def cleanup_processed_file(self, file_path: str):
        """Clean up a processed file"""
        try:
            Path(file_path).unlink()
        except Exception:
            pass  # Ignore cleanup errors 