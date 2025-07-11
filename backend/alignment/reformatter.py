"""
Reformatter module for post-alignment text processing.
Handles Type 1 (exact original text restoration) and Type 2 (formatted token display with consensus anchoring).
"""

from typing import Dict, List, Any, Tuple, Optional
from collections import defaultdict
from .format_mapping import FormatMapping, TokenPosition
from .alignment_utils import AlignmentError
import logging

logger = logging.getLogger(__name__)


class Reformatter:
    """
    Advanced reformatter that handles both exact text restoration (Type 1) 
    and consensus-anchored formatted token display (Type 2).
    """

    def __init__(self):
        pass

    def create_frontend_alignment_results(self, alignment_results: Dict[str, Any], 
                                        tokenized_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create frontend-ready alignment results with proper formatting.
        
        Uses format mappings from tokenized_data (created during tokenization) instead of recreating them.
        """
        logger.info("🎨 REFORMATTER ► Creating frontend alignment results")
        
        # FIXED: Use existing format mappings from tokenizer instead of recreating
        format_mappings = self._extract_format_mappings_from_tokenized_data(tokenized_data)
        logger.info(f"✅ FORMAT MAPPINGS ► Extracted from tokenizer for {sum(len(block_mappings) for block_mappings in format_mappings.values())} drafts across {len(format_mappings)} blocks")
        
        # Step 2: Compute consensus groupings
        logger.info("🎯 STEP 2 ► Computing consensus groupings")
        consensus_groupings = self.compute_consensus_groupings(alignment_results, format_mappings)
        logger.info("✅ CONSENSUS GROUPINGS ► Computed for {len(consensus_groupings)} blocks")
        
        # Step 3: Process alignment blocks with formatting
        logger.info("🔧 STEP 3 ► Processing alignment blocks with formatting")
        processed_results = self._process_alignment_blocks(
            alignment_results, format_mappings, consensus_groupings
        )
        logger.info("✅ BLOCK PROCESSING ► Processed {len(processed_results.get('blocks', {}))} blocks")
        
        logger.info("🎉 REFORMATTER COMPLETE ► {len(processed_results.get('blocks', {}))} blocks processed successfully")
        
        # Log sample output for debugging
        if processed_results.get('blocks'):
            sample_block_id = list(processed_results['blocks'].keys())[0]
            sample_block = processed_results['blocks'][sample_block_id]
            if sample_block.get('sequences'):
                sample_draft_id = list(sample_block['sequences'].keys())[0]
                sample_sequence = sample_block['sequences'][sample_draft_id]
                logger.info(f"📝 SAMPLE OUTPUT ► Block '{sample_block_id}', Draft '{sample_draft_id}':")
                logger.info(f"   🔤 Tokens: {sample_sequence.get('tokens', [])[:10]}...")
                logger.info(f"   📱 Display tokens: {sample_sequence.get('display_tokens', [])[:10]}...")
                logger.info(f"   📄 Exact text preview: {sample_sequence.get('exact_text', '')[:50]}...")
                logger.info(f"   ✅ Formatting applied: {sample_sequence.get('formatting_applied', False)}")
        
        return processed_results

    def _extract_format_mappings_from_tokenized_data(self, tokenized_data: Dict[str, Any]) -> Dict[str, Dict[str, FormatMapping]]:
        """
        Extract format mappings that were already created during tokenization.
        
        This avoids duplicating the format mapping creation work.
        """
        logger.info("🎯 EXTRACTING FORMAT MAPPINGS ► From tokenized data")
        
        format_mappings = {}
        blocks = tokenized_data.get('blocks', {})
        
        for block_id, block_data in blocks.items():
            # Get format mappings that were created during tokenization
            block_format_mappings = block_data.get('format_mappings', {})
            
            if block_format_mappings:
                format_mappings[block_id] = block_format_mappings
                logger.info(f"   📋 Block {block_id}: {len(block_format_mappings)} format mappings found")
            else:
                logger.warning(f"   ⚠️ Block {block_id}: No format mappings found")
                format_mappings[block_id] = {}
        
        total_mappings = sum(len(block_mappings) for block_mappings in format_mappings.values())
        logger.info(f"✅ FORMAT MAPPINGS EXTRACTED ► {total_mappings} mappings across {len(format_mappings)} blocks")
        
        return format_mappings

    def _process_alignment_blocks(self, alignment_results: Dict[str, Any], 
                                format_mappings: Dict[str, Dict[str, FormatMapping]],
                                consensus_groupings: Dict[str, Dict[str, List[int]]]) -> Dict[str, Any]:
        """Process each alignment block with formatting and consensus grouping."""
        logger.info("🔧 PROCESSING ALIGNMENT BLOCKS ► Applying formatting to sequences")
        
        processed_blocks = {}
        successful_formats = 0
        failed_formats = 0
        
        blocks = alignment_results.get('blocks', {})
        
        for block_id, align_block in blocks.items():
            logger.info(f"   📋 Processing alignment block: {block_id}")
            
            aligned_sequences = align_block.get('aligned_sequences', [])
            consensus_group_sizes = consensus_groupings.get(block_id, {})
            
            if not aligned_sequences:
                logger.warning(f"   ⚠️ No aligned sequences for block {block_id}")
                continue
            
            logger.info(f"      📊 Found {len(aligned_sequences)} aligned sequences in block {block_id}")
            
            # FIXED: Keep the same structure as original - use aligned_sequences array
            formatted_aligned_sequences = []
            
            for seq in aligned_sequences:
                draft_id = seq.get('draft_id')
                aligned_tokens = seq.get('tokens', [])
                original_to_alignment = seq.get('original_to_alignment', [])
                
                logger.info(f"      🔤 Processing sequence {draft_id}: {len(aligned_tokens)} aligned tokens")
                
                # Get format mapping for this draft
                format_mapping = format_mappings.get(block_id, {}).get(draft_id)
                group_sizes = consensus_group_sizes.get(draft_id, [])
                
                if format_mapping:
                    logger.info(f"      ✅ FORMAT MAPPING FOUND ► {draft_id}: {len(format_mapping.token_positions)} positions available")
                    
                    try:
                        # Create formatted sequence
                        formatted_sequence = self._create_formatted_sequence(
                            draft_id, aligned_tokens, original_to_alignment, 
                            format_mapping, group_sizes
                        )
                        
                        # FIXED: Maintain original structure with draft_id, tokens, etc.
                        formatted_aligned_sequences.append({
                            'draft_id': draft_id,
                            'tokens': formatted_sequence.get('display_tokens', aligned_tokens),  # Use display_tokens for table
                            'original_to_alignment': original_to_alignment,
                            'exact_text': formatted_sequence.get('exact_text', ''),  # Add exact text for draft viewer
                            'formatting_applied': formatted_sequence.get('formatting_applied', False),
                            'metadata': formatted_sequence.get('metadata', {})
                        })
                        
                        successful_formats += 1
                        logger.info(f"      🎉 FORMATTING SUCCESS ► {draft_id} formatted successfully")
                        
                    except Exception as e:
                        logger.error(f"      ❌ FORMATTING ERROR ► {draft_id}: {e}")
                        # Fallback to original structure
                        formatted_aligned_sequences.append({
                            'draft_id': draft_id,
                            'tokens': aligned_tokens,
                            'original_to_alignment': original_to_alignment,
                            'exact_text': ' '.join([t for t in aligned_tokens if t != '-']),
                            'formatting_applied': False
                        })
                        failed_formats += 1
                else:
                    logger.warning(f"      ⚠️ NO FORMAT MAPPING ► {draft_id}: using fallback formatting")
                    formatted_aligned_sequences.append({
                        'draft_id': draft_id,
                        'tokens': aligned_tokens,
                        'original_to_alignment': original_to_alignment,
                        'exact_text': ' '.join([t for t in aligned_tokens if t != '-']),
                        'formatting_applied': False
                    })
                    failed_formats += 1
            
            # FIXED: Use the same structure as original alignment results
            processed_blocks[block_id] = {
                'aligned_sequences': formatted_aligned_sequences,  # ← Frontend expects this!
                'alignment_length': len(formatted_aligned_sequences[0].get('tokens', [])) if formatted_aligned_sequences else 0,
                'draft_count': len(formatted_aligned_sequences),
                'block_id': block_id
            }
            
            logger.info(f"   ✅ BLOCK COMPLETE ► {block_id}: {len(formatted_aligned_sequences)} sequences processed")
        
        logger.info(f"🎊 BLOCK PROCESSING COMPLETE ► {len(processed_blocks)} sequences processed")
        logger.info(f"   ✅ Successful formats: {successful_formats}")
        logger.info(f"   ❌ Failed formats: {failed_formats}")
        
        return {
            'blocks': processed_blocks,
            'summary': {
                'total_blocks': len(processed_blocks),
                'successful_formats': successful_formats,
                'failed_formats': failed_formats
            }
        }

    def _create_formatted_sequence(self, draft_id: str, aligned_tokens: List[str], 
                                 original_to_alignment: List[int], format_mapping: FormatMapping,
                                 consensus_group_sizes: List[int]) -> Dict[str, Any]:
        """Create a formatted sequence with both Type 1 and Type 2 formatting."""
        logger.info(f"🎨 CREATING FORMATTED SEQUENCE ► {draft_id}")
        logger.info(f"   📊 Input: {len(aligned_tokens)} aligned tokens, {len(original_to_alignment)} alignment mappings")
        logger.info(f"   🎯 Consensus group sizes: {len(consensus_group_sizes)} groups")
        
        # Count non-gap tokens for validation
        non_gap_tokens = [token for token in aligned_tokens if token != '-']
        logger.info(f"   🔤 Non-gap tokens: {len(non_gap_tokens)} (from {len(aligned_tokens)} total)")
        
        # Type 2: Get formatted tokens (before consensus grouping)
        logger.info("   🔧 TYPE 2 FORMATTING ► Getting formatted tokens")
        formatted_tokens = self.get_formatted_tokens(aligned_tokens, format_mapping, original_to_alignment)
        logger.info(f"   ✅ Type 2 formatted tokens: {len(formatted_tokens)} tokens")
        logger.info(f"      First 10 formatted tokens: {formatted_tokens[:10]}")
        
        # Apply consensus grouping to formatted tokens
        if consensus_group_sizes:
            logger.info(f"   🎯 APPLYING CONSENSUS GROUPING ► {len(consensus_group_sizes)} group sizes to {len(formatted_tokens)} tokens")
            display_tokens = self.apply_type2_grouping(formatted_tokens, consensus_group_sizes)
            logger.info(f"   ✅ Consensus grouping result: {len(display_tokens)} grouped tokens")
        else:
            logger.info("   ⚠️ No consensus grouping available, using formatted tokens as-is")
            display_tokens = formatted_tokens
        
        # Reconstruct with gaps
        logger.info("   🔗 Reconstructed with gaps: {len(display_tokens)} tokens")
        
        # Type 1: Exact text restoration
        logger.info("   📄 TYPE 1 FORMATTING ► Exact text restoration")
        exact_text = self.reconstruct_type1_exact(aligned_tokens, format_mapping, original_to_alignment)
        logger.info(f"   ✅ Type 1 exact text: {len(exact_text)} characters")
        logger.info(f"      Text preview: '{exact_text[:50]}...'")
        
        # Create position mapping
        position_mapping = self._create_position_mapping(aligned_tokens, display_tokens)
        logger.info(f"   🗺️ Position mapping: {len(position_mapping)} mappings created")
        
        result = {
            'tokens': aligned_tokens,                    # Original aligned tokens
            'display_tokens': display_tokens,            # Type 2: Formatted tokens for table/heatmap
            'exact_text': exact_text,                   # Type 1: Exact text for draft viewer
            'position_mapping': position_mapping,        # Maps alignment positions to display positions
            'formatting_applied': True,
            'metadata': {
                'original_token_count': len(non_gap_tokens),
                'aligned_token_count': len(aligned_tokens),
                'display_token_count': len(display_tokens),
                'exact_text_length': len(exact_text),
                'consensus_groups_applied': len(consensus_group_sizes) > 0
            }
        }
        
        logger.info(f"🎉 FORMATTED SEQUENCE COMPLETE ► {draft_id}")
        logger.info(f"   📊 Final structure: tokens={len(aligned_tokens)}, display_tokens={len(display_tokens)}, exact_text={len(exact_text)} chars")
        
        return result

    def _create_fallback_sequence(self, draft_id: str, aligned_tokens: List[str], 
                                original_to_alignment: List[int]) -> Dict[str, Any]:
        """Create a fallback sequence when formatting fails."""
        logger.warning(f"⚠️ CREATING FALLBACK SEQUENCE ► {draft_id}")
        
        # Simple fallback: use aligned tokens as-is
        non_gap_tokens = [token for token in aligned_tokens if token != '-']
        exact_text = ' '.join(non_gap_tokens)
        
        return {
            'tokens': aligned_tokens,
            'display_tokens': aligned_tokens,  # No formatting applied
            'exact_text': exact_text,         # Simple space-separated text
            'position_mapping': {i: i for i in range(len(aligned_tokens))},  # 1:1 mapping
            'formatting_applied': False,
            'metadata': {
                'original_token_count': len(non_gap_tokens),
                'aligned_token_count': len(aligned_tokens),
                'display_token_count': len(aligned_tokens),
                'exact_text_length': len(exact_text),
                'fallback_used': True
            }
        }

    def _reconstruct_with_gaps(self, aligned_tokens: List[str], 
                             formatted_non_gap_tokens: List[str]) -> List[str]:
        """Reconstruct formatted tokens with gaps in the correct positions."""
        result = []
        formatted_idx = 0
        
        for token in aligned_tokens:
            if token == '-':
                result.append('-')  # Preserve gap
            else:
                if formatted_idx < len(formatted_non_gap_tokens):
                    result.append(formatted_non_gap_tokens[formatted_idx])
                    formatted_idx += 1
                else:
                    result.append(token)  # Fallback to original token
        
        return result

    def _create_position_mapping(self, aligned_tokens: List[str], 
                               display_tokens: List[str]) -> Dict[int, Optional[int]]:
        """Create mapping from alignment positions to display positions."""
        mapping = {}
        display_idx = 0
        
        for align_idx, token in enumerate(aligned_tokens):
            if token == '-':
                mapping[align_idx] = None  # Gap has no display position
            else:
                if display_idx < len(display_tokens):
                    mapping[align_idx] = display_idx
                    display_idx += 1
                else:
                    mapping[align_idx] = None  # No corresponding display token
        
        return mapping

    def reconstruct_type1_exact(self, aligned_tokens: List[str], format_mapping: FormatMapping,
                               original_to_alignment: List[int]) -> str:
        """
        Reconstruct exact original text (Type 1) from aligned tokens.
        
        Maps back through: aligned tokens → original tokens → exact original text
        """
        if not format_mapping or not format_mapping.token_positions:
            # Fallback: simple space-separated text
            non_gap_tokens = [token for token in aligned_tokens if token != '-']
            return ' '.join(non_gap_tokens)
        
        # Build reverse mapping: alignment position → original token index
        alignment_to_original = {}
        for orig_idx, align_pos in enumerate(original_to_alignment):
            if align_pos != -1:
                alignment_to_original[align_pos] = orig_idx
        
        # Reconstruct text by going through alignment positions in order
        text_parts = []
        for align_pos, token in enumerate(aligned_tokens):
            if token == '-':
                continue  # Skip gaps
            
            orig_idx = alignment_to_original.get(align_pos)
            if orig_idx is not None:
                # Get original text for this token
                token_pos = format_mapping.get_position_for_token(orig_idx)
                if token_pos:
                    text_parts.append(token_pos.original_text)
                else:
                    text_parts.append(token)  # Fallback
            else:
                text_parts.append(token)  # Fallback
        
        return ' '.join(text_parts)

    def compute_consensus_groupings(self, alignment_results: Dict[str, Any],
                                  format_mappings: Dict[str, Dict[str, FormatMapping]]) -> Dict[str, Dict[str, List[int]]]:
        """
        Compute consensus groupings for Type 2 formatting.
        
        Analyzes how many formatted tokens each normalized token maps to across drafts,
        then creates a consensus grouping that anchors all drafts consistently.
        """
        logger.info("🎯 COMPUTING CONSENSUS GROUPINGS ► Analyzing token mappings across drafts")
        
        consensus_groupings = {}
        total_positions_analyzed = 0
        positions_with_conflicts = 0
        
        blocks = alignment_results.get('blocks', {})
        
        for block_id, align_block in blocks.items():
            logger.info(f"   📋 Processing consensus for block: {block_id}")
            
            block_groupings = {}
            aligned_sequences = align_block.get('aligned_sequences', [])
            
            if not aligned_sequences:
                logger.warning(f"   ⚠️ No aligned sequences for block {block_id}")
                continue
            
            # FIXED: Get alignment length from first sequence
            alignment_length = len(aligned_sequences[0].get('tokens', []))
            logger.info(f"   📏 Alignment length: {alignment_length} positions")
            
            # Step 1: Analyze how many formatted tokens each normalized token maps to
            logger.info("   🔍 Analyzing token mappings across drafts")
            position_analysis = self._analyze_token_mappings(
                aligned_sequences, format_mappings.get(block_id, {}), block_id
            )
            
            # Step 2: Compute consensus grouping for each position
            consensus_group_sizes = []
            for pos in range(alignment_length):
                if pos < len(position_analysis):
                    # Use maximum group size across all drafts for this position
                    position_counts = position_analysis[pos]
                    if position_counts:
                        max_group_size = max(position_counts.values())
                        min_group_size = min(position_counts.values())
                        
                        if max_group_size != min_group_size:
                            positions_with_conflicts += 1
                            logger.info(f"   🔥 CONFLICT at position {pos}: sizes range from {min_group_size} to {max_group_size}")
                            logger.info(f"      Draft mappings: {position_counts}")
                            logger.info(f"      Using consensus size: {max_group_size}")
                        
                        consensus_group_sizes.append(max_group_size)
                    else:
                        consensus_group_sizes.append(1)
                else:
                    consensus_group_sizes.append(1)
                
                total_positions_analyzed += 1
            
            # Step 3: Apply consensus grouping to all drafts
            for seq in aligned_sequences:
                draft_id = seq.get('draft_id')
                if draft_id:
                    block_groupings[draft_id] = consensus_group_sizes.copy()
                    logger.debug(f"   ✅ Applied consensus grouping to {draft_id}: {len(consensus_group_sizes)} positions")
            
            consensus_groupings[block_id] = block_groupings
            logger.info(f"   📊 Block {block_id}: {len(block_groupings)} drafts with consensus grouping")
        
        logger.info(f"🎊 CONSENSUS GROUPINGS COMPLETE ► {len(consensus_groupings)} blocks processed")
        logger.info(f"   📊 Total positions analyzed: {total_positions_analyzed}")
        logger.info(f"   🔥 Positions with conflicts: {positions_with_conflicts}")
        logger.info(f"   📈 Conflict rate: {(positions_with_conflicts/max(total_positions_analyzed, 1)*100):.1f}%")
        
        return consensus_groupings

    def get_formatted_tokens(self, aligned_tokens: List[str], format_mapping: FormatMapping,
                             original_to_alignment: List[int]) -> List[str]:
        """
        Get formatted tokens from aligned tokens using format mapping.
        
        This is used for Type 2 display before consensus grouping is applied.
        """
        logger.debug(f"🔤 GETTING FORMATTED TOKENS ► {len(aligned_tokens)} aligned tokens")
        logger.debug(f"   Format mapping positions: {len(format_mapping.token_positions) if format_mapping and format_mapping.token_positions else 0}")
        logger.debug(f"   Original to alignment mappings: {len(original_to_alignment)}")
        
        if not aligned_tokens or not format_mapping or not format_mapping.token_positions:
            logger.warning("⚠️ FORMATTED TOKENS FALLBACK ► Missing data, returning aligned tokens as-is")
            return aligned_tokens  # Fallback
        
        formatted_tokens = []
        
        # Build reverse mapping: alignment position -> original token indices
        alignment_to_original = self._build_alignment_to_original_mapping(
            original_to_alignment, len(aligned_tokens)
        )
        logger.debug(f"   🗺️ Built reverse mapping: {len(alignment_to_original)} alignment positions mapped")
        
        for align_pos, token in enumerate(aligned_tokens):
            if token == '-':
                formatted_tokens.append('-')  # Preserve gaps
                logger.debug(f"   Position {align_pos}: gap preserved")
                continue
            
            # Find original token indices for this alignment position
            original_indices = alignment_to_original.get(align_pos, [])
            
            if not original_indices:
                formatted_tokens.append(token)  # Fallback to aligned token
                logger.debug(f"   Position {align_pos}: '{token}' (no original mapping, using as-is)")
                continue
            
            # Get formatted tokens for these original indices
            formatted_for_position = []
            for orig_idx in original_indices:
                token_pos = format_mapping.get_position_for_token(orig_idx)
                if token_pos:
                    formatted_for_position.append(token_pos.original_text)
                    logger.debug(f"      Original index {orig_idx}: '{token_pos.normalized_text}' → '{token_pos.original_text}'")
                else:
                    formatted_for_position.append(token)  # Fallback
                    logger.debug(f"      Original index {orig_idx}: no position found, using '{token}'")
            
            # For now, just use the first formatted token
            # The consensus grouping will handle merging later
            if formatted_for_position:
                formatted_tokens.append(formatted_for_position[0])
                logger.debug(f"   Position {align_pos}: '{token}' → '{formatted_for_position[0]}' (used first of {len(formatted_for_position)})")
            else:
                formatted_tokens.append(token)
                logger.debug(f"   Position {align_pos}: '{token}' (no formatted versions found)")
        
        logger.debug(f"✅ FORMATTED TOKENS COMPLETE ► {len(formatted_tokens)} tokens processed")
        return formatted_tokens

    def _analyze_token_mappings(self, aligned_sequences: List[Dict], 
                               format_mappings: Dict[str, FormatMapping], 
                               block_id: str) -> List[Dict[str, int]]:
        """Analyze how many formatted tokens each normalized token maps to across drafts."""
        logger.debug(f"🔍 ANALYZING TOKEN MAPPINGS ► Block {block_id}")
        
        if not aligned_sequences:
            logger.warning(f"   ⚠️ No aligned sequences for analysis")
            return []
        
        alignment_length = len(aligned_sequences[0].get('tokens', []))
        position_analysis = [{} for _ in range(alignment_length)]
        
        logger.debug(f"   📏 Analyzing {alignment_length} positions across {len(aligned_sequences)} sequences")
        
        for seq in aligned_sequences:
            draft_id = seq.get('draft_id')
            if not draft_id or draft_id not in format_mappings:
                logger.warning(f"   ⚠️ Skipping {draft_id}: no format mapping available")
                continue
                
            format_mapping = format_mappings[draft_id]
            aligned_tokens = seq.get('tokens', [])
            original_to_alignment = seq.get('original_to_alignment', [])
            
            logger.debug(f"   🔤 Analyzing {draft_id}: {len(aligned_tokens)} tokens, {len(original_to_alignment)} mappings")
            
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
                
                if formatted_token_count > 1:
                    logger.debug(f"   🎯 {draft_id} pos {align_pos}: {len(original_indices)} orig indices → {formatted_token_count} formatted tokens")
        
        logger.debug(f"✅ TOKEN MAPPING ANALYSIS COMPLETE ► {len(position_analysis)} positions analyzed")
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
                # For now, count each position as 1 formatted token
                # This could be enhanced to split on whitespace if needed
                formatted_tokens.add(token_pos.original_text)
        
        return len(formatted_tokens) if formatted_tokens else len(original_indices)

    def apply_type2_grouping(self, formatted_tokens: List[str], group_sizes: List[int]) -> List[str]:
        """
        Apply consensus grouping to formatted tokens for Type 2 display.
        
        Groups consecutive tokens according to consensus group sizes to ensure
        consistent positioning across all drafts in the table/heatmap view.
        """
        if not group_sizes or len(group_sizes) != len(formatted_tokens):
            logger.warning(f"⚠️ GROUP SIZE MISMATCH ► tokens={len(formatted_tokens)}, groups={len(group_sizes)}")
            return formatted_tokens  # Fallback
        
        grouped_tokens = []
        i = 0
        
        for group_size in group_sizes:
            if group_size <= 0:
                continue  # Skip invalid group sizes
            
            # Collect tokens for this group
            group_tokens = []
            for _ in range(group_size):
                if i < len(formatted_tokens):
                    group_tokens.append(formatted_tokens[i])
                    i += 1
            
            if group_tokens:
                # Merge tokens in this group intelligently
                merged_token = self._merge_tokens_intelligently(group_tokens)
                grouped_tokens.append(merged_token)
        
        return grouped_tokens

    def _merge_tokens_intelligently(self, tokens: List[str]) -> str:
        """
        Intelligently merge multiple tokens into a single display token.
        
        Handles cases like:
        - ['4°', '00'', 'W.'] → '4°00'W.'
        - ['North', 'West'] → 'North West'
        """
        if not tokens:
            return ""
        
        if len(tokens) == 1:
            return tokens[0]
        
        # Check if tokens look like they should be concatenated (coordinates, etc.)
        merged = ''.join(tokens)
        
        # If the merged result looks like a coordinate or technical term, use it
        if any(char in merged for char in ['°', "'", '"', '(', ')']):
            return merged
        
        # Otherwise, join with spaces
        return ' '.join(tokens) 