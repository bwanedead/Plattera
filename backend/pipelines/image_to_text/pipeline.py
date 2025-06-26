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
            parallel_results = self._execute_parallel_calls(
                service, image_data, image_format, prompt, model, redundancy_count
            )
            
            # CRITICAL: Analyze results and generate consensus data for heatmap
            return self._analyze_redundancy_consensus(parallel_results, model, service)
            
        except Exception as e:
            logger.error(f"Redundancy processing failed: {str(e)}")
            return {
                "success": False,
                "error": f"Redundancy processing failed: {str(e)}"
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
                    print(f"✅ Redundancy call {i+1} completed")
                    results.append(result)
                except Exception as e:
                    print(f"❌ Redundancy call {i+1} failed: {e}")
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
        """
        🔴 CRITICAL CONSENSUS ALGORITHM - HEATMAP CONFIDENCE GENERATOR 🔴
        ================================================================
        
        This method generates the word-level confidence data that powers heatmap coloring.
        
        CRITICAL HEATMAP OUTPUTS:
        - consensus_text: Merged text with highest confidence words (preserves formatting)
        - word_confidence_map: Dict mapping word positions to confidence scores (0.0-1.0)
        
        ALGORITHM OVERVIEW:
        ==================
        1. Select longest text as formatting template (preserves document structure)
        2. Map word positions using regex to maintain exact character positions
        3. Find corresponding words across texts using position ratios and similarity
        4. Calculate confidence as agreement percentage across all texts
        5. Build consensus by replacing disputed words with most common alternatives
        6. Generate confidence map for heatmap coloring
        
        CRITICAL HEATMAP REQUIREMENTS:
        =============================
        
        1. FORMATTING PRESERVATION:
           - Uses longest text as base to preserve line breaks, spacing, indentation
           - Maintains exact character positions for word replacement
           - Preserves document structure (headers, paragraphs, lists, etc.)
        
        2. WORD POSITION MAPPING:
           - Each word gets unique identifier: word_0, word_1, word_2, etc.
           - Position mapping allows heatmap to highlight specific words
           - Confidence scores enable color coding (green=high, yellow=medium, red=low)
        
        3. CONFIDENCE CALCULATION:
           - confidence = agreement_count / total_texts
           - 1.0 = Perfect agreement (all texts have same word)
           - 0.5 = Half agreement (50% of texts agree)
           - 0.0 = No agreement (all texts have different words)
        
        4. SIMILARITY MATCHING:
           - Uses SequenceMatcher with 70% threshold for fuzzy word matching
           - Handles OCR variations (e.g., "Property" vs "Properly")
           - Position-based search within ±2 word range for alignment
        
        HEATMAP COLOR MAPPING:
        =====================
        - High Confidence (0.8-1.0): Green background (rgba(34, 197, 94, 0.1-0.3))
        - Medium Confidence (0.5-0.79): Yellow background (rgba(234, 179, 8, 0.2-0.5))
        - Low Confidence (0.0-0.49): Red background (rgba(239, 68, 68, 0.3-0.7))
        
        RETURN FORMAT (CRITICAL):
        ========================
        Returns tuple: (consensus_text, word_confidence_map)
        
        consensus_text: str - Merged text with best words, preserving formatting
        word_confidence_map: dict - {"word_0": 0.8, "word_1": 0.6, "word_2": 1.0, ...}
        
        ⚠️  DO NOT MODIFY:
        - Word position mapping logic (breaks heatmap highlighting)
        - Confidence calculation formula (breaks color accuracy)
        - Formatting preservation logic (breaks document structure)
        - Return format (breaks frontend parsing)
        
        ✅ SAFE TO MODIFY:
        - Similarity threshold (currently 70%)
        - Search range for word matching (currently ±2)
        - Confidence calculation weights
        - Additional metadata in confidence map
        """
        
        if len(texts) == 1:
            # Only one result, perfect confidence for all words
            words = re.findall(r'\S+', texts[0])
            confidence_map = {f"word_{i}": 1.0 for i, word in enumerate(words)}
            return texts[0], confidence_map
        
        # CRITICAL: Use longest text as base to preserve document structure
        base_text = max(texts, key=len)
        
        # CRITICAL: Find all word positions to maintain exact character positions
        word_pattern = r'\S+'  # Matches any non-whitespace sequence
        base_words = []
        word_positions = []  # (start_char, end_char) for each word
        
        for match in re.finditer(word_pattern, base_text):
            base_words.append(match.group())
            word_positions.append((match.start(), match.end()))
        
        # CRITICAL: Generate consensus and confidence for each word position
        consensus_replacements = {}  # word_index -> replacement_word
        word_confidence_map = {}     # word_index -> confidence_score
        
        for i, (base_word, (start_pos, end_pos)) in enumerate(zip(base_words, word_positions)):
            # Collect corresponding words from all texts at similar positions
            word_candidates = [base_word]  # Start with base word
            
            # CRITICAL: Find corresponding words in other texts
            for other_text in texts:
                if other_text == base_text:
                    continue
                    
                # Find words in other texts around the same relative position
                other_words = re.findall(word_pattern, other_text)
                
                if other_words:
                    # CRITICAL: Calculate relative position for word alignment
                    relative_pos = i / len(base_words) if len(base_words) > 0 else 0
                    target_index = int(relative_pos * len(other_words))
                    target_index = min(target_index, len(other_words) - 1)
                    
                    # CRITICAL: Search within range for similar words
                    search_range = min(2, len(other_words))  # ±2 word search window
                    for j in range(max(0, target_index - search_range), 
                                 min(len(other_words), target_index + search_range + 1)):
                        candidate_word = other_words[j]
                        
                        # CRITICAL: Use similarity matching for OCR variations
                        similarity = SequenceMatcher(None, base_word.lower(), candidate_word.lower()).ratio()
                        if similarity > 0.7:  # 70% similarity threshold
                            word_candidates.append(candidate_word)
                            break
            
            # CRITICAL: Calculate confidence and choose consensus word
            non_empty_candidates = [w for w in word_candidates if w.strip()]
            confidence = len(non_empty_candidates) / len(texts)  # Agreement percentage
            
            if len(non_empty_candidates) > 1:
                # Find most common word among candidates
                word_counts = {}
                for word in non_empty_candidates:
                    word_counts[word] = word_counts.get(word, 0) + 1
                
                consensus_word = max(word_counts.items(), key=lambda x: x[1])[0]
                
                # Only replace if consensus word is different from base
                if consensus_word != base_word:
                    consensus_replacements[i] = consensus_word
            
            # CRITICAL: Store confidence for heatmap coloring
            word_confidence_map[f"word_{i}"] = confidence
        
        # CRITICAL: Build consensus text while preserving exact formatting
        consensus_text = base_text
        
        # Apply replacements from right to left to maintain character positions
        for word_index in sorted(consensus_replacements.keys(), reverse=True):
            start_pos, end_pos = word_positions[word_index]
            replacement_word = consensus_replacements[word_index]
            consensus_text = consensus_text[:start_pos] + replacement_word + consensus_text[end_pos:]
        
        return consensus_text, word_confidence_map 