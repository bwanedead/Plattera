"""
Consensus Draft Generator
========================

Generates consensus drafts from Type 2 alignment table results.
Takes the display tokens from Type2DisplayFormatter output and creates
consensus by selecting the most common token at each position.

This is COMPLETELY SEPARATE and does NOT modify any existing alignment code.
"""

from typing import Dict, List, Any
from collections import Counter
import logging

logger = logging.getLogger(__name__)


class ConsensusDraftGenerator:
    """
    Generates consensus drafts from Type 2 display tokens.
    
    Takes the already-processed alignment results (with Type 2 tokens)
    and creates consensus drafts by selecting the most common token at each position.
    """
    
    GAP = "-"
    
    def generate_consensus_draft(self, alignment_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate consensus drafts from Type 2 alignment results.
        
        Args:
            alignment_results: The complete alignment results from reformatter
            
        Returns:
            Dictionary with consensus sequences for each block
        """
        logger.info("🎯 CONSENSUS GENERATOR ► Creating consensus from Type 2 tokens")
        
        consensus_sequences = {}
        blocks = alignment_results.get('blocks', {})
        
        for block_id, block_data in blocks.items():
            logger.info(f"   📋 Processing block: {block_id}")
            
            aligned_sequences = block_data.get('aligned_sequences', [])
            
            if len(aligned_sequences) < 2:
                logger.info(f"   ⚠️ Skipping block {block_id} - need at least 2 drafts")
                continue
            
            # Extract Type 2 tokens from all sequences (exclude any existing consensus)
            token_sequences = []
            draft_ids = []
            
            for sequence in aligned_sequences:
                draft_id = sequence.get('draft_id')
                tokens = sequence.get('tokens', [])
                
                if draft_id and draft_id != 'consensus':
                    token_sequences.append(tokens)
                    draft_ids.append(draft_id)
            
            if not token_sequences:
                logger.warning(f"   ⚠️ No valid sequences for block {block_id}")
                continue
            
            # Generate consensus tokens
            consensus_tokens = self._create_consensus_tokens(token_sequences)
            
            # Create consensus text (join non-gap tokens)
            consensus_text = ' '.join([token for token in consensus_tokens if token != self.GAP])
            
            # Create consensus sequence with same structure as other sequences
            consensus_sequence = {
                'draft_id': 'consensus',
                'tokens': consensus_tokens,
                'original_to_alignment': list(range(len(consensus_tokens))),
                'exact_text': consensus_text,
                'formatting_applied': True,
                'metadata': {
                    'generation_method': 'type2_most_common',
                    'source_drafts': draft_ids,
                    'token_count': len(consensus_tokens),
                    'text_length': len(consensus_text)
                }
            }
            
            consensus_sequences[block_id] = consensus_sequence
            logger.info(f"   ✅ Generated consensus: {len(consensus_tokens)} tokens")
        
        logger.info(f"✅ CONSENSUS COMPLETE ► Generated {len(consensus_sequences)} drafts")
        return consensus_sequences
    
    def _create_consensus_tokens(self, token_sequences: List[List[str]]) -> List[str]:
        """
        Create consensus tokens by selecting most common token at each position.
        
        Args:
            token_sequences: List of token sequences from Type 2 formatter
            
        Returns:
            List of consensus tokens
        """
        if not token_sequences:
            return []
        
        # All sequences should be same length (from alignment)
        alignment_length = len(token_sequences[0])
        consensus_tokens = []
        
        for position in range(alignment_length):
            # Collect all non-gap tokens at this position
            tokens_at_position = []
            
            for sequence in token_sequences:
                if position < len(sequence):
                    token = sequence[position]
                    if token != self.GAP:
                        tokens_at_position.append(token)
            
            # Select most common token, or gap if none
            if tokens_at_position:
                token_counts = Counter(tokens_at_position)
                most_common_token = token_counts.most_common(1)[0][0]
                consensus_tokens.append(most_common_token)
            else:
                consensus_tokens.append(self.GAP)
        
        return consensus_tokens 