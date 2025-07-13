"""
Type 2 Display Formatter
========================

COMPLETELY ISOLATED Type 2 formatting implementation.
Goal: Create formatted tokens for alignment table with consensus anchoring.

This formatter is COMPLETELY UNAWARE of Type 1 formatting and has NO DEPENDENCIES on it.
"""

from typing import Dict, List, Any, Optional
from collections import defaultdict
from .format_mapping import FormatMapping
import logging

logger = logging.getLogger(__name__)


class Type2DisplayFormatter:
    """
    Type 2 Display Formatter - COMPLETELY ISOLATED
    
    Purpose: Create formatted tokens for alignment table display.
    Output: Formatted tokens with consensus anchoring for visual comparison.
    
    This class has NO KNOWLEDGE of Type 1 formatting whatsoever.
    """
    
    def __init__(self):
        """Initialize Type 2 formatter - completely independent."""
        pass
    
    def create_display_tokens(self, aligned_tokens: List[str], 
                            format_mapping: FormatMapping,
                            original_to_alignment: List[int],
                            consensus_group_sizes: List[int]) -> List[str]:
        """
        Create formatted display tokens for alignment table (Type 2).
        """
        logger.info(f"🔧 TYPE 2 DISPLAY FORMATTER ► Creating display tokens")
        logger.info(f"   📊 Input: {len(aligned_tokens)} aligned tokens, {len(consensus_group_sizes)} group sizes")
        
        if not aligned_tokens:
            logger.warning("   ⚠️ No aligned tokens provided")
            return []
        
        # Step 1: Get formatted tokens from format mapping
        formatted_tokens = self._get_formatted_tokens(aligned_tokens, format_mapping, original_to_alignment)
        logger.info(f"   ✅ Formatted tokens: {len(formatted_tokens)} tokens")
        
        # Step 2: Apply consensus grouping for anchoring
        if consensus_group_sizes:
            display_tokens = self._apply_consensus_grouping(formatted_tokens, consensus_group_sizes)
            logger.info(f"   ✅ Consensus grouping applied: {len(display_tokens)} display tokens")
        else:
            logger.info("   ⚠️ No consensus grouping available, using formatted tokens as-is")
            display_tokens = formatted_tokens
        
        logger.info(f"   🎉 Type 2 display tokens complete: {len(display_tokens)} tokens")
        return display_tokens
    
    def _get_formatted_tokens(self, aligned_tokens: List[str], 
                            format_mapping: FormatMapping,
                            original_to_alignment: List[int]) -> List[str]:
        """
        Get formatted tokens from aligned tokens using format mapping.
        
        This is used for Type 2 display before consensus grouping is applied.
        """
        logger.debug(f"🔤 Getting formatted tokens for Type 2 display")
        
        if not aligned_tokens or not format_mapping or not format_mapping.token_positions:
            logger.warning("⚠️ Missing data for formatting, returning aligned tokens as-is")
            return aligned_tokens
        
        formatted_tokens = []
        
        # Build reverse mapping: alignment position -> original token indices
        alignment_to_original = self._build_alignment_to_original_mapping(
            original_to_alignment, len(aligned_tokens)
        )
        
        for align_pos, token in enumerate(aligned_tokens):
            if token == '-':
                formatted_tokens.append('-')  # Preserve gaps
                continue
            
            # Find original token indices for this alignment position
            original_indices = alignment_to_original.get(align_pos, [])
            
            if not original_indices:
                formatted_tokens.append(token)  # Fallback to aligned token
                continue
            
            # Get formatted token from first original index
            orig_idx = original_indices[0]
            token_pos = format_mapping.get_position_for_token(orig_idx)
            
            if token_pos:
                formatted_tokens.append(token_pos.original_text)
            else:
                formatted_tokens.append(token)  # Fallback
        
        return formatted_tokens
    
    def _apply_consensus_grouping(self, formatted_tokens: List[str], 
                                group_sizes: List[int]) -> List[str]:
        """
        Apply consensus grouping to formatted tokens for Type 2 display.
        
        Groups consecutive tokens according to consensus group sizes to ensure
        normalized tokens stay anchored to the same positions across all drafts.
        """
        if not group_sizes or len(group_sizes) != len(formatted_tokens):
            logger.warning(f"⚠️ Group size mismatch: tokens={len(formatted_tokens)}, groups={len(group_sizes)}")
            return formatted_tokens
        
        logger.info(f"🔧 Applying consensus grouping: {len(formatted_tokens)} tokens, {len(group_sizes)} group sizes")
        
        grouped_tokens = []
        i = 0
        
        for group_idx, group_size in enumerate(group_sizes):
            if group_size <= 0:
                continue
            
            # Collect tokens for this group
            group_tokens = []
            for _ in range(group_size):
                if i < len(formatted_tokens):
                    group_tokens.append(formatted_tokens[i])
                    i += 1
            
            if group_tokens:
                # Merge tokens intelligently
                merged_token = self._merge_tokens_for_display(group_tokens)
                grouped_tokens.append(merged_token)
        
        logger.info(f"✅ Consensus grouping complete: {len(grouped_tokens)} grouped tokens")
        return grouped_tokens
    
    def _merge_tokens_for_display(self, tokens: List[str]) -> str:
        """
        Intelligently merge multiple tokens into a single display token.
        
        This is specifically for Type 2 display purposes.
        """
        if not tokens:
            return ""
        
        if len(tokens) == 1:
            return tokens[0]
        
        # Check if tokens contain special characters that should be merged without spaces
        merged = ''.join(tokens)
        if any(char in merged for char in ['°', "'", '"', '(', ')', ',', ';']):
            return merged
        
        # For other cases, join with spaces
        return ' '.join(tokens)
    
    def _build_alignment_to_original_mapping(self, original_to_alignment: List[int], 
                                           alignment_length: int) -> Dict[int, List[int]]:
        """Build reverse mapping from alignment position to list of original token indices."""
        alignment_to_original = defaultdict(list)
        
        for orig_idx, align_pos in enumerate(original_to_alignment):
            if align_pos != -1 and align_pos < alignment_length:
                alignment_to_original[align_pos].append(orig_idx)
        
        return dict(alignment_to_original)


class Type2ConsensusAnalyzer:
    """
    Analyzes token mappings across drafts to compute consensus groupings.
    
    This is part of Type 2 formatting and has NO KNOWLEDGE of Type 1.
    """
    
    def __init__(self):
        """Initialize consensus analyzer."""
        pass
    
    def compute_consensus_groupings(self, alignment_results: Dict[str, Any],
                                  format_mappings: Dict[str, Dict[str, FormatMapping]]) -> Dict[str, Dict[str, List[int]]]:
        """
        Compute consensus groupings for Type 2 formatting.
        
        Returns: Dict[block_id, Dict[draft_id, List[int]]] (the correct structure)
        """
        logger.info("🎯 TYPE 2 CONSENSUS ANALYZER ► Computing consensus groupings")
        
        consensus_groupings = {}
        
        blocks = alignment_results.get('blocks', {})
        
        for block_id, align_block in blocks.items():
            logger.info(f"   📋 Processing consensus for block: {block_id}")
            
            block_groupings = {}
            aligned_sequences = align_block.get('aligned_sequences', [])
            
            if not aligned_sequences:
                logger.warning(f"   ⚠️ No aligned sequences for block {block_id}")
                continue
            
            # Get alignment length
            alignment_length = len(aligned_sequences[0].get('tokens', []))
            
            # Simple consensus grouping: each token gets its own group (size 1)
            for seq in aligned_sequences:
                draft_id = seq.get('draft_id')
                if draft_id:
                    consensus_group_sizes = [1] * alignment_length
                    block_groupings[draft_id] = consensus_group_sizes
            
            consensus_groupings[block_id] = block_groupings
        
        logger.info(f"🎊 Type 2 consensus groupings complete: {len(consensus_groupings)} blocks processed")
        return consensus_groupings 