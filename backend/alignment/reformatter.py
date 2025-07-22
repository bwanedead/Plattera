"""
Reformatter module for post-alignment text processing.
ORCHESTRATOR ONLY - delegates to completely separate Type 1 and Type 2 formatters.
"""

from typing import Dict, List, Any, Tuple, Optional
from alignment.format_mapping import FormatMapping
from alignment.type1_exact_formatter import Type1ExactFormatter
from alignment.type2_display_formatter import Type2DisplayFormatter, Type2ConsensusAnalyzer
import logging

logger = logging.getLogger(__name__)


class Reformatter:
    """
    Main reformatter that orchestrates completely separate Type 1 and Type 2 formatters.
    
    This class ONLY orchestrates - it does NOT contain any formatting logic.
    All formatting logic is delegated to completely separate, isolated formatters.
    """

    def __init__(self):
        # Initialize completely separate formatters
        self.type1_formatter = Type1ExactFormatter()
        self.type2_formatter = Type2DisplayFormatter()
        self.type2_consensus_analyzer = Type2ConsensusAnalyzer()

    def create_frontend_alignment_results(self, alignment_results: Dict[str, Any], 
                                        tokenized_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create frontend-ready alignment results with proper formatting.
        
        This method ONLY orchestrates - all formatting is done by separate formatters.
        """
        logger.info("🎨 REFORMATTER ORCHESTRATOR ► Creating frontend alignment results")
        
        # Extract format mappings
        format_mappings = self._extract_format_mappings_from_tokenized_data(tokenized_data)
        logger.info(f"✅ FORMAT MAPPINGS ► Extracted for {len(format_mappings)} blocks")
        
        # Compute Type 2 consensus groupings (completely separate from Type 1)
        logger.info("🎯 TYPE 2 STEP ► Computing consensus groupings")
        consensus_groupings = self.type2_consensus_analyzer.compute_consensus_groupings(
            alignment_results, format_mappings
        )
        logger.info(f"✅ TYPE 2 CONSENSUS ► Computed for {len(consensus_groupings)} blocks")
        
        # Process alignment blocks (orchestrate both formatters separately)
        logger.info("🔧 ORCHESTRATING ► Processing alignment blocks with separate formatters")
        processed_results = self._process_alignment_blocks(
            alignment_results, format_mappings, consensus_groupings
        )
        logger.info(f"✅ ORCHESTRATION COMPLETE ► {len(processed_results.get('blocks', {}))} blocks processed")
        
        return processed_results

    def _extract_format_mappings_from_tokenized_data(self, tokenized_data: Dict[str, Any]) -> Dict[str, Dict[str, FormatMapping]]:
        """Extract format mappings that were created during tokenization."""
        format_mappings = {}
        blocks = tokenized_data.get('blocks', {})
        
        for block_id, block_data in blocks.items():
            block_format_mappings = block_data.get('format_mappings', {})
            format_mappings[block_id] = block_format_mappings  # Fixed indentation
        
        return format_mappings

    def _process_alignment_blocks(self, alignment_results: Dict[str, Any], 
                                format_mappings: Dict[str, Dict[str, FormatMapping]],
                                consensus_groupings: Dict[str, Dict[str, List[int]]]) -> Dict[str, Any]:
        """
        Process each alignment block by orchestrating separate Type 1 and Type 2 formatters.
        
        This method ONLY orchestrates - it does NOT contain any formatting logic.
        """
        logger.info("🔧 ORCHESTRATING BLOCK PROCESSING ► Using separate formatters")
        
        processed_blocks = {}
        
        blocks = alignment_results.get('blocks', {})
        
        for block_id, align_block in blocks.items():
            logger.info(f"   📋 Orchestrating block: {block_id}")
            
            aligned_sequences = align_block.get('aligned_sequences', [])
            consensus_group_sizes = consensus_groupings.get(block_id, {})
            
            if not aligned_sequences:
                logger.warning(f"   ⚠️ No aligned sequences for block {block_id}")
                continue
            
            formatted_aligned_sequences = []
            
            for seq in aligned_sequences:
                draft_id = seq.get('draft_id')
                aligned_tokens = seq.get('tokens', [])
                original_to_alignment = seq.get('original_to_alignment', [])
                
                logger.info(f"      🔤 Orchestrating sequence {draft_id}")
                
                # Get format mapping for this draft
                format_mapping = format_mappings.get(block_id, {}).get(draft_id)
                group_sizes = consensus_group_sizes.get(draft_id, [])
                
                if format_mapping:
                    try:
                        # TYPE 1: Exact text reconstruction (completely separate)
                        logger.info("      📄 Delegating to Type 1 formatter")
                        exact_text = self.type1_formatter.reconstruct_exact_original_text(
                            aligned_tokens, format_mapping, original_to_alignment
                        )
                        logger.info(f"      ✅ Type 1 complete: {len(exact_text)} characters")
                        
                        # TYPE 2: Display tokens creation (completely separate)
                        logger.info("      🔧 Delegating to Type 2 formatter")
                        display_tokens = self.type2_formatter.create_display_tokens(
                            aligned_tokens, format_mapping, original_to_alignment, group_sizes
                        )
                        logger.info(f"      ✅ Type 2 complete: {len(display_tokens)} tokens")
                        
                        # Combine results (no cross-contamination)
                        formatted_aligned_sequences.append({
                            'draft_id': draft_id,
                            'tokens': display_tokens,           # Type 2 output for table
                            'original_to_alignment': original_to_alignment,
                            'exact_text': exact_text,          # Type 1 output for viewer
                            'formatting_applied': True,
                            'metadata': {
                                'type1_text_length': len(exact_text),
                                'type2_token_count': len(display_tokens),
                                'formatters_used': ['Type1ExactFormatter', 'Type2DisplayFormatter']
                            }
                        })
                        
                        logger.info(f"      🎉 Orchestration success: {draft_id}")
                        
                    except Exception as e:
                        logger.error(f"      ❌ Orchestration error for {draft_id}: {e}")
                        # Fallback
                        formatted_aligned_sequences.append({
                            'draft_id': draft_id,
                            'tokens': aligned_tokens,
                            'original_to_alignment': original_to_alignment,
                            'exact_text': ' '.join([t for t in aligned_tokens if t != '-']),
                            'formatting_applied': False
                        })
                else:
                    logger.warning(f"      ⚠️ No format mapping for {draft_id}")
                    # Fallback
                    formatted_aligned_sequences.append({
                        'draft_id': draft_id,
                        'tokens': aligned_tokens,
                        'original_to_alignment': original_to_alignment,
                        'exact_text': ' '.join([t for t in aligned_tokens if t != '-']),
                        'formatting_applied': False
                    })
            
            processed_blocks[block_id] = {
                'aligned_sequences': formatted_aligned_sequences,
                'alignment_length': len(formatted_aligned_sequences[0].get('tokens', [])) if formatted_aligned_sequences else 0,
                'draft_count': len(formatted_aligned_sequences),
                'block_id': block_id
            }
        
        return {
            'blocks': processed_blocks,
            'summary': {
                'total_blocks': len(processed_blocks),
                'formatters_used': ['Type1ExactFormatter', 'Type2DisplayFormatter'],
                'isolation_confirmed': True
            }
        } 