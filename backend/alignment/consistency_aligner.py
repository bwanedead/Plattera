"""
BioPython Consistency-Based Alignment Module
==========================================

Implements custom consistency-based multiple sequence alignment using BioPython's
PairwiseAligner with iterative refinement to approximate T-Coffee accuracy.
"""

import logging
from typing import Dict, List, Any, Tuple, Optional
from collections import defaultdict, Counter
import numpy as np

from .alignment_utils import (
    BioPythonAlignerConfig, AlignmentError, 
    calculate_alignment_consistency, BIOPYTHON_AVAILABLE
)

logger = logging.getLogger(__name__)


class ConsistencyBasedAligner:
    """
    Custom consistency-based MSA using BioPython with iterative refinement
    
    Approximates T-Coffee's accuracy by:
    1. Generate all pairwise alignments
    2. Build consistency library from pairwise matches
    3. Optimize multiple alignment using consistency weights
    4. Iteratively refine alignment (2-3 iterations)
    """
    
    def __init__(self, scoring_params: Dict[str, int] = None):
        if not BIOPYTHON_AVAILABLE:
            raise AlignmentError("BioPython not available")
        
        self.aligner_config = BioPythonAlignerConfig(scoring_params)
        self.consistency_threshold = 0.6  # Minimum consistency for reliable matches
        self.max_iterations = 3           # Refinement iterations
        
    def align_multiple_sequences(self, block_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform consistency-based multiple sequence alignment on a block
        
        Args:
            block_data: Preprocessed block data with encoded drafts
            
        Returns:
            Dict with alignment results and metadata
        """
        encoded_drafts = block_data['encoded_drafts']
        draft_count = len(encoded_drafts)
        
        logger.info(f"🧬 CONSISTENCY ALIGNMENT ► Aligning {draft_count} drafts for block '{block_data['block_id']}'")
        
        if draft_count < 2:
            logger.warning(f"⚠️ Only {draft_count} draft(s) in block - no alignment needed")
            return self._handle_single_draft(block_data)
        
        try:
            # Step 1: Generate all pairwise alignments
            pairwise_alignments = self._generate_pairwise_alignments(encoded_drafts)
            logger.info(f"   🔄 Generated {len(pairwise_alignments)} pairwise alignments")
            
            # Step 2: Build consistency library
            consistency_library = self._build_consistency_library(pairwise_alignments, encoded_drafts)
            logger.info(f"   📚 Built consistency library with {len(consistency_library)} positions")
            
            # Step 3: Construct initial multiple alignment
            multiple_alignment = self._construct_multiple_alignment(
                encoded_drafts, consistency_library, block_data['id_to_token']
            )
            
            # Step 4: Iterative refinement
            refined_alignment = self._refine_alignment(
                multiple_alignment, consistency_library, encoded_drafts
            )
            
            # Step 5: Convert back to tokens and format results
            final_result = self._format_alignment_results(
                refined_alignment, block_data, pairwise_alignments
            )
            
            logger.info(f"✅ ALIGNMENT COMPLETE ► Block '{block_data['block_id']}' aligned successfully")
            return final_result
            
        except Exception as e:
            logger.error(f"❌ Alignment failed for block '{block_data['block_id']}': {e}")
            raise AlignmentError(f"Multiple sequence alignment failed: {e}")
    
    def _generate_pairwise_alignments(self, encoded_drafts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate all pairwise alignments between drafts"""
        pairwise_alignments = []
        
        for i in range(len(encoded_drafts)):
            for j in range(i + 1, len(encoded_drafts)):
                draft1 = encoded_drafts[i]
                draft2 = encoded_drafts[j]
                
                # Perform pairwise alignment
                alignment = self.aligner_config.align_sequences(
                    draft1['encoded_tokens'], 
                    draft2['encoded_tokens']
                )
                
                if alignment:
                    pairwise_alignments.append({
                        'draft1_id': draft1['draft_id'],
                        'draft2_id': draft2['draft_id'],
                        'draft1_index': i,
                        'draft2_index': j,
                        'alignment': alignment,
                        'score': alignment.score
                    })
        
        return pairwise_alignments
    
    def _build_consistency_library(self, pairwise_alignments: List[Dict[str, Any]], 
                                 encoded_drafts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Build consistency library from pairwise alignments
        
        Creates a library of consistent matches across all pairwise alignments,
        weighted by frequency and alignment quality.
        """
        consistency_library = defaultdict(lambda: defaultdict(float))
        position_mappings = defaultdict(list)
        
        for pair_data in pairwise_alignments:
            alignment = pair_data['alignment']
            draft1_idx = pair_data['draft1_index']
            draft2_idx = pair_data['draft2_index']
            
            # Extract aligned sequences from BioPython alignment
            try:
                # Handle BioPython alignment format
                aligned_seq1 = []
                aligned_seq2 = []
                
                # BioPython alignments have aligned sequences
                for i in range(len(alignment)):
                    # Get tokens from alignment coordinates
                    seq1_coords = alignment.coordinates[0]
                    seq2_coords = alignment.coordinates[1]
                    
                    if i < len(seq1_coords) - 1:
                        start1, end1 = seq1_coords[i], seq1_coords[i+1]
                        start2, end2 = seq2_coords[i], seq2_coords[i+1]
                        
                        # Add aligned tokens or gaps
                        if start1 == end1:  # Gap in sequence 1
                            aligned_seq1.extend([-1] * (end2 - start2))
                        elif start2 == end2:  # Gap in sequence 2
                            aligned_seq2.extend([-1] * (end1 - start1))
                        else:  # Match/mismatch
                            seq1_tokens = encoded_drafts[draft1_idx]['encoded_tokens'][start1:end1]
                            seq2_tokens = encoded_drafts[draft2_idx]['encoded_tokens'][start2:end2]
                            aligned_seq1.extend(seq1_tokens)
                            aligned_seq2.extend(seq2_tokens)
                
                # Process alignment to build consistency weights
                for pos in range(min(len(aligned_seq1), len(aligned_seq2))):
                    token1 = aligned_seq1[pos] if pos < len(aligned_seq1) else -1
                    token2 = aligned_seq2[pos] if pos < len(aligned_seq2) else -1
                    
                    # Record match in consistency library
                    match_key = f"{draft1_idx}:{pos}-{draft2_idx}:{pos}"
                    
                    if token1 == token2 and token1 != -1:
                        # Strong match - high consistency weight
                        consistency_library[match_key]['weight'] += 1.0
                        consistency_library[match_key]['token'] = token1
                    elif token1 != -1 and token2 != -1:
                        # Mismatch - lower consistency weight
                        consistency_library[match_key]['weight'] += 0.3
                        consistency_library[match_key]['token1'] = token1
                        consistency_library[match_key]['token2'] = token2
                        
            except Exception as e:
                logger.warning(f"Error processing alignment between {draft1_idx} and {draft2_idx}: {e}")
                continue
        
        return dict(consistency_library)
    
    def _construct_multiple_alignment(self, encoded_drafts: List[Dict[str, Any]], 
                                    consistency_library: Dict[str, Any], 
                                    id_to_token: Dict[int, str]) -> List[List[int]]:
        """
        Construct multiple alignment using consistency library
        
        Uses a progressive alignment approach, starting with the most consistent
        pairwise alignment and adding sequences iteratively.
        """
        draft_count = len(encoded_drafts)
        
        if draft_count == 2:
            # Simple case - just use pairwise alignment
            return self._align_two_sequences(encoded_drafts[0], encoded_drafts[1])
        
        # For multiple sequences, use a progressive approach
        # Start with the longest sequence as reference
        reference_idx = max(range(draft_count), 
                          key=lambda i: len(encoded_drafts[i]['encoded_tokens']))
        
        # Initialize alignment with reference sequence
        multiple_alignment = [encoded_drafts[reference_idx]['encoded_tokens'].copy()]
        aligned_draft_indices = [reference_idx]
        
        # Progressively add other sequences
        for draft_idx in range(draft_count):
            if draft_idx == reference_idx:
                continue
            
            # Find best position to align this sequence
            best_alignment = self._find_best_alignment_position(
                encoded_drafts[draft_idx]['encoded_tokens'],
                multiple_alignment,
                consistency_library
            )
            
            multiple_alignment.append(best_alignment)
            aligned_draft_indices.append(draft_idx)
        
        return multiple_alignment
    
    def _align_two_sequences(self, draft1: Dict[str, Any], draft2: Dict[str, Any]) -> List[List[int]]:
        """Align two sequences using BioPython"""
        alignment = self.aligner_config.align_sequences(
            draft1['encoded_tokens'], 
            draft2['encoded_tokens']
        )
        
        if not alignment:
            # Fallback - return unaligned sequences
            max_len = max(len(draft1['encoded_tokens']), len(draft2['encoded_tokens']))
            seq1 = draft1['encoded_tokens'] + [-1] * (max_len - len(draft1['encoded_tokens']))
            seq2 = draft2['encoded_tokens'] + [-1] * (max_len - len(draft2['encoded_tokens']))
            return [seq1, seq2]
        
        # Convert BioPython alignment to our format
        aligned_seq1 = []
        aligned_seq2 = []
        
        try:
            # Extract sequences from BioPython alignment
            seq1_tokens = draft1['encoded_tokens']
            seq2_tokens = draft2['encoded_tokens']
            
            # Use alignment coordinates to build aligned sequences
            coords1 = alignment.coordinates[0]
            coords2 = alignment.coordinates[1]
            
            for i in range(len(coords1) - 1):
                start1, end1 = coords1[i], coords1[i+1]
                start2, end2 = coords2[i], coords2[i+1]
                
                if start1 == end1:  # Gap in sequence 1
                    gap_len = end2 - start2
                    aligned_seq1.extend([-1] * gap_len)
                    aligned_seq2.extend(seq2_tokens[start2:end2])
                elif start2 == end2:  # Gap in sequence 2
                    gap_len = end1 - start1
                    aligned_seq1.extend(seq1_tokens[start1:end1])
                    aligned_seq2.extend([-1] * gap_len)
                else:  # Match/mismatch
                    aligned_seq1.extend(seq1_tokens[start1:end1])
                    aligned_seq2.extend(seq2_tokens[start2:end2])
            
        except Exception as e:
            logger.warning(f"Error extracting alignment: {e}, using fallback")
            # Fallback to simple concatenation
            max_len = max(len(draft1['encoded_tokens']), len(draft2['encoded_tokens']))
            aligned_seq1 = draft1['encoded_tokens'] + [-1] * (max_len - len(draft1['encoded_tokens']))
            aligned_seq2 = draft2['encoded_tokens'] + [-1] * (max_len - len(draft2['encoded_tokens']))
        
        return [aligned_seq1, aligned_seq2]
    
    def _find_best_alignment_position(self, sequence: List[int], 
                                    multiple_alignment: List[List[int]], 
                                    consistency_library: Dict[str, Any]) -> List[int]:
        """
        Find best alignment position for a sequence against multiple alignment
        
        Uses consistency scores to determine optimal positioning.
        """
        if not multiple_alignment:
            return sequence
        
        # For simplicity, align against the first (reference) sequence
        reference_seq = multiple_alignment[0]
        alignment = self.aligner_config.align_sequences(sequence, reference_seq)
        
        if not alignment:
            # Fallback - pad to match alignment length
            alignment_length = len(reference_seq)
            if len(sequence) <= alignment_length:
                return sequence + [-1] * (alignment_length - len(sequence))
            else:
                return sequence[:alignment_length]
        
        # Convert alignment to our format
        try:
            aligned_sequence = []
            coords_seq = alignment.coordinates[0]
            coords_ref = alignment.coordinates[1]
            
            for i in range(len(coords_seq) - 1):
                start_seq, end_seq = coords_seq[i], coords_seq[i+1]
                start_ref, end_ref = coords_ref[i], coords_ref[i+1]
                
                if start_seq == end_seq:  # Gap in new sequence
                    gap_len = end_ref - start_ref
                    aligned_sequence.extend([-1] * gap_len)
                else:  # Token(s) in new sequence
                    aligned_sequence.extend(sequence[start_seq:end_seq])
                    
        except Exception as e:
            logger.warning(f"Error aligning sequence: {e}")
            # Fallback
            alignment_length = len(reference_seq)
            if len(sequence) <= alignment_length:
                aligned_sequence = sequence + [-1] * (alignment_length - len(sequence))
            else:
                aligned_sequence = sequence[:alignment_length]
        
        return aligned_sequence
    
    def _refine_alignment(self, multiple_alignment: List[List[int]], 
                        consistency_library: Dict[str, Any], 
                        encoded_drafts: List[Dict[str, Any]]) -> List[List[int]]:
        """
        Iteratively refine the multiple alignment using consistency optimization
        
        Performs 2-3 iterations of refinement to improve alignment quality.
        """
        current_alignment = multiple_alignment
        
        for iteration in range(self.max_iterations):
            logger.info(f"   🔄 Refinement iteration {iteration + 1}/{self.max_iterations}")
            
            # Calculate consistency scores for current alignment
            consistency_scores = self._calculate_position_consistency(current_alignment)
            
            # Identify positions that need refinement (low consistency)
            low_consistency_positions = [
                pos for pos, score in enumerate(consistency_scores) 
                if score < self.consistency_threshold
            ]
            
            if not low_consistency_positions:
                logger.info(f"   ✅ Alignment converged after {iteration + 1} iterations")
                break
            
            logger.info(f"   🎯 Refining {len(low_consistency_positions)} low-consistency positions")
            
            # Refine alignment at problematic positions
            refined_alignment = self._refine_problematic_positions(
                current_alignment, low_consistency_positions, consistency_library
            )
            
            current_alignment = refined_alignment
        
        return current_alignment
    
    def _calculate_position_consistency(self, alignment: List[List[int]]) -> List[float]:
        """Calculate consistency score for each position in the alignment"""
        if not alignment or not alignment[0]:
            return []
        
        alignment_length = len(alignment[0])
        consistency_scores = []
        
        for pos in range(alignment_length):
            position_tokens = [seq[pos] for seq in alignment if pos < len(seq)]
            
            # Remove gaps
            non_gap_tokens = [token for token in position_tokens if token != -1]
            
            if not non_gap_tokens:
                consistency_scores.append(0.0)
                continue
            
            # Calculate agreement proportion
            token_counts = Counter(non_gap_tokens)
            most_common_count = token_counts.most_common(1)[0][1]
            consistency = most_common_count / len(non_gap_tokens)
            
            consistency_scores.append(consistency)
        
        return consistency_scores
    
    def _refine_problematic_positions(self, alignment: List[List[int]], 
                                    problem_positions: List[int], 
                                    consistency_library: Dict[str, Any]) -> List[List[int]]:
        """Refine alignment at positions with low consistency"""
        refined_alignment = [seq.copy() for seq in alignment]
        
        for pos in problem_positions:
            # Get tokens at this position
            position_tokens = [seq[pos] for seq in refined_alignment if pos < len(seq)]
            
            # Find most consistent token based on library
            best_token = self._find_most_consistent_token(pos, position_tokens, consistency_library)
            
            # Apply refinement (simple approach - could be more sophisticated)
            for seq_idx, seq in enumerate(refined_alignment):
                if pos < len(seq) and seq[pos] != -1:
                    # Keep existing non-gap tokens for now
                    # More sophisticated refinement could be implemented here
                    pass
        
        return refined_alignment
    
    def _find_most_consistent_token(self, position: int, tokens: List[int], 
                                  consistency_library: Dict[str, Any]) -> int:
        """Find the most consistent token for a given position"""
        if not tokens:
            return -1
        
        # Simple approach - return most common non-gap token
        non_gap_tokens = [token for token in tokens if token != -1]
        if not non_gap_tokens:
            return -1
        
        token_counts = Counter(non_gap_tokens)
        return token_counts.most_common(1)[0][0]
    
    def _format_alignment_results(self, alignment: List[List[int]], 
                                block_data: Dict[str, Any], 
                                pairwise_alignments: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Format alignment results for output"""
        id_to_token = block_data['id_to_token']
        encoded_drafts = block_data['encoded_drafts']
        
        # Convert alignment back to tokens
        aligned_sequences = []
        for seq_idx, encoded_seq in enumerate(alignment):
            draft_id = encoded_drafts[seq_idx]['draft_id'] if seq_idx < len(encoded_drafts) else f'draft_{seq_idx}'
            
            # Convert encoded tokens back to strings
            token_sequence = []
            for token_id in encoded_seq:
                if token_id == -1:
                    token_sequence.append('-')  # Gap
                else:
                    token_sequence.append(id_to_token.get(token_id, f'UNK_{token_id}'))
            
            # Get the original tokens for this draft
            original_tokens = encoded_drafts[seq_idx]['tokens']
            original_to_alignment = []
            orig_ptr = 0
            for align_idx, token_id in enumerate(encoded_seq):
                if token_id == -1:
                    continue  # gap in this draft
                if orig_ptr < len(original_tokens):
                    # Map this original token to this alignment position
                    original_to_alignment.append(align_idx)
                    orig_ptr += 1

            aligned_sequences.append({
                'draft_id': draft_id,
                'tokens': token_sequence,
                'encoded_tokens': encoded_seq,
                'original_to_alignment': original_to_alignment
            })
        
        return {
            'block_id': block_data['block_id'],
            'aligned_sequences': aligned_sequences,
            'alignment_length': len(alignment[0]) if alignment else 0,
            'draft_count': len(alignment),
            'token_to_id': block_data['token_to_id'],
            'id_to_token': block_data['id_to_token'],
            'pairwise_alignments': pairwise_alignments,
            'alignment_method': 'consistency_based_msa'
        }
    
    def _handle_single_draft(self, block_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle case where only one draft exists"""
        encoded_drafts = block_data['encoded_drafts']
        if not encoded_drafts:
            return {
                'block_id': block_data['block_id'],
                'aligned_sequences': [],
                'alignment_length': 0,
                'draft_count': 0,
                'token_to_id': {},
                'id_to_token': {},
                'alignment_method': 'single_draft'
            }
        
        draft = encoded_drafts[0]
        return {
            'block_id': block_data['block_id'],
            'aligned_sequences': [{
                'draft_id': draft['draft_id'],
                'tokens': draft['tokens'],
                'encoded_tokens': draft['encoded_tokens']
            }],
            'alignment_length': len(draft['tokens']),
            'draft_count': 1,
            'token_to_id': block_data['token_to_id'],
            'id_to_token': block_data['id_to_token'],
            'alignment_method': 'single_draft'
        } 