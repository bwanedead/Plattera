"""
Type 1 Exact Text Formatter
===========================

COMPLETELY ISOLATED Type 1 formatting implementation.
Goal: Reconstruct exact original text with all original formatting, spacing, and punctuation preserved.

This formatter is COMPLETELY UNAWARE of Type 2 formatting and has NO DEPENDENCIES on it.
"""

from typing import Dict, List, Any, Optional, Set, Tuple
from alignment.format_mapping import FormatMapping
import logging

logger = logging.getLogger(__name__)


class Type1ExactFormatter:
    """
    Type 1 Exact Text Formatter - COMPLETELY ISOLATED
    
    Purpose: Reconstruct exact original text from aligned tokens.
    Output: Complete, readable original text for draft viewer.
    
    This class has NO KNOWLEDGE of Type 2 formatting whatsoever.
    """
    
    def __init__(self):
        """Initialize Type 1 formatter - completely independent."""
        pass
    
    def reconstruct_exact_original_text(self, aligned_tokens: List[str], 
                                      format_mapping: FormatMapping,
                                      original_to_alignment: List[int]) -> str:
        """
        Reconstruct exact original text (Type 1) from aligned tokens.
        
        This method is COMPLETELY ISOLATED from Type 2 formatting.
        It only cares about reconstructing the exact original text.
        
        Args:
            aligned_tokens: List of aligned tokens (including gaps '-')
            format_mapping: Mapping from tokens to original text positions
            original_to_alignment: Mapping from original token indices to alignment positions
            
        Returns:
            str: Exact original text with all formatting preserved
        """
        logger.info(f"🔍 TYPE 1 EXACT FORMATTER ► Reconstructing exact original text")
        logger.info(f"   📊 Input: {len(aligned_tokens)} aligned tokens, {len(original_to_alignment)} mappings")
        
        if not format_mapping or not format_mapping.token_positions:
            # Fallback: simple space-separated text
            non_gap_tokens = [token for token in aligned_tokens if token != '-']
            logger.warning("   ⚠️ No format mapping, using fallback")
            return ' '.join(non_gap_tokens)
        
        # 🔧 FIX: Handle case where original_to_alignment is missing or empty
        if not original_to_alignment:
            logger.warning("   ⚠️ No original_to_alignment mapping, using fallback")
            non_gap_tokens = [token for token in aligned_tokens if token != '-']
            return ' '.join(non_gap_tokens)
        
        # 🔧 FIX: The format mapping is now based on normalized text, so we need to work with that
        # The original_to_alignment maps normalized token indices to alignment positions
        # The format_mapping.token_positions are based on the normalized text
        
        # Build reverse mapping: alignment position -> normalized token indices
        alignment_to_normalized = self._build_alignment_to_normalized_mapping(
            original_to_alignment, len(aligned_tokens)
        )
        
        logger.info(f"   🗺️ Built alignment-to-normalized mapping: {len(alignment_to_normalized)} entries")
        
        # Collect text portions in order
        text_portions = []
        seen_spans: Set[Tuple[int, int]] = set()  # 🔑 Track already-used character spans
        
        logger.info(f"   📋 Processing {len(aligned_tokens)} aligned tokens for exact text reconstruction...")
        
        # Process alignment positions in order
        for align_pos, token in enumerate(aligned_tokens):
            if token == '-':
                logger.debug(f"     Position {align_pos}: Skipping gap")
                continue  # Skip gaps
            
            # Get normalized indices for this alignment position
            normalized_indices = alignment_to_normalized.get(align_pos, [])
            logger.debug(f"     Position {align_pos}: Token '{token}' → Normalized indices {normalized_indices}")
            
            if not normalized_indices:
                logger.debug(f"       ❌ No normalized index mapping for aligned position {align_pos}")
                continue
            
            # Use the first normalized index (order doesn't matter for duplicates)
            norm_idx = normalized_indices[0]
            token_pos = format_mapping.get_position_for_token(norm_idx)
            
            if not token_pos:
                logger.warning(f"       ❌ No position found for normalized index {norm_idx}")
                continue
            
            # 🔑 Check if we've already processed this character span
            span = (token_pos.start_char, token_pos.end_char)
            if span in seen_spans:
                logger.debug(f"       ⚠️ SPAN ALREADY USED: '{token_pos.original_text}' (chars {span}) - skipping duplicate")
                continue
            
            # Mark this span as used
            seen_spans.add(span)
            
            logger.debug(f"       ✅ Found original text: '{token_pos.original_text}' (chars {token_pos.start_char}-{token_pos.end_char})")
            text_portions.append({
                'text': token_pos.original_text,
                'start_char': token_pos.start_char,
                'end_char': token_pos.end_char,
                'normalized_idx': norm_idx
            })
            
            logger.debug(f"       ✅ Added to text portions (total: {len(text_portions)})")
        
        # Reconstruct with exact original spacing
        result = self._reconstruct_with_exact_spacing(text_portions, format_mapping.original_text)
        
        logger.info(f"   ✅ Type 1 exact text reconstruction complete: {len(result)} characters")
        logger.debug(f"   📋 Used character spans: {len(seen_spans)}")
        logger.debug(f"   📋 Text portions count: {len(text_portions)}")
        
        return result
    
    def _build_alignment_to_normalized_mapping(self, original_to_alignment: List[int], 
                                         alignment_length: int) -> Dict[int, List[int]]:
        """Build reverse mapping from alignment position to list of normalized token indices."""
        from collections import defaultdict
        
        alignment_to_normalized = defaultdict(list)
        
        for norm_idx, align_pos in enumerate(original_to_alignment):
            if align_pos != -1 and align_pos < alignment_length:
                alignment_to_normalized[align_pos].append(norm_idx)
        
        return dict(alignment_to_normalized)
    
    def _reconstruct_with_exact_spacing(self, text_portions: List[Dict], original_text: str) -> str:
        """
        Reconstruct text with exact original spacing preserved.
        
        This is the key method that preserves exact original formatting.
        """
        if not text_portions:
            return ""
        
        # Sort by original character position to maintain order
        sorted_portions = sorted(text_portions, key=lambda x: x['start_char'])
        
        result_parts = []
        
        for i, portion in enumerate(sorted_portions):
            # Add the original text portion
            result_parts.append(portion['text'])
            
            # Add exact spacing between portions
            if i < len(sorted_portions) - 1:
                next_portion = sorted_portions[i + 1]
                
                current_end = portion['end_char']
                next_start = next_portion['start_char']
                
                # Extract exact spacing from original text
                if current_end < next_start:
                    exact_spacing = original_text[current_end:next_start]
                    result_parts.append(exact_spacing)
        
        return ''.join(result_parts) 