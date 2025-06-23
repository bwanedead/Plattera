"""
Vision Processor Module
Handles Vision API integration for image-to-text extraction with configurable models
Supports multi-model parallel processing for maximum accuracy
"""
import base64
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
from services.llm_service import get_llm_service
from services.llm_profiles import LLMProfile, ProfileConfig
import io
import asyncio
import concurrent.futures
from threading import Thread
import time

class VisionProcessor:
    def __init__(self):
        self.openai_service = get_llm_service("openai")
        self.anthropic_service = get_llm_service("anthropic")
    
    def extract_text_from_image(self, 
                              image_path: str, 
                              extraction_mode: str = "legal_document",
                              model: str = "gpt-4o") -> Tuple[bool, Optional[str], Optional[dict]]:
        """
        Extract text from image using Vision API - SIMPLE TEXT EXTRACTION ONLY
        """
        # Determine provider from model
        provider = self._get_provider_for_model(model)
        service = self.openai_service if provider == "openai" else self.anthropic_service
        
        if not service.is_configured():
            return False, f"{provider.title()} client not configured", None
        
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
            
            print(f"DEBUG: Making vision call with model: {model} (provider: {provider})")
            
            # Make simple vision API call
            success, error, result = service.make_vision_call(
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
                'provider': provider,
                'word_count': len(extracted_text.split()) if extracted_text else 0,
                'character_count': len(extracted_text) if extracted_text else 0,
                'tokens_used': result.get('usage', {}).get('total_tokens', 0)
            }
            
            print(f"DEBUG: Extraction successful, text length: {len(extracted_text)}")
            
            return True, None, extraction_result
            
        except Exception as e:
            print(f"DEBUG: Exception in extract_text_from_image: {str(e)}")
            return False, f"Vision processing error: {str(e)}", None
    
    def extract_text_committee_mode(self, 
                                  image_path: str,
                                  models: List[str] = None,
                                  extraction_mode: str = "legal_document") -> Tuple[bool, Optional[str], Optional[dict]]:
        """
        Extract text using multiple models in parallel (committee approach)
        
        Args:
            image_path: Path to the image file
            models: List of model names to use. If None, uses default committee
            extraction_mode: Type of extraction to perform
            
        Returns:
            Tuple of (success, error_message, results_dict)
        """
        if models is None:
            # Updated default committee: GPT-4o, o3, Claude Sonnet 4, Claude Sonnet 3.7
            models = ["gpt-4o", "o3", "claude-sonnet-4-20250514", "claude-3-7-sonnet-20250219"]
        
        print(f"DEBUG: Starting committee extraction with models: {models}")
        
        # Validate all models are available
        available_models = self.get_available_models()
        invalid_models = [m for m in models if m not in available_models]
        if invalid_models:
            return False, f"Invalid models: {invalid_models}", None
        
        # Check if required services are configured
        openai_models = [m for m in models if self._get_provider_for_model(m) == "openai"]
        anthropic_models = [m for m in models if self._get_provider_for_model(m) == "anthropic"]
        
        if openai_models and not self.openai_service.is_configured():
            return False, "OpenAI service not configured but OpenAI models requested", None
        
        if anthropic_models and not self.anthropic_service.is_configured():
            return False, "Anthropic service not configured but Anthropic models requested", None
        
        # Run extractions in parallel
        start_time = time.time()
        results = self._run_parallel_extractions(image_path, models, extraction_mode)
        end_time = time.time()
        
        # Analyze results
        successful_results = {model: result for model, result in results.items() if result['success']}
        failed_results = {model: result for model, result in results.items() if not result['success']}
        
        if not successful_results:
            return False, "All model extractions failed", {
                'failed_results': failed_results,
                'total_time': end_time - start_time
            }
        
        # Compile committee results
        committee_result = {
            'committee_mode': True,
            'models_used': models,
            'successful_extractions': len(successful_results),
            'failed_extractions': len(failed_results),
            'total_time': end_time - start_time,
            'results': successful_results,
            'failed_results': failed_results,
            'summary': self._analyze_committee_results(successful_results)
        }
        
        print(f"DEBUG: Committee extraction completed in {end_time - start_time:.2f}s")
        print(f"DEBUG: Successful: {len(successful_results)}, Failed: {len(failed_results)}")
        
        return True, None, committee_result
    
    def _run_parallel_extractions(self, image_path: str, models: List[str], extraction_mode: str) -> Dict[str, Dict[str, Any]]:
        """Run multiple model extractions in parallel using ThreadPoolExecutor"""
        results = {}
        
        def extract_single_model(model):
            """Helper function to extract text with a single model"""
            try:
                success, error, result = self.extract_text_from_image(image_path, extraction_mode, model)
                return {
                    'success': success,
                    'error': error,
                    'result': result,
                    'model': model
                }
            except Exception as e:
                return {
                    'success': False,
                    'error': str(e),
                    'result': None,
                    'model': model
                }
        
        # Use ThreadPoolExecutor for parallel execution
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(models)) as executor:
            # Submit all tasks
            future_to_model = {executor.submit(extract_single_model, model): model for model in models}
            
            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_model):
                model = future_to_model[future]
                try:
                    result = future.result()
                    results[model] = result
                    print(f"DEBUG: Completed extraction for {model}: {'Success' if result['success'] else 'Failed'}")
                except Exception as e:
                    results[model] = {
                        'success': False,
                        'error': f"Execution error: {str(e)}",
                        'result': None,
                        'model': model
                    }
                    print(f"DEBUG: Exception in {model} extraction: {str(e)}")
        
        return results
    
    def _analyze_committee_results(self, successful_results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze committee results to provide summary statistics"""
        if not successful_results:
            return {}
        
        # Extract text lengths and token usage
        text_lengths = []
        word_counts = []
        token_usage = []
        
        for model, result_data in successful_results.items():
            if result_data['success'] and result_data['result']:
                result = result_data['result']
                text_lengths.append(result.get('character_count', 0))
                word_counts.append(result.get('word_count', 0))
                token_usage.append(result.get('tokens_used', 0))
        
        # Calculate statistics
        summary = {
            'total_models': len(successful_results),
            'avg_text_length': sum(text_lengths) / len(text_lengths) if text_lengths else 0,
            'min_text_length': min(text_lengths) if text_lengths else 0,
            'max_text_length': max(text_lengths) if text_lengths else 0,
            'avg_word_count': sum(word_counts) / len(word_counts) if word_counts else 0,
            'total_tokens_used': sum(token_usage),
            'text_length_variance': max(text_lengths) - min(text_lengths) if text_lengths else 0
        }
        
        # Add model-specific summaries
        model_summaries = {}
        for model, result_data in successful_results.items():
            if result_data['success'] and result_data['result']:
                result = result_data['result']
                model_summaries[model] = {
                    'character_count': result.get('character_count', 0),
                    'word_count': result.get('word_count', 0),
                    'tokens_used': result.get('tokens_used', 0),
                    'provider': result.get('provider', 'unknown')
                }
        
        summary['model_summaries'] = model_summaries
        
        return summary
    
    def _get_provider_for_model(self, model: str) -> str:
        """Determine which provider a model belongs to"""
        available_models = ProfileConfig.get_supported_models()
        if model in available_models:
            return available_models[model].get('provider', 'openai')
        
        # Fallback based on model name patterns
        if model.startswith('claude'):
            return 'anthropic'
        else:
            return 'openai'
    
    def get_available_models(self) -> Dict[str, Dict[str, Any]]:
        """Get list of available vision models with their capabilities"""
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
        provider = self._get_provider_for_model(model)
        service = self.openai_service if provider == "openai" else self.anthropic_service
        
        if not service.is_configured():
            return False, f"{provider.title()} client not configured", None
        
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
            
            # Use the service for the test call
            success, error, result = service.make_vision_call(
                text_prompt="What do you see in this image? Respond with 'Vision API working'",
                image_base64=test_image_b64,
                profile=LLMProfile.FAST_PROCESSING,
                model=model
            )
            
            if not success:
                return False, error, None
            
            test_result = {
                'status': 'success',
                'response': result['content'],
                'model': model,
                'provider': provider,
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