"""
Consensus Building Module
========================

Builds final consensus text with confidence scores and alternatives.
Replaces the old segmented fuzzy consensus system.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter, defaultdict

from .align import AlignmentGrid, AlignmentColumn
from .tokenise import Token

logger = logging.getLogger(__name__)

class ConsensusBuilder:
    """Builds consensus from alignment grid"""
    
    def build_consensus(self, alignment: AlignmentGrid) -> Tuple[str, Dict[str, float], Dict[str, List[str]]]:
        """
        Build consensus text with confidence scores and alternatives
        
        Args:
            alignment: Complete alignment grid
            
        Returns:
            Tuple of (consensus_text, confidence_map, alternatives_map)
        """
        if not alignment.columns:
            logger.warning("Empty alignment grid")
            return "", {}, {}
        
        consensus_tokens = []
        confidence_map = {}
        alternatives_map = {}
        
        logger.info(f"🔨 Building consensus from {len(alignment.columns)} aligned columns")
        
        for col_idx, column in enumerate(alignment.columns):
            modal_token, confidence, alternatives = self._process_column(column, col_idx)
            
            if modal_token is not None:
                consensus_tokens.append(modal_token)
                word_key = f"word_{len(consensus_tokens)-1}"
                confidence_map[word_key] = confidence
                
                if alternatives:
                    alternatives_map[word_key] = alternatives
        
        # Convert tokens back to text
        consensus_text = self._tokens_to_text(consensus_tokens)
        
        logger.info(f"📝 Consensus built: {len(consensus_tokens)} tokens, {len(alternatives_map)} with alternatives")
        logger.info(f"📊 Average confidence: {sum(confidence_map.values()) / len(confidence_map):.3f}")
        
        return consensus_text, confidence_map, alternatives_map
    
    def _process_column(self, column: AlignmentColumn, col_idx: int) -> Tuple[Optional[Token], float, List[str]]:
        """
        Process a single alignment column to get modal token, confidence, and alternatives
        
        Args:
            column: Alignment column to process
            col_idx: Column index for logging
            
        Returns:
            Tuple of (modal_token, confidence, alternative_texts)
        """
        # Filter out gaps (None values)
        non_gap_tokens = [token for token in column.tokens if token is not None]
        
        if not non_gap_tokens:
            # Pure gap column - skip
            return None, 0.0, []
        
        # Count token occurrences (normalized)
        token_counts = Counter()
        token_to_original = {}
        
        for token in non_gap_tokens:
            normalized = self._normalize_token_text(token.text)
            token_counts[normalized] += 1
            
            # Keep track of original token for the normalized version
            if normalized not in token_to_original:
                token_to_original[normalized] = token
        
        # Find modal token (most common)
        modal_normalized, modal_count = token_counts.most_common(1)[0]
        modal_token = token_to_original[modal_normalized]
        
        # Calculate confidence
        total_tokens = len(non_gap_tokens)
        confidence = modal_count / total_tokens
        
        # Find alternatives (other tokens)
        alternatives = []
        for token in non_gap_tokens:
            normalized = self._normalize_token_text(token.text)
            if normalized != modal_normalized and token.text not in alternatives:
                alternatives.append(token.text)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_alternatives = []
        for alt in alternatives:
            if alt.lower() not in seen:
                seen.add(alt.lower())
                unique_alternatives.append(alt)
        
        if len(unique_alternatives) > 0:
            logger.debug(f"Column {col_idx}: '{modal_token.text}' ({confidence:.2f}) vs {unique_alternatives}")
        
        return modal_token, confidence, unique_alternatives
    
    def _normalize_token_text(self, text: str) -> str:
        """Normalize token text for comparison"""
        return text.lower().strip()
    
    def _tokens_to_text(self, tokens: List[Token]) -> str:
        """Convert tokens back to readable text with proper spacing"""
        if not tokens:
            return ""
        
        text_parts = []
        for i, token in enumerate(tokens):
            # Add space before token (except first)
            if i > 0:
                # Smart spacing rules
                prev_token = tokens[i-1]
                
                # No space after opening punctuation or before closing punctuation
                if (prev_token.type == "PUN" and prev_token.text in "([{") or \
                   (token.type == "PUN" and token.text in ")]}"):
                    pass  # No space
                # No space before sentence punctuation
                elif token.type == "PUN" and token.text in ".,;:!?":
                    pass  # No space
                else:
                    text_parts.append(" ")
            
            text_parts.append(token.text)
        
        return "".join(text_parts) 