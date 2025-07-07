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
    """Handles format preservation during tokenization"""
    
    def __init__(self):
        # Legal document formatting patterns we want to preserve
        self.formatting_patterns = [
            r'[NS]\s*\d+°\s*\d+\'\s*\d+"\s*[EW]',  # N 37°15'30" W
            r'[NS]\s*\d+°\s*\d+\'\s*[EW]',          # N 37°15' W
            r'[NS]\s*\d+°\s*[EW]',                   # N 37° W
            r'\d+°\s*\d+\'\s*\d+"',                  # 37°15'30"
            r'\d+°\s*\d+\'',                         # 37°15'
            r'\d+°',                                 # 37°
            r'\(\d+\)',                              # (2)
            r'[NSEW]\.',                             # N., S., E., W.
            r'\d+,\d+',                              # 1,638
            r'\d+\.\d+',                             # 4.5
        ]
        
        # Compile patterns for efficiency
        self.compiled_patterns = [re.compile(pattern, re.IGNORECASE) 
                                 for pattern in self.formatting_patterns]
    
    def create_mapping(self, draft_id: str, original_text: str, normalized_tokens: List[str]) -> FormatMapping:
        """
        Create mapping between original text and normalized tokens.
        
        Args:
            draft_id: Identifier for this draft
            original_text: Original text with formatting
            normalized_tokens: List of normalized tokens from tokenizer
            
        Returns:
            FormatMapping with character positions for each token
        """
        logger.debug(f"Creating format mapping for draft {draft_id} with {len(normalized_tokens)} tokens")
        
        if not original_text or not normalized_tokens:
            return FormatMapping(draft_id, original_text, [])
        
        token_positions = []
        
        # Split original text into words while preserving positions
        word_matches = list(re.finditer(r'\S+', original_text))
        
        # Align normalized tokens with original words
        token_idx = 0
        word_idx = 0
        
        while token_idx < len(normalized_tokens) and word_idx < len(word_matches):
            current_token = normalized_tokens[token_idx]
            current_match = word_matches[word_idx]
            original_word = current_match.group()
            
            # Normalize the original word using the same logic as the tokenizer
            normalized_word = self._normalize_word(original_word)
            
            if normalized_word == current_token:
                # Direct match - create position mapping
                token_positions.append(TokenPosition(
                    token_index=token_idx,
                    start_char=current_match.start(),
                    end_char=current_match.end(),
                    original_text=original_word,
                    normalized_text=current_token
                ))
                token_idx += 1
                word_idx += 1
                
            elif self._could_be_compound_token(current_token, normalized_word):
                # Handle cases where one token maps to multiple words
                # or one word maps to multiple tokens
                compound_mapping = self._handle_compound_mapping(
                    token_idx, current_token, word_idx, word_matches, normalized_tokens
                )
                
                if compound_mapping:
                    token_positions.extend(compound_mapping['positions'])
                    token_idx += compound_mapping['tokens_consumed']
                    word_idx += compound_mapping['words_consumed']
                else:
                    # Skip this word if we can't map it
                    word_idx += 1
            else:
                # Skip this word if it doesn't match current token
                word_idx += 1
        
        logger.debug(f"Created {len(token_positions)} position mappings for draft {draft_id}")
        
        return FormatMapping(
            draft_id=draft_id,
            original_text=original_text,
            token_positions=token_positions
        )
    
    def _normalize_word(self, word: str) -> str:
        """
        Normalize a single word using the same logic as JsonDraftTokenizer._normalize_text
        This ensures consistency with the tokenization process.
        """
        normalized = word.lower()
        
        # Apply same transformations as tokenizer
        # Collapse commas/spaces inside numbers
        normalized = re.sub(r'(?<=\d)[,\s]+(?=\d)', '', normalized)
        
        # Protect decimal points
        normalized = re.sub(r'(?<=\d)\.(?=\d)', 'DOT', normalized)
        
        # Remove non-alphanumeric characters
        normalized = re.sub(r'[^a-z0-9\s]', ' ', normalized.replace('DOT', ' ')).replace('DOT', '.')
        
        # Collapse spaces and strip
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized
    
    def _could_be_compound_token(self, token: str, normalized_word: str) -> bool:
        """Check if token could be composed of multiple words or vice versa"""
        return (len(token) > len(normalized_word) and normalized_word in token) or \
               (len(normalized_word) > len(token) and token in normalized_word)
    
    def _handle_compound_mapping(self, token_idx: int, current_token: str, 
                                word_idx: int, word_matches: List, 
                                normalized_tokens: List[str]) -> Optional[Dict]:
        """
        Handle complex mappings where tokens don't align 1:1 with words.
        This is a simplified implementation - can be enhanced as needed.
        """
        # For now, create a basic mapping for the current token
        if word_idx < len(word_matches):
            current_match = word_matches[word_idx]
            return {
                'positions': [TokenPosition(
                    token_index=token_idx,
                    start_char=current_match.start(),
                    end_char=current_match.end(),
                    original_text=current_match.group(),
                    normalized_text=current_token
                )],
                'tokens_consumed': 1,
                'words_consumed': 1
            }
        return None
    
    def reconstruct_formatted_text(self, 
                                 aligned_tokens: List[str], 
                                 mapping: FormatMapping,
                                 original_to_alignment: List[int]) -> str:
        """
        Reconstruct formatted text from aligned tokens using original formatting.
        
        Args:
            aligned_tokens: Tokens after alignment (may include gaps '-')
            mapping: Original format mapping
            original_to_alignment: Maps original token index to aligned position
            
        Returns:
            Text with original formatting restored
        """
        if not aligned_tokens or not mapping.token_positions:
            return ""
        
        reconstructed_parts = []
        
        # Process each non-gap token in the aligned sequence
        for aligned_idx, token in enumerate(aligned_tokens):
            if token == '-':
                # Skip alignment gaps
                continue
            
            # Find which original token this aligned position corresponds to
            original_token_idx = None
            for orig_idx, aligned_pos in enumerate(original_to_alignment):
                if aligned_pos == aligned_idx:
                    original_token_idx = orig_idx
                    break
            
            if original_token_idx is not None:
                # Get the original formatting for this token
                position = mapping.get_position_for_token(original_token_idx)
                
                if position:
                    # Check if the token has been modified during editing
                    if token.lower() == position.normalized_text.lower():
                        # Token unchanged - use original formatting
                        reconstructed_parts.append(position.original_text)
                    else:
                        # Token was edited - apply formatting pattern to new value
                        formatted_token = self._apply_formatting_pattern(
                            token, position.original_text
                        )
                        reconstructed_parts.append(formatted_token)
                else:
                    # No position mapping found - use token as-is
                    reconstructed_parts.append(token)
            else:
                # No original token mapping found - use token as-is
                reconstructed_parts.append(token)
        
        return ' '.join(reconstructed_parts)
    
    def _apply_formatting_pattern(self, new_token: str, original_text: str) -> str:
        """
        Apply the formatting pattern from original text to new token value.
        
        Args:
            new_token: The new/edited token value
            original_text: The original text with formatting
            
        Returns:
            New token with original formatting pattern applied
        """
        # Degree symbol preservation
        if '°' in original_text:
            if new_token.isdigit():
                return f"{new_token}°"
            elif "'" in original_text:
                # Handle degree-minute format
                parts = new_token.split()
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    return f"{parts[0]}° {parts[1]}'"
        
        # Parentheses preservation
        if original_text.startswith('(') and original_text.endswith(')'):
            return f"({new_token})"
        
        # Directional abbreviation preservation
        if original_text.endswith('.') and len(original_text) <= 3:
            return f"{new_token}."
        
        # Comma in numbers preservation
        if ',' in original_text and new_token.isdigit():
            # Add comma for thousands separator if number is large enough
            if len(new_token) >= 4:
                return f"{new_token[:-3]},{new_token[-3:]}"
        
        # Default: return new token as-is
        return new_token
    
    def get_formatting_statistics(self, mappings: List[FormatMapping]) -> Dict[str, Any]:
        """
        Get statistics about formatting patterns found in the mappings.
        
        Args:
            mappings: List of format mappings to analyze
            
        Returns:
            Dictionary with formatting statistics
        """
        stats = {
            'total_drafts': len(mappings),
            'total_tokens': sum(len(m.token_positions) for m in mappings),
            'formatted_tokens': 0,
            'pattern_counts': {},
            'formatting_coverage': 0.0
        }
        
        formatted_count = 0
        pattern_counts = {}
        
        for mapping in mappings:
            for position in mapping.token_positions:
                if position.original_text != position.normalized_text:
                    formatted_count += 1
                    
                    # Identify which pattern this token matches
                    for pattern in self.compiled_patterns:
                        if pattern.search(position.original_text):
                            pattern_name = pattern.pattern
                            pattern_counts[pattern_name] = pattern_counts.get(pattern_name, 0) + 1
                            break
        
        stats['formatted_tokens'] = formatted_count
        stats['pattern_counts'] = pattern_counts
        stats['formatting_coverage'] = (formatted_count / max(stats['total_tokens'], 1)) * 100
        
        return stats 