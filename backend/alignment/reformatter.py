"""
Reformatter module for post-alignment text processing.
Handles Type 1 (exact original text restoration) and Type 2 (formatted token display with consensus anchoring).
"""

from typing import Dict, List, Any, Tuple, Optional
from collections import defaultdict
from .format_mapping import FormatMapping, TokenPosition, FormatMapper
from .alignment_utils import AlignmentError
import logging

logger = logging.getLogger(__name__)


class Reformatter:
    """
    Advanced reformatter that handles both exact text restoration (Type 1) 
    and consensus-anchored formatted token display (Type 2).
    
    This class is the main integration point for all formatting operations
    and feeds data to frontend viewers (alignment table, heatmap, draft viewer).
    """

    def __init__(self):
        self.format_mapper = FormatMapper()

    def create_frontend_alignment_results(self, alignment_results: Dict[str, Any], 
                                        tokenized_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create frontend-ready alignment results with proper token formatting.
        
        This is the main method that integrates with biopython_engine and outputs
        to all frontend viewers (alignment table, heatmap, draft viewer).
        
        Args:
            alignment_results: Results from BioPython alignment
            tokenized_data: Output from tokenizer with format mappings
            
        Returns:
            Frontend-ready alignment results with both Type 1 and Type 2 formatting
        """
        logger.info("🔧 REFORMATTER ► Creating frontend alignment results with format reconstruction")
        
        # Step 1: Build format mappings for all drafts
        format_mappings = self._build_format_mappings(tokenized_data)
        
        # Step 2: Compute consensus groupings for Type 2 formatting
        consensus_groupings = self.compute_consensus_groupings(alignment_results, format_mappings)
        
        # Step 3: Process alignment results with both formatting types
        frontend_blocks = self._process_alignment_blocks(
            alignment_results, format_mappings, consensus_groupings
        )
        
        # Step 4: Create final frontend-ready structure
        frontend_results = {
            'blocks': frontend_blocks,
            'summary': alignment_results.get('summary', {}),
            'metadata': alignment_results.get('metadata', {}),
            'format_reconstruction_applied': True,
            'consensus_groupings': consensus_groupings  # For debugging/analysis
        }
        
        logger.info(f"✅ REFORMATTER COMPLETE ► {len(frontend_blocks)} blocks processed")
        return frontend_results

    def _build_format_mappings(self, tokenized_data: Dict[str, Any]) -> Dict[str, Dict[str, FormatMapping]]:
        """Build format mappings for all drafts in all blocks."""
        format_mappings = {}
        
        for block_id, block_data in tokenized_data['blocks'].items():
            format_mappings[block_id] = {}
            
            for draft_data in block_data.get('encoded_drafts', []):
                draft_id = draft_data['draft_id']
                original_text = draft_data.get('original_text', '')
                tokens = draft_data.get('tokens', [])
                
                # Create format mapping
                format_mapping = self.format_mapper.create_mapping(draft_id, original_text, tokens)
                format_mappings[block_id][draft_id] = format_mapping
                logger.debug(f"📊 FORMAT MAPPING ► {draft_id}: {len(format_mapping.token_positions)} patterns found")
        
        return format_mappings

    def _process_alignment_blocks(self, alignment_results: Dict[str, Any], 
                                format_mappings: Dict[str, Dict[str, FormatMapping]],
                                consensus_groupings: Dict[str, Dict[str, List[int]]]) -> Dict[str, Any]:
        """Process all alignment blocks with formatting."""
        frontend_blocks = {}
        
        for block_id, block_data in alignment_results['blocks'].items():
            frontend_sequences = []
            
            for sequence_data in block_data.get('aligned_sequences', []):
                draft_id = sequence_data['draft_id']
                aligned_tokens = sequence_data['tokens']
                original_to_alignment = sequence_data.get('original_to_alignment', [])
                
                # Get format mapping for this draft
                format_mapping = format_mappings.get(block_id, {}).get(draft_id)
                
                if format_mapping and aligned_tokens:
                    try:
                        # Create both Type 1 and Type 2 formatted versions
                        formatted_sequence = self._create_formatted_sequence(
                            draft_id, aligned_tokens, original_to_alignment, 
                            format_mapping, consensus_groupings.get(block_id, {}).get(draft_id, [])
                        )
                        frontend_sequences.append(formatted_sequence)
                        
                    except Exception as e:
                        logger.error(f"❌ FORMAT RECONSTRUCTION FAILED ► {draft_id} in {block_id}: {e}")
                        # Fallback to original tokens
                        frontend_sequences.append(self._create_fallback_sequence(
                            draft_id, aligned_tokens, original_to_alignment
                        ))
                else:
                    # No format mapping available
                    logger.warning(f"⚠️ NO FORMAT MAPPING ► {draft_id} in {block_id}")
                    frontend_sequences.append(self._create_fallback_sequence(
                        draft_id, aligned_tokens, original_to_alignment
                    ))
            
            frontend_blocks[block_id] = {
                'aligned_sequences': frontend_sequences,
                'confidence_scores': block_data.get('confidence_scores', {}),
                'agreement_info': block_data.get('agreement_info', {}),
                'differences': block_data.get('differences', [])
            }
        
        return frontend_blocks

    def _create_formatted_sequence(self, draft_id: str, aligned_tokens: List[str], 
                                 original_to_alignment: List[int], format_mapping: FormatMapping,
                                 consensus_group_sizes: List[int]) -> Dict[str, Any]:
        """
        Create a formatted sequence with both Type 1 and Type 2 formatting.
        
        Type 1: Exact text restoration for draft viewer
        Type 2: Formatted tokens with consensus anchoring for table/heatmap
        """
        # Get non-gap tokens for processing
        non_gap_tokens = [t for t in aligned_tokens if t != '-']
        
        # === TYPE 2 FORMATTING: Formatted tokens for table/heatmap ===
        type2_formatted_tokens = self.get_formatted_tokens(
            aligned_tokens, format_mapping, original_to_alignment
        )
        
        # Apply consensus grouping to Type 2 tokens
        if consensus_group_sizes:
            type2_grouped_tokens = self.apply_type2_grouping(
                [t for t in type2_formatted_tokens if t != '-'], consensus_group_sizes
            )
        else:
            type2_grouped_tokens = [t for t in type2_formatted_tokens if t != '-']
        
        # Reconstruct Type 2 tokens with gaps for alignment table
        type2_tokens_with_gaps = self._reconstruct_with_gaps(
            aligned_tokens, type2_grouped_tokens
        )
        
        # === TYPE 1 FORMATTING: Exact text restoration ===
        type1_exact_text = self.reconstruct_type1_exact(
            aligned_tokens, format_mapping, original_to_alignment
        )
        
        # === POSITION MAPPING for frontend coordination ===
        alignment_to_frontend_mapping = self._create_position_mapping(
            aligned_tokens, type2_grouped_tokens
        )
        
        logger.debug(f"✅ FORMATTED ► {draft_id}: Type1={len(type1_exact_text)} chars, "
                    f"Type2={len(type2_tokens_with_gaps)} tokens, "
                    f"Display={len(type2_grouped_tokens)} non-gap")
        
        return {
            'draft_id': draft_id,
            'tokens': type2_tokens_with_gaps,  # For alignment table (with gaps)
            'display_tokens': type2_grouped_tokens,  # For heatmap (no gaps)
            'exact_text': type1_exact_text,  # For draft viewer (Type 1)
            'original_to_alignment': original_to_alignment,
            'alignment_to_frontend': alignment_to_frontend_mapping,
            'formatting_applied': True
        }

    def _create_fallback_sequence(self, draft_id: str, aligned_tokens: List[str], 
                                original_to_alignment: List[int]) -> Dict[str, Any]:
        """Create fallback sequence when formatting fails."""
        fallback_mapping = {i: i for i in range(len(aligned_tokens))}
        non_gap_tokens = [t for t in aligned_tokens if t != '-']
        
        return {
            'draft_id': draft_id,
            'tokens': aligned_tokens,
            'display_tokens': non_gap_tokens,
            'exact_text': ' '.join(non_gap_tokens),  # Simple fallback
            'original_to_alignment': original_to_alignment,
            'alignment_to_frontend': fallback_mapping,
            'formatting_applied': False
        }

    def _reconstruct_with_gaps(self, aligned_tokens: List[str], 
                             formatted_non_gap_tokens: List[str]) -> List[str]:
        """Reconstruct formatted tokens with gaps preserved for alignment table."""
        result = []
        non_gap_idx = 0
        
        for token in aligned_tokens:
            if token == '-':
                result.append('-')
            else:
                if non_gap_idx < len(formatted_non_gap_tokens):
                    result.append(formatted_non_gap_tokens[non_gap_idx])
                    non_gap_idx += 1
                else:
                    result.append(token)  # Fallback
        
        return result

    def _create_position_mapping(self, aligned_tokens: List[str], 
                               display_tokens: List[str]) -> Dict[int, Optional[int]]:
        """Create mapping from alignment position to frontend display position."""
        mapping = {}
        display_idx = 0
        
        for align_idx, token in enumerate(aligned_tokens):
            if token == '-':
                mapping[align_idx] = None  # Gaps map to null
            else:
                mapping[align_idx] = display_idx
                display_idx += 1
        
        return mapping

    def reconstruct_type1_exact(self, aligned_tokens: List[str], format_mapping: FormatMapping,
                                original_to_alignment: List[int]) -> str:
        """
        Type 1: Exact restoration to original text with all formatting preserved.
        
        This is a "dumb" universal process that maps normalized tokens back to 
        their exact original text portions using character-level mapping.
        """
        if not aligned_tokens or not format_mapping or not format_mapping.token_positions:
            # Fallback to simple space-separated text
            return ' '.join(token for token in aligned_tokens if token != '-')
        
        return self.format_mapper.reconstruct_formatted_text(
            aligned_tokens, format_mapping, original_to_alignment
        )

    def compute_consensus_groupings(self, alignment_results: Dict[str, Any],
                                    format_mappings: Dict[str, Dict[str, FormatMapping]]) -> Dict[str, Dict[str, List[int]]]:
        """
        Compute consensus-based groupings to ensure consistent token anchoring across drafts.
        
        This solves the core problem where normalized tokens map to different numbers 
        of formatted tokens across drafts, causing table misalignment.
        """
        logger.info("🔧 CONSENSUS GROUPING ► Computing consensus-based token groupings")
        
        consensus_groupings = {}
        
        for block_id, align_block in alignment_results['blocks'].items():
            logger.debug(f"   📋 Processing block: {block_id}")
            
            block_groupings = {}
            aligned_sequences = align_block.get('aligned_sequences', [])
            
            if not aligned_sequences:
                logger.warning(f"   ⚠️ No aligned sequences for block {block_id}")
                continue
                
            alignment_length = len(aligned_sequences[0].get('tokens', []))
            logger.debug(f"   📏 Alignment length: {alignment_length} positions")
            
            # Step 1: Analyze how many formatted tokens each normalized token maps to
            position_analysis = self._analyze_token_mappings(
                aligned_sequences, format_mappings.get(block_id, {}), block_id
            )
            
            # Step 2: Compute consensus grouping for each position
            consensus_group_sizes = []
            for pos in range(alignment_length):
                if pos < len(position_analysis):
                    # Use maximum group size across all drafts for this position
                    max_group_size = max(position_analysis[pos].values()) if position_analysis[pos] else 1
                    consensus_group_sizes.append(max_group_size)
                    
                    if max_group_size > 1:
                        logger.debug(f"   🎯 Position {pos}: consensus group size {max_group_size}")
                        logger.debug(f"      Draft mappings: {position_analysis[pos]}")
                else:
                    consensus_group_sizes.append(1)
            
            # Step 3: Apply consensus grouping to all drafts
            for seq in aligned_sequences:
                draft_id = seq.get('draft_id')
                if draft_id:
                    block_groupings[draft_id] = consensus_group_sizes.copy()
                    logger.debug(f"   ✅ Applied consensus grouping to {draft_id}")
            
            consensus_groupings[block_id] = block_groupings
            logger.debug(f"   📊 Block {block_id}: {len(block_groupings)} drafts with consensus grouping")
        
        logger.info("✅ CONSENSUS GROUPING COMPLETE ► All blocks processed")
        return consensus_groupings

    def _analyze_token_mappings(self, aligned_sequences: List[Dict], 
                               format_mappings: Dict[str, FormatMapping], 
                               block_id: str) -> List[Dict[str, int]]:
        """Analyze how many formatted tokens each normalized token maps to across drafts."""
        if not aligned_sequences:
            return []
            
        alignment_length = len(aligned_sequences[0].get('tokens', []))
        position_analysis = [{} for _ in range(alignment_length)]
        
        for seq in aligned_sequences:
            draft_id = seq.get('draft_id')
            if not draft_id or draft_id not in format_mappings:
                continue
                
            format_mapping = format_mappings[draft_id]
            aligned_tokens = seq.get('tokens', [])
            original_to_alignment = seq.get('original_to_alignment', [])
            
            # Build reverse mapping: alignment position -> original token indices
            alignment_to_original = self._build_alignment_to_original_mapping(
                original_to_alignment, len(aligned_tokens)
            )
            
            # Analyze each alignment position
            for align_pos in range(len(aligned_tokens)):
                if aligned_tokens[align_pos] == '-':
                    # Gap position - contributes 0 tokens
                    position_analysis[align_pos][draft_id] = 0
                    continue
                
                # Find original token indices that map to this alignment position
                original_indices = alignment_to_original.get(align_pos, [])
                
                if not original_indices:
                    # No mapping found - default to 1 token
                    position_analysis[align_pos][draft_id] = 1
                    continue
                
                # Count formatted tokens for these original indices
                formatted_token_count = self._count_formatted_tokens_for_indices(
                    original_indices, format_mapping
                )
                
                position_analysis[align_pos][draft_id] = formatted_token_count
                
                logger.debug(f"   🔍 {draft_id} pos {align_pos}: {len(original_indices)} orig indices → {formatted_token_count} formatted tokens")
        
        return position_analysis

    def _build_alignment_to_original_mapping(self, original_to_alignment: List[int], 
                                           alignment_length: int) -> Dict[int, List[int]]:
        """Build reverse mapping from alignment position to list of original token indices."""
        alignment_to_original = defaultdict(list)
        
        for orig_idx, align_pos in enumerate(original_to_alignment):
            if align_pos != -1 and align_pos < alignment_length:
                alignment_to_original[align_pos].append(orig_idx)
        
        return dict(alignment_to_original)

    def _count_formatted_tokens_for_indices(self, original_indices: List[int], 
                                          format_mapping: FormatMapping) -> int:
        """Count how many formatted tokens the given original token indices map to."""
        if not original_indices or not format_mapping.token_positions:
            return len(original_indices)  # Fallback: assume 1:1 mapping
        
        # Find all formatted tokens that these original indices map to
        formatted_tokens = set()
        
        for orig_idx in original_indices:
            # Find the token position for this original index
            token_pos = format_mapping.get_position_for_token(orig_idx)
            if token_pos:
                # Use the original formatted text as the identifier
                formatted_tokens.add(token_pos.original_text)
        
        # Return count of distinct formatted tokens
        count = len(formatted_tokens) if formatted_tokens else len(original_indices)
        
        logger.debug(f"      Original indices {original_indices} → {count} formatted tokens: {list(formatted_tokens)}")
        return count

    def apply_type2_grouping(self, formatted_tokens: List[str], group_sizes: List[int]) -> List[str]:
        """
        Apply Type 2 grouping to formatted tokens using consensus group sizes.
        
        This ensures consistent positioning across drafts by merging tokens 
        according to the consensus grouping.
        """
        if not formatted_tokens or not group_sizes:
            return formatted_tokens
        
        grouped_tokens = []
        token_idx = 0
        
        for group_size in group_sizes:
            if group_size == 0:
                # Gap position - skip (will be handled at reconstruction level)
                continue
            elif group_size == 1:
                # Single token
                if token_idx < len(formatted_tokens):
                    grouped_tokens.append(formatted_tokens[token_idx])
                    token_idx += 1
                else:
                    grouped_tokens.append('-')  # No token available
            else:
                # Multiple tokens - merge them
                tokens_to_merge = []
                for _ in range(group_size):
                    if token_idx < len(formatted_tokens):
                        tokens_to_merge.append(formatted_tokens[token_idx])
                        token_idx += 1
                
                if tokens_to_merge:
                    # Merge tokens intelligently
                    merged_token = self._merge_tokens_intelligently(tokens_to_merge)
                    grouped_tokens.append(merged_token)
                else:
                    grouped_tokens.append('-')  # No tokens available
        
        logger.debug(f"   🎯 Type 2 grouping: {len(formatted_tokens)} tokens → {len(grouped_tokens)} grouped tokens")
        return grouped_tokens

    def _merge_tokens_intelligently(self, tokens: List[str]) -> str:
        """
        Merge multiple tokens intelligently, preserving formatting.
        
        This is a "dumb" merge that simply concatenates tokens with minimal spacing,
        making no assumptions about content.
        """
        if not tokens:
            return ""
        if len(tokens) == 1:
            return tokens[0]
        
        # Simple concatenation with no spaces for formatted tokens
        # This preserves things like "4°" + "00'" + "W." → "4°00'W."
        return ''.join(tokens)

    def get_formatted_tokens(self, aligned_tokens: List[str], format_mapping: FormatMapping,
                             original_to_alignment: List[int]) -> List[str]:
        """
        Get formatted tokens from aligned tokens using format mapping.
        
        This is used for Type 2 display before consensus grouping is applied.
        """
        if not aligned_tokens or not format_mapping or not format_mapping.token_positions:
            return aligned_tokens  # Fallback
        
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
            
            # Get formatted tokens for these original indices
            formatted_for_position = []
            for orig_idx in original_indices:
                token_pos = format_mapping.get_position_for_token(orig_idx)
                if token_pos:
                    formatted_for_position.append(token_pos.original_text)
                else:
                    formatted_for_position.append(token)  # Fallback
            
            # For now, just use the first formatted token
            # The consensus grouping will handle merging later
            if formatted_for_position:
                formatted_tokens.append(formatted_for_position[0])
            else:
                formatted_tokens.append(token)
        
        return formatted_tokens 