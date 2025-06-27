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
from typing import Tuple, List, Dict, Any
import concurrent.futures
from difflib import SequenceMatcher
import re
import string
import itertools
from .image_processor import enhance_for_character_recognition
import json
from .json_alignment import merge_drafts as merge_json_drafts  # Import new alignment system

logger = logging.getLogger(__name__)

# 🔴 CONSENSUS PROCESSING UTILITIES MOVED TO consensus.py 🔴
# ==============================================================

def _is_json_result(text: str) -> bool:
    """Check if extracted text is JSON format matching our document schema"""
    if not text or not text.strip():
        return False
    
    try:
        parsed = json.loads(text)
        return (
            isinstance(parsed, dict) and 
            "documentId" in parsed and 
            "sections" in parsed and 
            isinstance(parsed["sections"], list)
        )
    except (json.JSONDecodeError, TypeError):
        return False

def _are_json_results(texts: List[str]) -> bool:
    """Check if all texts are JSON format"""
    if not texts:
        return False
    return all(_is_json_result(text) for text in texts)

def _is_llm_refusal_or_failed(text: str) -> bool:
    """
    Detect LLM refusal responses or failed extractions.
    
    Returns True if the text appears to be a refusal message or
    significantly failed extraction that should be excluded from consensus.
    """
    if not text or len(text.strip()) < 10:
        return True
    
    text_lower = text.lower().strip()
    
    # Common LLM refusal patterns
    refusal_patterns = [
        "i'm sorry, i can't assist",
        "i cannot assist",
        "i'm unable to help",
        "i can't help with that",
        "i'm not able to",
        "i cannot provide",
        "i'm sorry, but i cannot",
        "i apologize, but i cannot",
        "i don't feel comfortable",
        "i'm not comfortable",
        "this request goes against",
        "i cannot fulfill this request",
        "i'm sorry, i cannot process",
        "unable to process",
        "cannot be processed"
    ]
    
    # Check for refusal patterns
    for pattern in refusal_patterns:
        if pattern in text_lower:
            return True
    
    # Check if text is suspiciously short (likely failed extraction)
    word_count = len(text.split())
    if word_count < 5:  # Very short responses are likely failures
        return True
    
    return False

def _filter_valid_extractions(texts: List[str]) -> List[str]:
    """
    Filter out LLM refusals and failed extractions from text list.
    
    Also filters out texts that are significantly shorter than the median,
    as they're likely failed extractions.
    """
    if not texts:
        return texts
    
    # First pass: Remove obvious refusals and very short texts
    filtered_texts = []
    for text in texts:
        if not _is_llm_refusal_or_failed(text):
            filtered_texts.append(text)
    
    if len(filtered_texts) <= 1:
        return filtered_texts  # Can't do length filtering with 1 or fewer texts
    
    # Second pass: Remove texts that are significantly shorter than others
    word_counts = [len(text.split()) for text in filtered_texts]
    median_words = sorted(word_counts)[len(word_counts) // 2]
    
    # Filter out texts with less than 30% of median word count
    # (likely failed extractions that passed the first filter)
    final_texts = []
    for text in filtered_texts:
        word_count = len(text.split())
        if word_count >= (median_words * 0.3):
            final_texts.append(text)
    
    return final_texts if final_texts else filtered_texts  # Fallback to first filter if second is too aggressive

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
                # Pass JSON mode flag for structured response
                json_mode = extraction_mode == "legal_document_json"
                result = service.process_image_with_text(
                    image_data=image_data,    # CRITICAL: base64 string
                    prompt=prompt,
                    model=model,
                    image_format=image_format,  # CRITICAL: format string
                    json_mode=json_mode  # CRITICAL: Enable structured JSON response
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
        """Get available extraction modes - DEPRECATED, use prompts.image_to_text.get_available_extraction_modes() instead"""
        # Import here to avoid circular dependencies
        from prompts.image_to_text import get_available_extraction_modes
        return get_available_extraction_modes()
    
    def process_with_redundancy(self, image_path: str, model: str = "gpt-4o", extraction_mode: str = "legal_document", 
                              enhancement_settings: dict = None, redundancy_count: int = 3, consensus_strategy: str = "sequential") -> dict:
        """
        🔴 CRITICAL REDUNDANCY PROCESSING - HEATMAP DATA GENERATOR 🔴
        ============================================================
        
        This method generates the redundancy analysis data that powers the heatmap feature.
        
        CRITICAL HEATMAP DATA GENERATED:
        - individual_results: Array of all processing attempts (needed for word alternatives)
        - consensus_text: Merged text with highest confidence words
        - best_formatted_text: Best individual result (preserves formatting)
        - best_result_index: Index of best result (for UI marking)
        - word_confidence_map: Word-level confidence scores (for heatmap coloring)
        
        HEATMAP INTEGRATION REQUIREMENTS:
        ================================
        
        1. INDIVIDUAL RESULTS (CRITICAL):
           - Each result contains full text for word alternatives
           - Success/failure status for filtering
           - Token counts for quality metrics
           - Error messages for debugging
        
        2. CONSENSUS ANALYSIS (CRITICAL):
           - Preserves document structure and formatting
           - Maps word positions for confidence calculation
           - Handles whitespace, punctuation, and special characters
           - Provides confidence scores (0.0-1.0) for each word
        
        3. RESPONSE FORMAT (CRITICAL):
           ```json
           {
             "success": true,
             "extracted_text": "best_formatted_text",  // Primary display text
             "metadata": {
               "redundancy_analysis": {
                 "individual_results": [...],    // Heatmap word alternatives
                 "consensus_text": "...",        // Heatmap consensus view
                 "best_formatted_text": "...",   // Heatmap best view
                 "best_result_index": 0,         // Heatmap best marking
                 "word_confidence_map": {...}    // Heatmap coloring data
               }
             }
           }
           ```
        
        CRITICAL PROCESSING FLOW:
        ========================
        1. Execute parallel API calls (maintains service interface)
        2. Filter successful results (ensures data quality)
        3. Calculate consensus with position mapping (preserves structure)
        4. Generate word confidence scores (enables heatmap coloring)
        5. Select best result (provides quality reference)
        6. Package data for frontend consumption
        
        ⚠️  DO NOT MODIFY:
        - Service interface calls (breaks API integration)
        - Response format structure (breaks frontend parsing)
        - Consensus algorithm logic (breaks word mapping)
        - Error handling patterns (breaks graceful degradation)
        
        ✅ SAFE TO MODIFY:
        - Confidence calculation thresholds
        - Parallel execution parameters
        - Quality scoring metrics
        - Additional metadata fields
        """
        try:
            # Handle single redundancy by falling back to original method
            if redundancy_count <= 1:
                return self.process(image_path, model, extraction_mode, enhancement_settings)
            
            # CRITICAL: Get service and prepare image (same as original process)
            service = self._get_service_for_model(model)
            if not service:
                return {
                    "success": False,
                    "error": f"No service available for model: {model}"
                }
            
            # CRITICAL: Use same image preparation as original process
            image_data, image_format = self._prepare_image(image_path, enhancement_settings)
            if not image_data:
                return {
                    "success": False,
                    "error": "Failed to prepare image data"
                }
            
            # CRITICAL: Use same prompt as original process
            prompt = get_image_to_text_prompt(extraction_mode, model)
            
            # CRITICAL: Execute parallel calls to generate redundancy data
            logger.info(f"Processing with redundancy: {redundancy_count} parallel calls")
            # Pass JSON mode flag for structured response
            json_mode = extraction_mode == "legal_document_json"
            parallel_results = self._execute_parallel_calls(
                service, image_data, image_format, prompt, model, redundancy_count, json_mode
            )
            
            # CRITICAL: Analyze results and generate consensus data for heatmap
            return self._analyze_redundancy_consensus(parallel_results, model, service, consensus_strategy)
            
        except Exception as e:
            logger.error(f"Redundancy processing failed: {str(e)}")
            return {
                "success": False,
                "error": f"Redundancy processing failed: {str(e)}"
            }

    def _execute_parallel_calls(self, service, image_data: str, image_format: str, prompt: str, model: str, count: int, json_mode: bool = False) -> List[dict]:
        """Execute multiple API calls with staggered timing to reduce empty responses"""
        import time
        results = []
        
        # Staggered execution to avoid API congestion
        stagger_delay = 0.7  # 700ms delay between call submissions
        
        # Use ThreadPoolExecutor for parallel API calls
        with concurrent.futures.ThreadPoolExecutor(max_workers=count) as executor:
            # Submit calls with staggered timing
            futures = []
            for i in range(count):
                if i > 0:  # Add delay before subsequent calls
                    time.sleep(stagger_delay)
                    logger.info(f"🕐 Staggered call {i+1} submitted after {stagger_delay * i:.1f}s delay")
                
                future = executor.submit(
                    service.process_image_with_text,
                    image_data=image_data,
                    prompt=prompt,
                    model=model,
                    image_format=image_format,
                    json_mode=json_mode
                )
                futures.append(future)
                
                if i == 0:
                    logger.info(f"🚀 Call {i+1} submitted immediately")
            
            # Collect results (these will complete whenever they finish)
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

    def _analyze_redundancy_consensus(self, results: List[dict], model: str, service, consensus_strategy: str = 'sequential') -> dict:
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
        
        # Filter out invalid extractions
        filtered_texts = _filter_valid_extractions(texts)
        
        # Log filtering results
        filtered_count = len(successful_results) - len(filtered_texts)
        if filtered_count > 0:
            logger.warning(f"Filtered out {filtered_count} invalid extractions from {len(successful_results)} successful results")
        
        if not filtered_texts:
            return {
                "success": False,
                "error": "All texts are invalid",
                "metadata": {
                    "redundancy_analysis": {
                        "total_calls": len(results),
                        "successful_calls": 0,
                        "failed_calls": len(results)
                    }
                }
            }
        
        # 🆕 NEW: Check if we have JSON-structured documents
        if _are_json_results(filtered_texts):
            logger.info("🔥 JSON documents detected - using new semantic alignment system")
            return self._analyze_json_consensus(results, successful_results, filtered_texts, model)
        else:
            logger.info("📝 Plain text documents - using existing consensus system")
            return self._analyze_text_consensus(results, successful_results, filtered_texts, model, consensus_strategy)
    
    def _analyze_json_consensus(self, results: List[dict], successful_results: List[dict], 
                               filtered_texts: List[str], model: str) -> dict:
        """Analyze JSON documents using the new semantic alignment system"""
        try:
            # Parse JSON documents
            json_documents = []
            for text in filtered_texts:
                try:
                    parsed = json.loads(text)
                    json_documents.append(parsed)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON document: {e}")
                    continue
            
            if not json_documents:
                raise ValueError("No valid JSON documents found")
            
            # Use new alignment system
            logger.info(f"🎯 Running semantic alignment on {len(json_documents)} JSON documents")
            alignment_result = merge_json_drafts(json_documents, {"debug": True})
            
            # Convert alignment result to consensus format
            consensus_text = alignment_result.get("consensus", "")
            confidence_list = alignment_result.get("confidence", [])
            alternatives_dict = alignment_result.get("alternatives", {})
            
            # Convert confidence list to word map format (for compatibility)
            word_confidence_map = {}
            for i, conf in enumerate(confidence_list):
                word_confidence_map[f"word_{i}"] = conf
            
            # Convert alternatives dict to word alternatives format
            word_alternatives = {}
            for word_idx, alts in alternatives_dict.items():
                word_alternatives[f"word_{word_idx}"] = alts
            
            # Calculate overall confidence
            overall_confidence = sum(confidence_list) / len(confidence_list) if confidence_list else 0.0
            
            # Find best result (longest JSON)
            best_result_index = 0
            best_score = 0
            filtered_results = []
            
            for result in successful_results:
                result_text = result.get("extracted_text", "")
                if result_text in filtered_texts:
                    filtered_results.append(result)
            
            for i, result in enumerate(filtered_results):
                score = len(result.get("extracted_text", ""))
                if score > best_score:
                    best_score = score
                    best_result_index = i
            
            best_formatted_text = filtered_results[best_result_index].get("extracted_text", "") if filtered_results else filtered_texts[0]
            
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
                    "processing_mode": "json_semantic_alignment",
                    "alignment_engine": "semantic",
                    "best_result_used": best_result_index + 1,
                    "redundancy_analysis": {
                        "total_calls": len(results),
                        "successful_calls": len(successful_results),
                        "valid_extractions": len(filtered_texts),
                        "filtered_out": len(successful_results) - len(filtered_texts),
                        "failed_calls": len(results) - len(successful_results),
                        "consensus_text": consensus_text,
                        "best_formatted_text": best_formatted_text,
                        "best_result_index": best_result_index,
                        "word_confidence_map": word_confidence_map,
                        "word_alternatives": word_alternatives,
                        "json_alignment_result": alignment_result,  # Full alignment data
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
            
        except Exception as e:
            logger.error(f"❌ JSON alignment failed: {str(e)}")
            # Fallback to text consensus
            logger.warning("🚨 Falling back to text consensus due to JSON alignment failure")
            return self._analyze_text_consensus(results, successful_results, filtered_texts, model, 'sequential')
    
    def _analyze_text_consensus(self, results: List[dict], successful_results: List[dict], 
                               filtered_texts: List[str], model: str, consensus_strategy: str) -> dict:
        """
        For non-JSON mode: Just return the best result without consensus processing.
        
        Consensus/alignment is only useful for JSON-structured documents.
        For plain text, we just pick the best result (longest/highest quality).
        """
        logger.info("📄 Non-JSON mode: Selecting best result (no consensus processing)")
        
        # Find the best individual result from filtered results
        filtered_results = []
        for result in successful_results:
            result_text = result.get("extracted_text", "")
            if result_text in filtered_texts:
                filtered_results.append(result)
        
        if not filtered_results:
            # Fallback to any successful result
            filtered_results = successful_results
        
        # Choose the result with the longest text (best extraction)
        best_result_index = 0
        best_score = 0
        
        for i, result in enumerate(filtered_results):
            # Score based on text length (longer = better extraction)
            text_length_score = len(result.get("extracted_text", ""))
            
            if text_length_score > best_score:
                best_score = text_length_score
                best_result_index = i
        
        best_result = filtered_results[best_result_index] if filtered_results else {"extracted_text": "No valid results"}
        best_formatted_text = best_result.get("extracted_text", "")
        
        # Aggregate token usage
        total_tokens = sum(r.get("tokens_used", 0) for r in successful_results)
        
        return {
            "success": True,
            "extracted_text": best_formatted_text,
            "model_used": model,
            "service_type": "llm", 
            "tokens_used": total_tokens,
            "confidence_score": 1.0,  # Single result = full confidence
            "metadata": {
                "redundancy_enabled": True,
                "redundancy_count": len(results),
                "processing_mode": "best_result_selection",
                "best_result_used": best_result_index + 1,
                "redundancy_analysis": {
                    "total_calls": len(results),
                    "successful_calls": len(successful_results),
                    "valid_extractions": len(filtered_texts),
                    "filtered_out": len(successful_results) - len(filtered_texts),
                    "failed_calls": len(results) - len(successful_results),
                    "best_formatted_text": best_formatted_text,
                    "best_result_index": best_result_index,
                    "note": "Non-JSON mode: No consensus processing, selected best result",
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

    def _calculate_consensus(self, texts: List[str], strategy: str = 'sequential') -> tuple:
        """
        Simple fallback consensus - just return the longest text.
        
        This is only used as a fallback when JSON alignment fails.
        Real consensus/alignment should only be used for JSON documents.
        
        Args:
            texts: List of draft texts to process
            strategy: Ignored (for compatibility)
            
        Returns:
            tuple: (consensus_text, confidence_map, word_alternatives)
        """
        if not texts:
            return "", {}, {}
        
        # Just return the longest text (best extraction)
        longest_text = max(texts, key=len)
        
        # No confidence/alternatives for simple fallback
        return longest_text, {}, {} 