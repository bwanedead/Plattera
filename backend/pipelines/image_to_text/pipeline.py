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
import string
import itertools
from .image_processor import enhance_for_character_recognition

logger = logging.getLogger(__name__)

# 🔴 CONSENSUS PREPROCESSING UTILITIES 🔴
# =======================================
def _preprocess_text(raw: str) -> str:
    """
    Join hyphen-linebreak splits & collapse whitespace.
    
    Handles cases like:
    - 'considera-\n    tions' → 'considerations'
    - Multiple whitespace → single space
    """
    # Join 'word-\n    more' → 'wordmore'
    text = re.sub(r'(\w+)-\s*\n\s*(\w+)', r'\1\2', raw)
    # Unify all whitespace to single spaces
    return re.sub(r'\s+', ' ', text)

def _normalize_token(token: str) -> str:
    """
    Lower-case, strip leading/trailing punctuation for comparison.
    
    Handles cases like:
    - 'less:' vs 'less.' → both become 'less'
    - 'Word,' vs 'word' → both become 'word'
    """
    return token.strip(string.punctuation).lower()

def _build_context_key(tokens: List[str], idx: int, win: int = 5) -> tuple:
    """
    Return a tuple of 11 tokens: 5 left, token, 5 right (normalised).
    
    This creates a unique fingerprint for each word based on its context.
    Used to match words that appear in the same context across drafts,
    even when SequenceMatcher gets confused by insertions/deletions.
    """
    pad = "␢"  # Special padding token for out-of-bounds positions
    left = [_normalize_token(tokens[i]) if i >= 0 else pad
            for i in range(idx - win, idx)]
    token = [_normalize_token(tokens[idx])]
    right = [_normalize_token(tokens[i]) if i < len(tokens) else pad
             for i in range(idx + 1, idx + win + 1)]
    return tuple(left + token + right)

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
        
        # Perform consensus analysis to get word confidence mapping
        consensus_text, word_confidence_map, word_alternatives = self._calculate_consensus(filtered_texts)
        
        # Calculate overall confidence
        overall_confidence = sum(word_confidence_map.values()) / len(word_confidence_map) if word_confidence_map else 0.0
        
        # Find the best individual result from filtered results
        # Map filtered texts back to their original results
        filtered_results = []
        for result in successful_results:
            result_text = result.get("extracted_text", "")
            if result_text in filtered_texts:
                filtered_results.append(result)
        
        # Choose the result with the highest confidence or longest text if confidence is similar
        best_result_index = 0
        best_score = 0
        
        for i, result in enumerate(filtered_results):
            # Score based on text length and confidence (if available)
            text_length_score = len(result.get("extracted_text", ""))
            confidence_score = result.get("confidence_score", 0.5) * 1000  # Weight confidence higher
            total_score = text_length_score + confidence_score
            
            if total_score > best_score:
                best_score = total_score
                best_result_index = i
        
        # Use the best filtered result's text to preserve formatting
        best_formatted_text = filtered_results[best_result_index].get("extracted_text", "") if filtered_results else consensus_text
        
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
                    "valid_extractions": len(filtered_texts),
                    "filtered_out": len(successful_results) - len(filtered_texts),
                    "failed_calls": len(results) - len(successful_results),
                    "consensus_text": consensus_text,
                    "best_formatted_text": best_formatted_text,
                    "best_result_index": best_result_index,
                    "word_confidence_map": word_confidence_map,
                    "word_alternatives": word_alternatives,
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
        🔴 IMPROVED CONSENSUS ALGORITHM - PUNCTUATION & HYPHEN AWARE 🔴
        ==============================================================
        
        Enhanced alignment that handles:
        - Hyphen line-breaks: 'considera-\n  tions' → 'considerations'
        - Punctuation differences: 'less:' vs 'less.' → treated as same
        - Neighbor word confusion: ignores inserts/deletes to prevent drift
        
        ALGORITHM:
        0. Pre-process all drafts (join hyphens, normalize whitespace)
        1. Use longest text as base template (preserves formatting)
        2. Align on normalized tokens, ignore pure inserts/deletes
        3. Build word-to-word mappings based on punctuation-agnostic comparison
        4. Calculate confidence from normalized matches
        5. Generate alternatives only from genuinely different words
        
        Returns:
            tuple: (consensus_text, confidence_map, word_alternatives)
        """
        
        # Step 0: Pre-process all drafts
        prepared_texts = [_preprocess_text(text) for text in texts]
        
        if len(prepared_texts) == 1:
            # Single result - perfect confidence for all words
            words = re.findall(r'\S+', prepared_texts[0])
            confidence_map = {f"word_{i}": 1.0 for i in range(len(words))}
            word_alternatives = {}  # No alternatives for single result
            return prepared_texts[0], confidence_map, word_alternatives

        # Step 1: Use longest text as base to preserve document structure
        base_index = max(range(len(prepared_texts)), key=lambda i: len(prepared_texts[i]))
        base_text = prepared_texts[base_index]
        base_tokens = re.findall(r'\S+', base_text)
        base_normalized = [_normalize_token(token) for token in base_tokens]
        
        # Get word positions in base text for replacement (skip pure punctuation)
        word_spans = []
        for match in re.finditer(r'\S+', base_text):
            token = match.group(0)
            if _normalize_token(token):  # Skip punctuation-only tokens
                word_spans.append(match.span())
        
        # Step 2: Initialize candidate lists - each base word starts with itself
        word_candidates = [[base_tokens[i]] for i in range(len(base_normalized))]

        # Step 3: Align every other draft to the base using normalized tokens
        for i, draft_text in enumerate(prepared_texts):
            if i == base_index:
                continue  # Skip the base text itself
                
            other_tokens = re.findall(r'\S+', draft_text)
            other_normalized = [_normalize_token(token) for token in other_tokens]
            
            # Use SequenceMatcher on normalized tokens for better alignment
            matcher = SequenceMatcher(None, base_normalized, other_normalized, autojunk=False)
            
            # Process alignment opcodes - only handle equal and same-length replace
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag == "equal" or (tag == "replace" and (i2 - i1) == (j2 - j1)):
                    # Safe 1-to-1 word mapping
                    for k in range(i2 - i1):
                        word_candidates[i1 + k].append(other_tokens[j1 + k])
                        
                # Note: "insert" and "delete" operations are ignored on purpose
                # This prevents neighbor words from drifting into wrong positions

        # ---------- PASS-2: CONTEXT-ANCHOR CORRECTION ----------
        # Fix alignment errors by matching words with identical 5-word context
        prepared_token_lists = [re.findall(r'\S+', t) for t in prepared_texts]

        # Build lookup tables for every non-base draft
        ctx_lookups = []
        for d_idx, tok_list in enumerate(prepared_token_lists):
            if d_idx == base_index:
                ctx_lookups.append(None)
                continue
            tbl = {}
            for i, _ in enumerate(tok_list):
                ck = _build_context_key(tok_list, i)
                if ck in tbl:
                    tbl[ck] = None          # duplicate – mark as ambiguous
                else:
                    tbl[ck] = i
            ctx_lookups.append(tbl)

        # Walk the base tokens again - add context matches
        for b_idx, b_tok in enumerate(base_tokens):
            ck = _build_context_key(base_tokens, b_idx)
            for d_idx, lookup in enumerate(ctx_lookups):
                if lookup is None:
                    continue
                match_idx = lookup.get(ck)
                if match_idx is None:
                    continue
                # Found a context match - add the token as candidate
                matched_token = prepared_token_lists[d_idx][match_idx]
                if matched_token not in word_candidates[b_idx]:
                    word_candidates[b_idx].append(matched_token)

        # Step 4: Calculate confidence and find consensus for each word
        confidence_map = {}
        consensus_replacements = {}
        word_alternatives = {}
        total_drafts = len(prepared_texts)

        for idx, candidates in enumerate(word_candidates):
            if idx >= len(base_tokens):
                continue  # Safety check
                
            base_token = base_tokens[idx]
            base_norm = base_normalized[idx]
            word_id = f"word_{idx}"
            
            # Calculate confidence based on normalized matches
            exact_matches = sum(1 for word in candidates if _normalize_token(word) == base_norm)
            confidence = exact_matches / total_drafts
            confidence_map[word_id] = confidence

            # Store alternatives - only different normalized forms
            unique_alternatives = {}
            for word in candidates:
                norm = _normalize_token(word)
                if norm != base_norm and norm not in unique_alternatives:
                    unique_alternatives[norm] = word  # Keep first spelling of each variant
            
            # Only store alternatives if there are actual differences
            if unique_alternatives:
                word_alternatives[word_id] = list(unique_alternatives.values())

            # Find consensus word (most common normalized form)
            if len(candidates) > 1:
                # Count occurrences by normalized form
                norm_counts = {}
                for word in candidates:
                    norm = _normalize_token(word)
                    norm_counts[norm] = norm_counts.get(norm, 0) + 1
                
                # Get most common normalized form
                most_common_norm = max(norm_counts.items(), key=lambda x: x[1])[0]
                
                # Find original case version of most common normalized form
                consensus_word = next(word for word in candidates 
                                    if _normalize_token(word) == most_common_norm)
                
                # Only replace if consensus differs from base word
                if consensus_word != base_token:
                    consensus_replacements[idx] = consensus_word

        # Step 5: Build consensus text by applying replacements
        consensus_text = base_text
        
        # Apply replacements from right to left to maintain character positions
        for word_index in sorted(consensus_replacements.keys(), reverse=True):
            if word_index < len(word_spans):
                start_pos, end_pos = word_spans[word_index]
                replacement_word = consensus_replacements[word_index]
                consensus_text = (consensus_text[:start_pos] + 
                                replacement_word + 
                                consensus_text[end_pos:])

        return consensus_text, confidence_map, word_alternatives 