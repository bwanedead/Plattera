"""
Fixed Unified Path Tokenizer Module
===================================

Handles the multi-word token issue by splitting normalized tokens that contain spaces.
"""

import re
import logging
from typing import Dict, List, Tuple, Any
from dataclasses import dataclass
from nltk.tokenize import word_tokenize

logger = logging.getLogger(__name__)

@dataclass
class DirectTokenMapping:
    """Direct mapping between formatted and normalized tokens"""
    token_id: int           # Position in original formatted sequence
    formatted_token: str    # Original token with formatting
    normalized_tokens: List[str]  # List of normalized tokens (can be multiple)

class UnifiedPathTokenizerFixed:
    """Fixed tokenizer that handles multi-word normalized tokens correctly"""
    
    def __init__(self):
        self.format_mapper = None
    
    def tokenize_with_unified_path(self, text: str) -> Tuple[List[str], List[str], List[DirectTokenMapping]]:
        """
        Fixed unified tokenization path that handles multi-word normalized tokens.
        
        Returns:
            Tuple of (formatted_tokens, normalized_tokens, mappings)
        """
        if not text or not text.strip():
            return [], [], []
        
        logger.info(f"🔄 FIXED UNIFIED PATH ► Processing text: '{text[:50]}...'")
        
        # STEP 1: Get formatted tokens
        formatted_tokens = word_tokenize(text)
        logger.info(f"   📋 Formatted tokens ({len(formatted_tokens)}): {formatted_tokens}")
        
        # STEP 2: Apply normalization to each token and handle multi-word results
        all_normalized_tokens = []
        mappings = []
        
        logger.info(f"   🔧 Applying normalization to each token:")
        
        for token_id, formatted_token in enumerate(formatted_tokens):
            # Apply normalization to this token
            normalized_result = self._apply_normalization_to_token(formatted_token)
            
            # Split the normalized result into individual tokens
            if normalized_result and not normalized_result.isspace():
                # Split on whitespace to handle multi-word results
                normalized_sub_tokens = normalized_result.split()
                
                if normalized_sub_tokens:
                    logger.info(f"      [{token_id:2d}]: '{formatted_token}' → {normalized_sub_tokens}")
                    
                    # Add all normalized sub-tokens to the final list
                    all_normalized_tokens.extend(normalized_sub_tokens)
                    
                    # Create mapping with list of normalized tokens
                    mappings.append(DirectTokenMapping(
                        token_id=token_id,
                        formatted_token=formatted_token,
                        normalized_tokens=normalized_sub_tokens
                    ))
                else:
                    logger.info(f"      [{token_id:2d}]: '{formatted_token}' → [] (empty after split)")
            else:
                logger.info(f"      [{token_id:2d}]: '{formatted_token}' → [] (filtered out)")
        
        logger.info(f"   ✅ Final tokens: {len(formatted_tokens)} → {len(all_normalized_tokens)}")
        logger.info(f"   📤 Normalized tokens: {all_normalized_tokens}")
        
        return formatted_tokens, all_normalized_tokens, mappings
    
    def _apply_normalization_to_token(self, token: str) -> str:
        """
        Apply the EXACT same normalization logic as current _normalize_text() to a single token.
        """
        if not token:
            return ""
        
        # Apply the exact same steps as the current _normalize_text()
        normalized = token
        
        # Step 1: Lowercase
        normalized = normalized.lower()
        
        # Step 2: Canonicalize numbers (same regex as current)
        normalized = re.sub(r'(?<=\d)[,\s]+(?=\d)', '', normalized)
        
        # Step 3: Protect decimal points (same as current)
        normalized = re.sub(r'(?<=\d)\.(?=\d)', 'DOT', normalized)
        
        # Step 4: Replace non-alphanumeric chars with space (same as current)
        normalized = re.sub(r'[^a-z0-9\s]', ' ', normalized.replace('DOT', ' ')).replace('DOT', '.')
        
        # Step 5: Collapse spaces and strip (same as current)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized

# Updated comparison script
class CurrentApproachTokenizer:
    """Replicate the current tokenization approach exactly"""
    
    def tokenize_current_approach(self, text: str) -> List[str]:
        """Current approach: normalize whole text first, then tokenize"""
        if not text or not text.strip():
            return []
        
        # Apply normalization to whole text (current approach)
        normalized_text = self._normalize_text(text)
        
        # Tokenize the normalized text
        tokens = word_tokenize(normalized_text)
        
        return tokens
    
    def _normalize_text(self, text: str) -> str:
        """EXACT copy of current normalization logic"""
        if not text:
            return ""
        
        text = text.lower()
        
        # Canonicalize numbers before stripping punctuation
        text = re.sub(r'(?<=\d)[,\s]+(?=\d)', '', text)
        
        # Protect decimal points by replacing them with a sentinel
        text = re.sub(r'(?<=\d)\.(?=\d)', 'DOT', text)
        
        # Replace all non-alphanumeric chars (except our sentinel) with a space
        text = re.sub(r'[^a-z0-9\s]', ' ', text.replace('DOT', ' ')).replace('DOT','.')
        
        # Collapse multiple spaces into one
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        
        return text 