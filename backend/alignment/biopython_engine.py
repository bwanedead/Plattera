"""
BioPython Alignment Engine
=========================

Main orchestrator for BioPython-based consistency alignment engine.
Coordinates JSON parsing, tokenization, alignment, confidence scoring, and visualization.
"""

import logging
from typing import Dict, List, Any
import time

from .alignment_utils import AlignmentError, log_alignment_statistics, encode_tokens_for_alignment
from .json_draft_tokenizer import JsonDraftTokenizer
from .consistency_aligner import ConsistencyBasedAligner
from .confidence_scorer import BioPythonConfidenceScorer

logger = logging.getLogger(__name__)

class BioPythonAlignmentEngine:
    """
    Core BioPython alignment engine.
    This class is responsible for tokenizing drafts and running the
    consistency-based Multiple Sequence Alignment (MSA). It outputs
    raw alignment data without any formatting.
    """

    def __init__(self):
        self.tokenizer = JsonDraftTokenizer()
        self.aligner = ConsistencyBasedAligner()
        self.confidence_scorer = BioPythonConfidenceScorer()
        logger.info("🧬 BioPython Alignment Engine initialized")

    def align_drafts(self, block_texts: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
        """
        Runs the core alignment workflow on raw text that has been organized by block.
        """
        start_time = time.time()
        logger.info(f"🚀 BIOPYTHON ALIGNMENT ► Starting workflow for {len(block_texts)} blocks")

        all_format_maps = {}
        processed_blocks_for_alignment = {}

        try:
            logger.info("📋 PHASE 1 ► Tokenizing, mapping, and encoding")
            for block_id, draft_texts in block_texts.items():
                all_normalized_tokens_in_block = set()
                tokenized_drafts_for_aligner = []
                block_format_maps = {}

                for draft_id, text in draft_texts.items():
                    tokenization_output = self.tokenizer.tokenize_and_map(text)
                    
                    normalized_tokens = tokenization_output["normalized_tokens"]
                    all_normalized_tokens_in_block.update(normalized_tokens)
                    tokenized_drafts_for_aligner.append({'draft_id': draft_id, 'tokens': normalized_tokens})
                    block_format_maps[draft_id] = tokenization_output["format_map"]
                
                all_format_maps[block_id] = block_format_maps
                
                # ESSENTIAL: Create the token_to_id map here, at the block level.
                unique_tokens = sorted(list(all_normalized_tokens_in_block))
                _, token_to_id, id_to_token = encode_tokens_for_alignment(unique_tokens)

                for draft in tokenized_drafts_for_aligner:
                    draft['encoded_tokens'] = [token_to_id.get(t, -1) for t in draft['tokens']]

                processed_blocks_for_alignment[block_id] = {
                    'block_id': block_id,
                    'encoded_drafts': tokenized_drafts_for_aligner,
                    'token_to_id': token_to_id,
                    'id_to_token': id_to_token,
                }
            
            logger.info("🧬 PHASE 2 ► Consistency-based multiple sequence alignment")
            alignment_results = self._align_all_blocks(processed_blocks_for_alignment)
            
            logger.info("🎯 PHASE 3 ► Confidence scoring and analysis")
            confidence_results = self.confidence_scorer.calculate_confidence_scores(alignment_results)

            processing_time = time.time() - start_time
            log_alignment_statistics(alignment_results)
            logger.info(f"✅ BIOPYTHON ALIGNMENT CORE COMPLETE ► Processed in {processing_time:.2f}s")

            return {
                'success': True,
                'format_maps': all_format_maps,
                'alignment_results': alignment_results,
                'confidence_results': confidence_results,
                'processing_time': processing_time
            }

        except Exception as e:
            logger.error(f"❌ BioPython alignment failed: {e}", exc_info=True)
            return {'success': False, 'error': str(e)}

    def _align_all_blocks(self, tokenized_data: Dict[str, Any]) -> Dict[str, Any]:
        """Performs alignment on all blocks from the tokenized data."""
        aligned_blocks = {}
        for block_id, block_data in tokenized_data.items():
            logger.info(f"   🧩 Aligning block '{block_id}'")
            try:
                # The aligner returns the raw alignment of token IDs
                aligned_block = self.aligner.align_multiple_sequences(block_data)
                aligned_blocks[block_id] = aligned_block
            except Exception as e:
                logger.error(f"❌ Failed to align block '{block_id}': {e}", exc_info=True)
                # On failure, we create a fallback result to avoid a crash
                aligned_blocks[block_id] = self._create_fallback_alignment(block_data)

        return {'blocks': aligned_blocks}

    def _create_fallback_alignment(self, block_data: Dict[str, Any]) -> Dict[str, Any]:
        """Creates a simple, unaligned result for a block that failed alignment."""
        logger.warning(f"Creating fallback alignment for block '{block_data.get('block_id', 'unknown')}'")
        aligned_sequences = []
        for draft_data in block_data.get('encoded_drafts', []):
            tokens = draft_data.get('tokens', [])
            aligned_sequences.append({
                'draft_id': draft_data.get('draft_id', 'unknown'),
                'tokens': tokens,
                'alignment_to_original_map': {i: i for i in range(len(tokens))}
            })
        return {
            'block_id': block_data.get('block_id', 'unknown'),
            'aligned_sequences': aligned_sequences,
            'alignment_method': 'fallback_unaligned'
        } 