"""
BioPython Alignment Engine
=========================

Main orchestrator for BioPython-based consistency alignment engine.
Coordinates JSON parsing, tokenization, alignment, confidence scoring, and visualization.
"""

import logging
from typing import Dict, List, Any
import time

from .alignment_utils import AlignmentError, log_alignment_statistics
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

    def align_drafts(self, draft_jsons: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Runs the core alignment workflow.

        Args:
            draft_jsons: A list of draft dictionaries.

        Returns:
            A dictionary containing the raw alignment results and the
            tokenization data needed for format reconstruction.
        """
        start_time = time.time()
        logger.info(f"🚀 BIOPYTHON ALIGNMENT ► Starting core workflow for {len(draft_jsons)} drafts")

        try:
            # Phase 1: JSON Parsing and Tokenization
            logger.info("📋 PHASE 1 ► JSON parsing and tokenization")
            tokenized_data = self.tokenizer.process_json_drafts(draft_jsons)

            # Phase 2: Consistency-Based Alignment
            logger.info("🧬 PHASE 2 ► Consistency-based multiple sequence alignment")
            alignment_results = self._align_all_blocks(tokenized_data)
            
            # Phase 3: Confidence Scoring (still useful for analysis)
            logger.info("🎯 PHASE 3 ► Confidence scoring and analysis")
            confidence_results = self.confidence_scorer.calculate_confidence_scores(alignment_results)

            processing_time = time.time() - start_time
            log_alignment_statistics(alignment_results)
            logger.info(f"✅ BIOPYTHON ALIGNMENT CORE COMPLETE ► Processed in {processing_time:.2f}s")

            return {
                'success': True,
                'tokenized_data': tokenized_data,
                'alignment_results': alignment_results,
                'confidence_results': confidence_results,
                'processing_time': processing_time
            }

        except Exception as e:
            logger.error(f"❌ BioPython alignment failed: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'processing_time': time.time() - start_time
            }

    def _align_all_blocks(self, tokenized_data: Dict[str, Any]) -> Dict[str, Any]:
        """Performs alignment on all blocks from the tokenized data."""
        aligned_blocks = {}
        for block_id, block_data in tokenized_data['blocks'].items():
            logger.info(f"   🧩 Aligning block '{block_id}'")
            try:
                # The aligner returns the raw alignment of token IDs
                aligned_block = self.aligner.align_multiple_sequences(block_data)
                aligned_blocks[block_id] = aligned_block
            except Exception as e:
                logger.error(f"❌ Failed to align block '{block_id}': {e}", exc_info=True)
                # On failure, we create a fallback result to avoid a crash
                aligned_blocks[block_id] = self._create_fallback_alignment(block_data)

        return {
            'blocks': aligned_blocks,
            'total_blocks': len(aligned_blocks),
            'draft_count': tokenized_data.get('draft_count', 0)
        }

    def _create_fallback_alignment(self, block_data: Dict[str, Any]) -> Dict[str, Any]:
        """Creates a simple, unaligned result for a block that failed alignment."""
        logger.warning(f"Creating fallback alignment for block '{block_data.get('block_id', 'unknown')}'")
        aligned_sequences = []
        for draft_data in block_data.get('encoded_drafts', []):
            aligned_sequences.append({
                'draft_id': draft_data.get('draft_id', 'unknown'),
                'tokens': draft_data.get('tokens', []),
                'alignment_to_original_map': {i: i for i in range(len(draft_data.get('tokens', [])))}
            })
        return {
            'block_id': block_data.get('block_id', 'unknown'),
            'aligned_sequences': aligned_sequences,
            'alignment_method': 'fallback_unaligned'
        } 