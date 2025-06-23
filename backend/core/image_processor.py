"""
Image Processor Module
Main orchestrator for the image-to-text pipeline
Coordinates validation, preprocessing, and vision processing
"""
import os
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
from .image_validator import ImageValidator
from .image_preprocessor import ImagePreprocessor
from .vision_processor import VisionProcessor

class ImageProcessor:
    def __init__(self, 
                 upload_dir: str = "uploads/raw",
                 processed_dir: str = "uploads/processed",
                 temp_dir: str = "uploads/temp"):
        
        # Initialize directories
        self.upload_dir = Path(upload_dir)
        self.processed_dir = Path(processed_dir)
        self.temp_dir = Path(temp_dir)
        
        # Ensure directories exist
        for directory in [self.upload_dir, self.processed_dir, self.temp_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Initialize processors
        self.validator = ImageValidator()
        self.preprocessor = ImagePreprocessor(
            output_dir=str(self.processed_dir)
        )
        self.vision_processor = VisionProcessor()
    
    def process_image_to_text(self, 
                            image_path: str, 
                            extraction_mode: str = "legal_document",
                            model: str = "gpt-4o",
                            cleanup_after: bool = True) -> Tuple[bool, Optional[str], Optional[dict]]:
        """
        Complete image-to-text pipeline with model selection
        
        Args:
            image_path: Path to the input image
            extraction_mode: Type of text extraction to perform
            model: Model to use for vision processing
            cleanup_after: Whether to clean up processed files after completion
        
        Returns:
            Tuple of (success, error_message, result)
        """
        processed_path = None
        
        try:
            # Step 1: Validate image
            is_valid, error, file_info = self.validator.validate_file(image_path)
            if not is_valid:
                return False, f"Validation failed: {error}", None
            
            # Step 2: Preprocess image
            success, error, processed_info = self.preprocessor.preprocess_image(image_path, file_info)
            if not success:
                return False, f"Preprocessing failed: {error}", None
            
            processed_path = processed_info['processed_path']
            
            # Step 3: Extract text using vision API with selected model
            success, error, extraction_result = self.vision_processor.extract_text_from_image(
                processed_path, extraction_mode, model
            )
            if not success:
                return False, f"Text extraction failed: {error}", None
            
            # Step 4: Use extracted text directly (no cleaning needed)
            extracted_text = extraction_result['extracted_text']
            
            # Combine all results
            final_result = {
                'extracted_text': extracted_text,  # Use raw AI output
                'extraction_mode': extraction_mode,
                'model_used': model,
                'file_info': file_info,
                'processing_info': processed_info,
                'extraction_info': extraction_result,
                'pipeline_stats': {
                    'original_size_mb': file_info['size_mb'],
                    'processed_size_mb': processed_info['file_size_mb'],
                    'tokens_used': extraction_result.get('tokens_used', 0),
                    'confidence': extraction_result.get('confidence', 0.8),
                    'word_count': len(extracted_text.split()) if extracted_text else 0
                }
            }
            
            return True, None, final_result
            
        except Exception as e:
            return False, f"Pipeline error: {str(e)}", None
        
        finally:
            # Cleanup processed file if requested
            if cleanup_after and processed_path:
                self.preprocessor.cleanup_processed_file(processed_path)
    
    def process_image_committee_mode(self, 
                                   image_path: str,
                                   models: List[str] = None,
                                   extraction_mode: str = "legal_document",
                                   cleanup_after: bool = True) -> Tuple[bool, Optional[str], Optional[dict]]:
        """
        Process image using committee of models for maximum accuracy
        
        Args:
            image_path: Path to the image file
            models: List of models to use. If None, uses default committee
            extraction_mode: Type of extraction to perform
            cleanup_after: Whether to cleanup processed files after extraction
        
        Returns:
            Tuple of (success, error_message, committee_results_dict)
        """
        processed_path = None
        
        try:
            # Step 1: Validate the image file
            is_valid, error, file_info = self.validator.validate_file(image_path)
            if not is_valid:
                return False, f"Validation failed: {error}", None
            
            # Step 2: Preprocess the image (format conversion, optimization)
            success, error, processed_info = self.preprocessor.preprocess_image(
                image_path, file_info
            )
            if not success:
                return False, f"Preprocessing failed: {error}", None
            
            processed_path = processed_info['processed_path']
            
            # Step 3: Extract text using committee of models
            success, error, committee_result = self.vision_processor.extract_text_committee_mode(
                processed_path, models, extraction_mode
            )
            if not success:
                return False, f"Committee extraction failed: {error}", None
            
            # Step 4: Combine with pipeline metadata
            final_result = {
                'committee_mode': True,
                'extraction_mode': extraction_mode,
                'file_info': file_info,
                'processing_info': processed_info,
                'committee_results': committee_result,
                'pipeline_stats': {
                    'original_size_mb': file_info['size_mb'],
                    'processed_size_mb': processed_info['file_size_mb'],
                    'total_models_used': committee_result.get('successful_extractions', 0),
                    'total_tokens_used': committee_result.get('summary', {}).get('total_tokens_used', 0),
                    'processing_time': committee_result.get('total_time', 0)
                }
            }
            
            return True, None, final_result
            
        except Exception as e:
            return False, f"Committee pipeline error: {str(e)}", None
        
        finally:
            # Cleanup processed file if requested
            if cleanup_after and processed_path:
                self.preprocessor.cleanup_processed_file(processed_path)
    
    def save_uploaded_file(self, file_data: bytes, filename: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Save uploaded file to the upload directory
        
        Args:
            file_data: Binary file data
            filename: Original filename
        
        Returns:
            Tuple of (success, error_message, saved_path)
        """
        try:
            # Sanitize filename
            safe_filename = self._sanitize_filename(filename)
            file_path = self.upload_dir / safe_filename
            
            # Ensure unique filename
            counter = 1
            original_path = file_path
            while file_path.exists():
                stem = original_path.stem
                suffix = original_path.suffix
                file_path = self.upload_dir / f"{stem}_{counter}{suffix}"
                counter += 1
            
            # Save file
            with open(file_path, 'wb') as f:
                f.write(file_data)
            
            return True, None, str(file_path)
            
        except Exception as e:
            return False, f"File save error: {str(e)}", None
    
    def get_processing_estimate(self, image_path: str) -> Tuple[bool, Optional[str], Optional[dict]]:
        """
        Get processing estimates without actually processing
        
        Args:
            image_path: Path to the image file
        
        Returns:
            Tuple of (success, error_message, estimate_info)
        """
        try:
            # Validate file first
            is_valid, error, file_info = self.validator.validate_file(image_path)
            if not is_valid:
                return False, f"Validation failed: {error}", None
            
            # Get processing estimates
            processing_info = self.preprocessor.get_processing_info(file_info)
            
            estimate = {
                'file_info': file_info,
                'processing_needed': processing_info['processing_needed'],
                'will_resize': processing_info['will_resize'],
                'estimated_dimensions': processing_info['estimated_dimensions'],
                'estimated_tokens': processing_info['estimated_tokens'],
                'estimated_cost_usd': self._estimate_cost(processing_info['estimated_tokens']),
                'supported_extraction_modes': self.vision_processor.get_supported_extraction_modes(),
                'available_models': self.get_available_models()
            }
            
            return True, None, estimate
            
        except Exception as e:
            return False, f"Estimation error: {str(e)}", None
    
    def test_pipeline_components(self) -> Dict[str, Any]:
        """Test all pipeline components"""
        results = {}
        
        # Test vision processor with multiple models
        available_models = self.get_available_models()
        for model_name, model_info in available_models.items():
            vision_success, vision_error, vision_result = self.vision_processor.test_vision_connection(model_name)
            results[f'vision_api_{model_name}'] = {
                'status': 'success' if vision_success else 'error',
                'error': vision_error,
                'result': vision_result,
                'provider': model_info.get('provider', 'unknown')
            }
        
        # Test file system access
        try:
            test_file = self.temp_dir / "test.txt"
            test_file.write_text("test")
            test_file.unlink()
            results['file_system'] = {'status': 'success'}
        except Exception as e:
            results['file_system'] = {'status': 'error', 'error': str(e)}
        
        # Test image processing libraries
        try:
            from PIL import Image
            import magic
            results['image_libraries'] = {'status': 'success', 'pil_available': True, 'magic_available': True}
        except ImportError as e:
            results['image_libraries'] = {'status': 'error', 'error': str(e)}
        
        return results
    
    def cleanup_old_files(self, max_age_hours: int = 24) -> Dict[str, int]:
        """Clean up old processed and temp files"""
        import time
        
        cleanup_stats = {'processed': 0, 'temp': 0, 'errors': 0}
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        # Clean processed files
        for file_path in self.processed_dir.glob("*"):
            try:
                if file_path.is_file():
                    file_age = current_time - file_path.stat().st_mtime
                    if file_age > max_age_seconds:
                        file_path.unlink()
                        cleanup_stats['processed'] += 1
            except Exception:
                cleanup_stats['errors'] += 1
        
        # Clean temp files
        for file_path in self.temp_dir.glob("*"):
            try:
                if file_path.is_file():
                    file_age = current_time - file_path.stat().st_mtime
                    if file_age > max_age_seconds:
                        file_path.unlink()
                        cleanup_stats['temp'] += 1
            except Exception:
                cleanup_stats['errors'] += 1
        
        return cleanup_stats
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe storage"""
        # Remove path separators and dangerous characters
        safe_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_"
        sanitized = "".join(c if c in safe_chars else "_" for c in filename)
        
        # Ensure reasonable length
        if len(sanitized) > 100:
            name_part = sanitized[:80]
            ext_part = sanitized[-20:] if '.' in sanitized[-20:] else ""
            sanitized = name_part + ext_part
        
        return sanitized or "uploaded_file"
    
    def _estimate_cost(self, estimated_tokens: int) -> float:
        """Estimate API cost in USD"""
        if isinstance(estimated_tokens, str) or estimated_tokens == 0:
            return 0.0
        
        # Updated pricing estimates for committee mode
        cost_per_1k_tokens = 0.15  # Average across all models
        estimated_cost = (estimated_tokens / 1000) * cost_per_1k_tokens
        return round(estimated_cost, 4)

    def get_available_models(self) -> Dict[str, Dict[str, Any]]:
        """Get available models for vision processing"""
        return self.vision_processor.get_available_models() 