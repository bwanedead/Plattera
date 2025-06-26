"""
Image to Text Processing Pipeline
Pure business logic - no API endpoints

🔴 CRITICAL REDUNDANCY IMPLEMENTATION DOCUMENTATION 🔴
=====================================================

THIS MODULE IS THE CENTRAL ORCHESTRATOR - PRESERVE ALL WIRING BELOW 🔴

COMPLETE DATA FLOW CHAIN:
1. API Endpoint → pipeline.process()
2. pipeline.process() → _get_service_for_model() → OpenAI service
3. pipeline.process() → _prepare_image() → enhance_for_character_recognition()
4. pipeline.process() → service.process_image_with_text()
5. OpenAI service → call_vision() → OpenAI API
6. OpenAI API response → _standardize_response() → API response

CRITICAL METHOD SIGNATURES:
- process(image_path: str, model: str, extraction_mode: str, enhancement_settings: dict) -> dict
- service.process_image_with_text(image_data: str, prompt: str, model: str, **kwargs) -> dict
- enhance_for_character_recognition(image_path: str) -> Tuple[str, str]

CRITICAL RESPONSE FORMAT:
{
    "success": True,
    "extracted_text": "...",  # THIS IS WHAT FRONTEND DISPLAYS
    "model_used": "gpt-4o",
    "service_type": "llm",
    "tokens_used": 6561,
    "confidence_score": 1.0,
    "metadata": {...}
}

CRITICAL WIRING POINTS:
1. _prepare_image() MUST return (base64_string, format_string)
2. service.process_image_with_text() MUST receive base64 string as image_data
3. _standardize_response() MUST extract "extracted_text" from service response
4. Final response MUST have "extracted_text" field for frontend

CRITICAL SERVICE INTERFACE:
- OpenAI service MUST have process_image_with_text() method
- Method MUST return dict with "success" and "extracted_text" fields
- OpenAI service MUST handle base64 image data correctly

ENHANCEMENT SAFETY RULES:
- NEVER change _prepare_image() return signature
- NEVER change service.process_image_with_text() call signature
- NEVER modify _standardize_response() extraction logic
- ALWAYS preserve "extracted_text" field in final response
- ALWAYS maintain service interface compatibility

REDUNDANCY IMPLEMENTATION SAFETY RULES:
======================================

✅ SAFE TO ADD:
- process_with_redundancy() method as NEW method alongside existing process()
- New private methods: _execute_parallel_calls(), _analyze_redundancy_consensus()
- Additional imports: concurrent.futures, difflib, typing.List
- Redundancy-specific response fields in metadata

❌ DO NOT MODIFY:
- Existing process() method signature or behavior
- Any existing private method signatures
- Service interface calls
- Response format structure
- Image preparation logic
- Error handling patterns

CRITICAL REDUNDANCY REQUIREMENTS:
================================
1. process_with_redundancy() MUST return same format as process()
2. MUST handle redundancy_count=1 by calling original process()
3. MUST preserve all existing error handling patterns
4. MUST use same service interface as original process()
5. MUST maintain "extracted_text" as primary result field

TESTING CHECKPOINTS:
===================
After redundancy implementation, verify:
1. Original process() method still works unchanged
2. process_with_redundancy(count=1) produces same result as process()
3. All service integrations remain functional
4. Response format matches frontend expectations
5. Error handling works for both methods
"""
from services.registry import get_registry
from prompts.image_to_text import get_image_to_text_prompt
import base64
from pathlib import Path
import logging
from typing import Tuple, List
import concurrent.futures
from difflib import SequenceMatcher
import re
from .image_processor import enhance_for_character_recognition

logger = logging.getLogger(__name__)

class ImageToTextPipeline:
    """
    Clean, decoupled pipeline for image-to-text processing
    
    🔴 CRITICAL ORCHESTRATOR - MAINTAINS SERVICE INTEGRATION 🔴
    """
    
    def __init__(self):
        # CRITICAL: Registry provides service routing
        self.registry = get_registry()
    
    def process(self, image_path: str, model: str = "gpt-4o", extraction_mode: str = "legal_document", enhancement_settings: dict = None) -> dict:
        """
        Process an image to extract text
        
        🔴 CRITICAL ENTRY POINT - DO NOT MODIFY SIGNATURE 🔴
        
        Args:
            image_path: Path to the image file
            model: Model identifier to use for processing
            extraction_mode: Mode of extraction (legal_document, simple_ocr, etc.)
            enhancement_settings: Optional dict with contrast, sharpness, brightness, color values
            
        Returns:
            dict: Processing result with extracted text and metadata
            
        CRITICAL FLOW:
        1. Get service for model (OpenAI for gpt-4o, gpt-o4-mini)
        2. Prepare enhanced image (base64 encoding)
        3. Get appropriate prompt for extraction mode
        4. Call service.process_image_with_text()
        5. Standardize response format
        """
        try:
            # CRITICAL: Get the appropriate service for this model
            # This routing is essential for multi-service support
            service = self._get_service_for_model(model)
            if not service:
                return {
                    "success": False,
                    "error": f"No service available for model: {model}"
                }
            
            # CRITICAL: Prepare the enhanced image
            # This MUST return (base64_string, format_string) tuple
            image_data, image_format = self._prepare_image(image_path, enhancement_settings)
            if not image_data:
                return {
                    "success": False,
                    "error": "Failed to prepare image data"
                }
            
            # CRITICAL: Get the prompt for this extraction mode and model
            # Different models may need different prompts
            prompt = get_image_to_text_prompt(extraction_mode, model)
            
            # CRITICAL: Process based on service type
            # OpenAI service MUST have process_image_with_text method
            if hasattr(service, 'process_image_with_text'):
                # LLM service (OpenAI)
                result = service.process_image_with_text(
                    image_data=image_data,    # CRITICAL: base64 string
                    prompt=prompt,
                    model=model,
                    image_format=image_format  # CRITICAL: format string
                )
            elif hasattr(service, 'extract_text'):
                # OCR service
                result = service.extract_text(image_path, model)
            else:
                return {
                    "success": False,
                    "error": f"Service {service.__class__.__name__} doesn't support image processing"
                }
            
            # CRITICAL: Standardize the response
            # This ensures consistent format for frontend
            return self._standardize_response(result, model, service)
            
        except Exception as e:
            logger.error(f"Pipeline processing failed: {str(e)}")
            return {
                "success": False,
                "error": f"Processing failed: {str(e)}"
            }
    
    def _get_service_for_model(self, model: str):
        """
        Find the appropriate service for a given model
        
        🔴 CRITICAL SERVICE ROUTING - MAINTAINS MODEL-SERVICE MAPPING 🔴
        """
        # CRITICAL: Get all available models from registry
        all_models = self.registry.get_all_models()
        
        if model not in all_models:
            return None
            
        # CRITICAL: Extract service routing information
        model_info = all_models[model]
        service_type = model_info.get("service_type")
        service_name = model_info.get("service_name")
        
        # CRITICAL: Route to appropriate service type
        if service_type == "llm":
            return self.registry.llm_services.get(service_name)
        elif service_type == "ocr":
            return self.registry.ocr_services.get(service_name)
        
        return None
    
    def _prepare_image(self, image_path: str, enhancement_settings: dict = None) -> Tuple[str, str]:
        """Enhanced with bulletproof error handling"""
        try:
            image_path = Path(image_path)
            if not image_path.exists():
                logger.error(f"Image path does not exist: {image_path}")
                return None, None
            
            # Validate enhancement settings
            if enhancement_settings:
                try:
                    contrast = float(enhancement_settings.get('contrast', 2.0))
                    sharpness = float(enhancement_settings.get('sharpness', 2.0))
                    brightness = float(enhancement_settings.get('brightness', 1.5))
                    color = max(0.0, min(3.0, float(enhancement_settings.get('color', 1.0))))
                    
                    logger.info(f"Using enhancement settings: C:{contrast}, S:{sharpness}, B:{brightness}, Col:{color}")
                    
                    enhanced_image_data, image_format = enhance_for_character_recognition(
                        str(image_path),
                        contrast=contrast,
                        sharpness=sharpness,
                        brightness=brightness,
                        color=color
                    )
                except Exception as e:
                    logger.warning(f"Enhancement settings parsing failed: {e}, using defaults")
                    enhanced_image_data, image_format = enhance_for_character_recognition(str(image_path))
            else:
                # Use default enhancement settings
                enhanced_image_data, image_format = enhance_for_character_recognition(str(image_path))
            
            # Validate results
            if not enhanced_image_data:
                logger.error("Image enhancement returned empty data")
                return None, None
            
            return enhanced_image_data, image_format
            
        except Exception as e:
            logger.error(f"Failed to prepare image: {str(e)}")
            return None, None
    
    def _standardize_response(self, result: dict, model: str, service) -> dict:
        """
        Standardize response format across different services
        
        🔴 CRITICAL RESPONSE FORMATTING - FRONTEND DEPENDS ON THIS 🔴
        
        CRITICAL FIELDS:
        - "extracted_text": The main text content (REQUIRED by frontend)
        - "success": Boolean status (REQUIRED)
        - "model_used": Model identifier (REQUIRED)
        - "service_type": Service type (REQUIRED)
        - "tokens_used": Token count (OPTIONAL but useful)
        """
        if not result.get("success", False):
            return result
            
        # CRITICAL: Add consistent metadata while preserving extracted_text
        # Frontend specifically looks for "extracted_text" field
        return {
            "success": True,
            "extracted_text": result.get("extracted_text", ""),  # CRITICAL: Frontend dependency
            "model_used": model,
            "service_type": "llm" if hasattr(service, 'process_image_with_text') else "ocr",
            "service_name": service.__class__.__name__.lower().replace('service', ''),
            "tokens_used": result.get("tokens_used"),
            "confidence_score": result.get("confidence_score"),
            "metadata": {
                "processing_time": result.get("processing_time"),
                "image_dimensions": result.get("image_dimensions"),
                "file_size": result.get("file_size"),
                **result.get("metadata", {})
            }
        }
    
    def get_available_models(self) -> dict:
        """Get models available for image-to-text processing"""
        all_models = self.registry.get_all_models()
        
        # Filter for models that can process images
        image_models = {}
        for model_id, model_info in all_models.items():
            if model_info.get("capabilities", {}).get("image_processing", False):
                image_models[model_id] = model_info
                
        return image_models
    
    def get_extraction_modes(self) -> dict:
        """Get available extraction modes"""
        return {
            "legal_document": "Optimized for legal documents and contracts",
            "simple_ocr": "Simple text extraction with minimal processing",
            "handwritten": "Specialized for handwritten text recognition",
            "property_deed": "Optimized for property deeds and real estate documents",
            "table_extraction": "Extract structured data from tables"
        }
    
    def process_with_redundancy(self, image_path: str, model: str = "gpt-4o", extraction_mode: str = "legal_document", 
                              enhancement_settings: dict = None, redundancy_count: int = 3) -> dict:
        """
        Process an image with redundancy for improved accuracy
        
        Args:
            image_path: Path to the image file
            model: Model identifier to use for processing
            extraction_mode: Mode of extraction
            enhancement_settings: Optional enhancement settings
            redundancy_count: Number of parallel API calls (default: 3)
            
        Returns:
            dict: Processing result with redundancy analysis
        """
        if redundancy_count <= 1:
            # No redundancy requested, use regular processing
            return self.process(image_path, model, extraction_mode, enhancement_settings)
        
        try:
            logger.info(f"🔄 Starting redundant processing with {redundancy_count} parallel calls")
            
            # Prepare image once for all calls
            image_data, image_format = self._prepare_image(image_path, enhancement_settings)
            if not image_data:
                return {
                    "success": False,
                    "error": "Failed to prepare image data"
                }
            
            service = self._get_service_for_model(model)
            if not service:
                return {
                    "success": False,
                    "error": f"No service available for model: {model}"
                }
            
            prompt = get_image_to_text_prompt(extraction_mode, model)
            
            # Execute parallel API calls
            results = self._execute_parallel_calls(service, image_data, image_format, prompt, model, redundancy_count)
            
            # Analyze results for consensus
            consensus_result = self._analyze_redundancy_consensus(results, model, service)
            
            return consensus_result
            
        except Exception as e:
            logger.error(f"Redundant processing failed: {str(e)}")
            return {
                "success": False,
                "error": f"Redundant processing failed: {str(e)}"
            }

    def _execute_parallel_calls(self, service, image_data: str, image_format: str, prompt: str, model: str, count: int) -> List[dict]:
        """Execute multiple parallel API calls"""
        results = []
        
        # Use ThreadPoolExecutor for parallel API calls
        with concurrent.futures.ThreadPoolExecutor(max_workers=count) as executor:
            # Submit all calls
            futures = []
            for i in range(count):
                future = executor.submit(
                    service.process_image_with_text,
                    image_data=image_data,
                    prompt=prompt,
                    model=model,
                    image_format=image_format
                )
                futures.append(future)
            
            # Collect results
            for i, future in enumerate(futures):
                try:
                    result = future.result(timeout=120)  # 2 minute timeout per call
                    logger.info(f"✅ Redundancy call {i+1} completed")
                    results.append(result)
                except Exception as e:
                    logger.error(f"❌ Redundancy call {i+1} failed: {e}")
                    results.append({
                        "success": False,
                        "error": f"API call failed: {str(e)}",
                        "extracted_text": ""
                    })
        
        return results

    def _analyze_redundancy_consensus(self, results: List[dict], model: str, service) -> dict:
        """Analyze multiple results to find consensus and confidence"""
        
        # Filter successful results
        successful_results = [r for r in results if r.get("success", False)]
        
        if not successful_results:
            return {
                "success": False,
                "error": "All redundancy calls failed",
                "metadata": {
                    "redundancy_analysis": {
                        "total_calls": len(results),
                        "successful_calls": 0,
                        "failed_calls": len(results)
                    }
                }
            }
        
        # Extract text from successful results
        texts = [r.get("extracted_text", "") for r in successful_results]
        
        # Perform consensus analysis to get word confidence mapping
        consensus_text, word_confidence_map = self._calculate_consensus(texts)
        
        # Calculate overall confidence
        overall_confidence = sum(word_confidence_map.values()) / len(word_confidence_map) if word_confidence_map else 0.0
        
        # Find the best individual result to preserve its formatting
        # Choose the result with the highest confidence or longest text if confidence is similar
        best_result_index = 0
        best_score = 0
        
        for i, result in enumerate(successful_results):
            # Score based on text length and confidence (if available)
            text_length_score = len(result.get("extracted_text", ""))
            confidence_score = result.get("confidence_score", 0.5) * 1000  # Weight confidence higher
            total_score = text_length_score + confidence_score
            
            if total_score > best_score:
                best_score = total_score
                best_result_index = i
        
        # Use the best individual result's text to preserve formatting
        best_formatted_text = successful_results[best_result_index].get("extracted_text", "")
        
        # Aggregate token usage
        total_tokens = sum(r.get("tokens_used", 0) for r in successful_results)
        
        return {
            "success": True,
            "extracted_text": best_formatted_text,
            "model_used": model,
            "service_type": "llm",
            "tokens_used": total_tokens,
            "confidence_score": overall_confidence,
            "metadata": {
                "redundancy_enabled": True,
                "redundancy_count": len(results),
                "processing_mode": "best_formatted",
                "best_result_used": best_result_index + 1,
                "redundancy_analysis": {
                    "total_calls": len(results),
                    "successful_calls": len(successful_results),
                    "failed_calls": len(results) - len(successful_results),
                    "consensus_text": consensus_text,
                    "best_formatted_text": best_formatted_text,
                    "best_result_index": best_result_index,
                    "word_confidence_map": word_confidence_map,
                    "individual_results": [
                        {
                            "success": r.get("success", False),
                            "text": r.get("extracted_text", ""),
                            "tokens": r.get("tokens_used", 0),
                            "error": r.get("error")
                        }
                        for r in results
                    ]
                }
            }
        }

    def _calculate_consensus(self, texts: List[str]) -> tuple:
        """Calculate consensus text and word-level confidence scores"""
        
        if len(texts) == 1:
            # Only one result, perfect confidence
            words = texts[0].split()
            confidence_map = {f"word_{i}": 1.0 for i, word in enumerate(words)}
            return texts[0], confidence_map
        
        # Tokenize all texts into words
        all_word_lists = [self._tokenize_text(text) for text in texts]
        
        # Find the longest common structure
        consensus_words = []
        word_confidence_map = {}
        
        # Use the first text as the base structure
        base_words = all_word_lists[0] if all_word_lists else []
        
        for i, base_word in enumerate(base_words):
            # Check how many other texts have a similar word at similar position
            matches = [base_word]
            
            for other_words in all_word_lists[1:]:
                # Look for similar word in nearby positions
                match_found = False
                search_range = min(3, len(other_words))  # Search within 3 positions
                
                for j in range(max(0, i-search_range), min(len(other_words), i+search_range+1)):
                    if j < len(other_words):
                        similarity = SequenceMatcher(None, base_word.lower(), other_words[j].lower()).ratio()
                        if similarity > 0.8:  # 80% similarity threshold
                            matches.append(other_words[j])
                            match_found = True
                            break
                
                if not match_found:
                    matches.append("")  # No match found
            
            # Calculate confidence based on agreement
            non_empty_matches = [m for m in matches if m.strip()]
            confidence = len(non_empty_matches) / len(texts)
            
            # Choose the most common word (or first if tie)
            if non_empty_matches:
                # Find most frequent word
                word_counts = {}
                for word in non_empty_matches:
                    word_counts[word] = word_counts.get(word, 0) + 1
                
                consensus_word = max(word_counts.items(), key=lambda x: x[1])[0]
                consensus_words.append(consensus_word)
                word_confidence_map[f"word_{i}"] = confidence
        
        consensus_text = " ".join(consensus_words)
        return consensus_text, word_confidence_map

    def _tokenize_text(self, text: str) -> List[str]:
        """Simple tokenization that preserves meaningful words"""
        # Remove extra whitespace and split on whitespace
        words = re.findall(r'\S+', text.strip())
        return words 