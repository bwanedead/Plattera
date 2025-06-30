"""
Text Processing Utilities
========================

Reusable text processing functions for pipeline operations.
"""

import json
import logging
from typing import List
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


def is_json_result(text: str) -> bool:
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


def are_json_results(texts: List[str]) -> bool:
    """Check if all texts are JSON format"""
    if not texts:
        return False
    return all(is_json_result(text) for text in texts)


def is_llm_refusal_or_failed(text: str) -> bool:
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


def filter_valid_extractions(texts: List[str]) -> List[str]:
    """
    Filter out LLM refusals and failed extractions from text list.
    
    Also filters out texts that are significantly shorter than the median,
    as they're likely failed extractions.
    """
    if not texts:
        return texts
    
    logger.info(f"📊 Filtering {len(texts)} successful results for quality...")
    
    # First pass: Remove obvious refusals and very short texts
    filtered_texts = []
    refusal_count = 0
    for i, text in enumerate(texts):
        if is_llm_refusal_or_failed(text):
            refusal_count += 1
            logger.warning(f"  ❌ Result {i+1}: Filtered as refusal/failed (length: {len(text.split())} words)")
        else:
            filtered_texts.append(text)
            logger.info(f"  ✅ Result {i+1}: Passed basic validation (length: {len(text.split())} words)")
    
    if len(filtered_texts) <= 1:
        logger.info(f"📋 Quality filtering complete: {len(filtered_texts)} results remaining (too few for length comparison)")
        return filtered_texts
    
    # Second pass: Remove texts that are significantly shorter than others
    word_counts = [len(text.split()) for text in filtered_texts]
    median_words = sorted(word_counts)[len(word_counts) // 2]
    threshold = median_words * 0.3
    
    logger.info(f"📐 Length analysis: median={median_words} words, threshold={threshold:.1f} words (30% of median)")
    
    # Filter out texts with less than 30% of median word count
    final_texts = []
    length_filtered_count = 0
    for i, text in enumerate(filtered_texts):
        word_count = len(text.split())
        if word_count >= threshold:
            final_texts.append(text)
            logger.info(f"  ✅ Result {i+1}: Passed length filter ({word_count} >= {threshold:.1f} words)")
        else:
            length_filtered_count += 1
            logger.warning(f"  ❌ Result {i+1}: Filtered as too short ({word_count} < {threshold:.1f} words)")
    
    total_filtered = refusal_count + length_filtered_count
    logger.info(f"📋 Quality filtering complete: {len(final_texts)}/{len(texts)} results kept ({refusal_count} refusals + {length_filtered_count} too short = {total_filtered} filtered)")
    
    return final_texts if final_texts else filtered_texts


def calculate_text_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity between two texts using sequence matching.
    
    Returns:
        float: Similarity score between 0.0 and 1.0
    """
    if not text1 or not text2:
        return 0.0
    
    return SequenceMatcher(None, text1, text2).ratio() 