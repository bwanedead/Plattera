"""
Unified Path Tokenizer Module
============================

Alternative tokenization approach that creates normalized tokens as derivatives 
of formatted tokens with direct 1:1 mapping.

Path: original text -> formatted tokens -> normalized tokens (per token)
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
    token_id: int           # Position in sequence
    formatted_token: str    # Original token with formatting
    normalized_token: str   # Normalized derivative

class UnifiedPathTokenizer:
    """Tokenizer using unified path: text -> formatted tokens -> normalized tokens"""
    
    def __init__(self):
        self.format_mapper = None  # We'll focus just on tokenization for now
    
    def tokenize_with_unified_path(self, text: str) -> Tuple[List[str], List[str], List[DirectTokenMapping]]:
        """
        Unified tokenization path: original text -> formatted tokens -> normalized tokens
        
        This creates direct 1:1 mapping while preserving the exact same normalization 
        logic as the current system.
        
        Returns:
            Tuple of (formatted_tokens, normalized_tokens, mappings)
        """
        if not text or not text.strip():
            return [], [], []
        
        logger.info(f"🔄 UNIFIED PATH ► Processing text: '{text[:50]}...'")
        
        # STEP 1: Get formatted tokens (same as current _tokenize_original_text)
        formatted_tokens = word_tokenize(text)
        logger.info(f"   📋 Formatted tokens ({len(formatted_tokens)}): {formatted_tokens}")
        
        # STEP 2: Apply existing normalization logic to each formatted token
        normalized_tokens = []
        mappings = []
        
        logger.info(f"   🔧 Applying normalization to each token:")
        
        for token_id, formatted_token in enumerate(formatted_tokens):
            # Apply the EXACT same normalization as current _normalize_text() but to each token
            normalized_token = self._apply_normalization_to_token(formatted_token)
            
            logger.info(f"      [{token_id:2d}]: '{formatted_token}' → '{normalized_token}'")
            
            # Only keep non-empty normalized tokens
            if normalized_token and not normalized_token.isspace():
                normalized_tokens.append(normalized_token)
                mappings.append(DirectTokenMapping(
                    token_id=token_id,
                    formatted_token=formatted_token,
                    normalized_token=normalized_token
                ))
            else:
                logger.info(f"           ⏭️ Filtered out (empty/whitespace)")
        
        logger.info(f"   ✅ Final tokens: {len(formatted_tokens)} → {len(normalized_tokens)}")
        logger.info(f"   📤 Normalized tokens: {normalized_tokens}")
        
        return formatted_tokens, normalized_tokens, mappings
    
    def _apply_normalization_to_token(self, token: str) -> str:
        """
        Apply the EXACT same normalization logic as current _normalize_text() to a single token.
        
        This preserves the current normalization behavior exactly.
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

# For comparison, replicate the current approach
class CurrentApproachTokenizer:
    """Replicate the current tokenization approach exactly"""
    
    def tokenize_current_approach(self, text: str) -> List[str]:
        """
        Current approach: normalize whole text first, then tokenize
        """
        if not text or not text.strip():
            return []
        
        logger.info(f"🔄 CURRENT APPROACH ► Processing text: '{text[:50]}...'")
        
        # Apply normalization to whole text (current approach)
        normalized_text = self._normalize_text(text)
        logger.info(f"   🔧 Normalized text: '{normalized_text}'")
        
        # Tokenize the normalized text
        tokens = word_tokenize(normalized_text)
        logger.info(f"   📤 Final tokens ({len(tokens)}): {tokens}")
        
        return tokens
    
    def _normalize_text(self, text: str) -> str:
        """
        EXACT copy of current normalization logic from json_draft_tokenizer.py
        """
        if not text:
            return ""
        
        original_text = text
        logger.debug(f"🔍 NORMALIZATION DEBUG ► Input: '{text[:50]}...'")
        
        text = text.lower()
        logger.debug(f"   After lowercase: '{text[:50]}...'")
        
        # Canonicalize numbers before stripping punctuation
        text = re.sub(r'(?<=\d)[,\s]+(?=\d)', '', text)
        logger.debug(f"   After number canonicalization: '{text[:50]}...'")
        
        # Protect decimal points by replacing them with a sentinel
        text = re.sub(r'(?<=\d)\.(?=\d)', 'DOT', text)
        
        # Replace all non-alphanumeric chars (except our sentinel) with a space
        text = re.sub(r'[^a-z0-9\s]', ' ', text.replace('DOT', ' ')).replace('DOT','.')
        logger.debug(f"   After punctuation removal: '{text[:50]}...'")
        
        # Collapse multiple spaces into one
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        logger.debug(f"   Final normalized: '{text[:50]}...'")
        
        return text 