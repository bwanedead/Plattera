"""
Format Mapping Module
====================

Handles preservation and restoration of formatting during tokenization and alignment.
Maintains character-level mapping between original text and normalized tokens.

This module is completely isolated and doesn't modify any existing alignment logic.
"""

import re
import logging
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TokenPosition:
    """Represents a token's position and formatting in original text"""
    token_index: int        # Index in the token list
    start_char: int         # Start position in original text
    end_char: int           # End position in original text
    original_text: str      # Original text with formatting (e.g., "37°")
    normalized_text: str    # Normalized token text (e.g., "37")


@dataclass
class FormatMapping:
    """Complete mapping for a single draft"""
    draft_id: str
    original_text: str
    token_positions: List[TokenPosition]
    
    def get_position_for_token(self, token_index: int) -> Optional[TokenPosition]:
        """Get position info for a specific token index"""
        for pos in self.token_positions:
            if pos.token_index == token_index:
                return pos
        return None


class FormatMapper:
    """Handles format preservation using universal positional mapping
    
    Maps tokens to original text purely by position, regardless of content.
    This approach works universally for any text without requiring content-specific logic.
    """
    
    def __init__(self):
        """Initialize the format mapper with direct mapping approach"""
        pass  # No patterns needed - we use direct character-level mapping
    
    def create_mapping(self, draft_id: str, original_text: str, normalized_tokens: List[str]) -> FormatMapping:
        """
        Create content-based mapping between original text and normalized tokens.
        
        This approach maps tokens to original words by content matching, not just position.
        """
        logger.debug(f"Creating content-based mapping for draft {draft_id} with {len(normalized_tokens)} tokens")
        
        if not original_text or not normalized_tokens:
            return FormatMapping(draft_id, original_text, [])
        
        # Find all words in the original text
        word_matches = list(re.finditer(r'\S+', original_text))
        
        token_positions = []
        used_word_positions = set()
        
        # Create content-based mapping
        for token_idx, token in enumerate(normalized_tokens):
            # Find the best matching word in the original text
            best_match = None
            best_score = 0
            
            for word_match in word_matches:
                word_start = word_match.start()
                word_end = word_match.end()
                
                # Skip if this word position has already been used
                if (word_start, word_end) in used_word_positions:
                    continue
                
                original_word = word_match.group()
                
                # Calculate similarity score
                score = self._calculate_similarity(token, original_word)
                
                if score > best_score:
                    best_score = score
                    best_match = word_match
            
            if best_match and best_score > 0.5:  # Threshold for matching
                token_positions.append(TokenPosition(
                    token_index=token_idx,
                    start_char=best_match.start(),
                    end_char=best_match.end(),
                    original_text=best_match.group(),
                    normalized_text=token
                ))
                
                used_word_positions.add((best_match.start(), best_match.end()))
                logger.debug(f"  Mapped token {token_idx}: '{token}' → '{best_match.group()}' (score: {best_score:.2f})")
            else:
                logger.warning(f"  No match found for token {token_idx}: '{token}'")
        
        logger.debug(f"Created {len(token_positions)} content-based mappings for draft {draft_id}")
        
        return FormatMapping(
            draft_id=draft_id,
            original_text=original_text,
            token_positions=token_positions
        )
    
    def _calculate_similarity(self, normalized_token: str, original_word: str) -> float:
        """Calculate similarity between normalized token and original word."""
        # Simple similarity based on normalized comparison
        normalized_original = re.sub(r'[^a-z0-9]', '', original_word.lower())
        normalized_token_clean = re.sub(r'[^a-z0-9]', '', normalized_token.lower())
        
        if normalized_original == normalized_token_clean:
            return 1.0
        elif normalized_original.startswith(normalized_token_clean) or normalized_token_clean.startswith(normalized_original):
            return 0.8
        else:
            return 0.0
    
    def reconstruct_formatted_text(self, 
                                 aligned_tokens: List[str], 
                                 mapping: FormatMapping,
                                 original_to_alignment: List[int]) -> str:
        """
        Reconstruct formatted text from aligned tokens using universal positional mapping.
        """
        if not aligned_tokens or not mapping.token_positions:
            return ""
        
        # Build a map from aligned position to original token index
        alignment_to_original = {}
        for original_idx, aligned_pos in enumerate(original_to_alignment):
            if aligned_pos != -1:  # -1 indicates token was deleted/not aligned
                alignment_to_original[aligned_pos] = original_idx
        
        # Sort token positions by their original order for spacing calculations
        sorted_positions = sorted(mapping.token_positions, key=lambda x: x.token_index)
        
        result_parts = []
        used_original_indices = set()  # Track used original indices
        
        for aligned_idx, token in enumerate(aligned_tokens):
            if token == '-':
                # Skip alignment gaps
                continue
            
            # Find the original token this aligned position corresponds to
            original_token_idx = alignment_to_original.get(aligned_idx)
            
            if original_token_idx is not None and original_token_idx not in used_original_indices:
                # Get the original formatting for this token
                position = mapping.get_position_for_token(original_token_idx)
                
                if position:
                    # Use the original formatted text
                    if token.lower() == position.normalized_text.lower():
                        # Token unchanged - use original formatting
                        formatted_text = position.original_text
                    else:
                        # Token was modified - use new token but try to preserve casing
                        formatted_text = self._preserve_simple_formatting(token, position.original_text)
                    
                    result_parts.append({
                        'text': formatted_text,
                        'start_char': position.start_char,
                        'end_char': position.end_char,
                        'original_idx': original_token_idx
                    })
                    used_original_indices.add(original_token_idx)  # Mark as used
        
        if not result_parts:
            return ""
        
        # Sort by original token index to maintain correct order
        result_parts.sort(key=lambda x: x['original_idx'])
        
        # Reconstruct with original spacing
        final_result = []
        
        for i, part in enumerate(result_parts):
            final_result.append(part['text'])
            
            # Add spacing between tokens based on original character positions
            if i < len(result_parts) - 1:
                next_part = result_parts[i + 1]
                
                # Calculate spacing between current token end and next token start
                current_end = part['end_char']
                next_start = next_part['start_char']
                
                if current_end < next_start:
                    # Extract the exact spacing from original text
                    spacing = mapping.original_text[current_end:next_start]
                    final_result.append(spacing)
        
        return ''.join(final_result)
    
    def _preserve_simple_formatting(self, new_token: str, original_text: str) -> str:
        """
        Apply simple formatting preservation when a token has been modified.
        
        Args:
            new_token: The modified token value
            original_text: The original formatted text
            
        Returns:
            New token with basic formatting preserved
        """
        # Preserve case pattern if token is alphabetic
        if new_token.isalpha() and original_text.isalpha():
            if original_text.isupper():
                return new_token.upper()
            elif original_text.islower():
                return new_token.lower()
            elif original_text.istitle():
                return new_token.title()
        
        # For non-alphabetic tokens, return as-is
        # The original spacing and punctuation context will be preserved
        # by the character-level mapping
        return new_token
    
    def get_formatting_statistics(self, mappings: List[FormatMapping]) -> Dict[str, Any]:
        """
        Get statistics about formatting found in the mappings.
        
        Args:
            mappings: List of format mappings to analyze
            
        Returns:
            Dictionary with formatting statistics
        """
        stats = {
            'total_drafts': len(mappings),
            'total_tokens': sum(len(m.token_positions) for m in mappings),
            'formatted_tokens': 0,
            'formatting_coverage': 0.0
        }
        
        formatted_count = 0
        
        for mapping in mappings:
            for position in mapping.token_positions:
                if position.original_text != position.normalized_text:
                    formatted_count += 1
        
        stats['formatted_tokens'] = formatted_count
        stats['formatting_coverage'] = (formatted_count / max(stats['total_tokens'], 1)) * 100
        
        return stats 