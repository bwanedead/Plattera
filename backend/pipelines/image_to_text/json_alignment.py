"""
JSON Document Alignment System
=============================

Main API for aligning JSON-segmented deed drafts.
Implements the specification for semantic alignment with confidence scoring.
"""

import json
import logging
from typing import List, Dict, Any, Optional, Tuple

from .validate import DraftValidator, SchemaError
from .align import DocumentAligner
from .consensus import ConsensusBuilder
from .alignment_config import LIMITS

logger = logging.getLogger(__name__)

class ConsensusBundle:
    """Container for consensus results"""
    
    def __init__(self, consensus: str, confidence: List[float], alternatives: Dict[int, List[str]], 
                 provenance: Optional[Dict[int, List[int]]] = None):
        self.consensus = consensus
        self.confidence = confidence
        self.alternatives = alternatives
        self.provenance = provenance
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response"""
        return {
            "consensus": self.consensus,
            "confidence": self.confidence,
            "alternatives": self.alternatives,
            "provenance": self.provenance
        }

class JsonAlignmentEngine:
    """Main engine for JSON document alignment"""
    
    def __init__(self):
        self.validator = DraftValidator()
        self.aligner = DocumentAligner()
        self.consensus_builder = ConsensusBuilder()
    
    def merge_drafts(self, drafts: List[Dict[str, Any]], debug: bool = False) -> ConsensusBundle:
        """
        Merge JSON drafts into consensus with confidence scores
        
        Args:
            drafts: List of JSON drafts (max 10)
            debug: Enable debug logging
            
        Returns:
            ConsensusBundle with consensus text and confidence data
        """
        if debug:
            logging.getLogger().setLevel(logging.DEBUG)
        
        # Handle redundancy = 1 case (fast path)
        if len(drafts) == 1:
            logger.info("🏃 Fast path: Single draft, bypassing alignment")
            return self._handle_single_draft(drafts[0])
        
        if len(drafts) > LIMITS["MAX_DRAFTS"]:
            logger.warning(f"Too many drafts ({len(drafts)}), limiting to {LIMITS['MAX_DRAFTS']}")
            drafts = drafts[:LIMITS["MAX_DRAFTS"]]
        
        logger.info(f"🚀 Starting JSON alignment for {len(drafts)} drafts")
        
        try:
            # Step 1: Validate all drafts
            valid_drafts, suspect_drafts = self.validator.validate_draft_batch(drafts)
            
            if not valid_drafts:
                raise ValueError("No valid drafts found for alignment")
            
            if len(suspect_drafts) > 0:
                logger.warning(f"⚠️ {len(suspect_drafts)} drafts marked as suspect and excluded")
                for suspect in suspect_drafts:
                    logger.warning(f"  Draft {suspect['index']+1}: {suspect['reason']}")
            
            # Handle single valid draft case
            if len(valid_drafts) == 1:
                logger.info("🏃 Only one valid draft, bypassing alignment")
                return self._handle_single_draft(valid_drafts[0])
            
            # Step 2: Align documents
            logger.info(f"🔄 Aligning {len(valid_drafts)} valid drafts")
            alignment_grid = self.aligner.align_documents(valid_drafts)
            
            # Step 3: Build consensus
            logger.info("🔨 Building consensus from alignment")
            consensus_text, confidence_map, alternatives_map = self.consensus_builder.build_consensus(alignment_grid)
            
            # Step 4: Convert to expected format
            return self._format_consensus_bundle(consensus_text, confidence_map, alternatives_map)
            
        except Exception as e:
            logger.error(f"❌ Alignment failed: {str(e)}")
            # Fallback to first valid draft or first draft
            fallback_draft = valid_drafts[0] if valid_drafts else drafts[0]
            logger.warning("🚨 Falling back to single draft due to alignment failure")
            return self._handle_single_draft(fallback_draft)
    
    def _handle_single_draft(self, draft: Dict[str, Any]) -> ConsensusBundle:
        """Handle single draft case - bypass alignment"""
        try:
            # Convert draft to text
            sections = draft.get("sections", [])
            text_parts = []
            
            for section in sections:
                header = section.get("header")
                body = section.get("body", "")
                
                if header and header.strip():
                    text_parts.append(f"{header.strip()}")
                    text_parts.append("─" * min(len(header.strip()), 50))
                
                if body and body.strip():
                    # Normalize internal whitespace but preserve structure
                    normalized_body = " ".join(body.strip().split())
                    text_parts.append(normalized_body)
                
                text_parts.append("")  # Section separator
            
            consensus_text = "\n".join(text_parts).strip()
            
            return ConsensusBundle(
                consensus=consensus_text,
                confidence=[],  # Empty for single draft
                alternatives={}  # Empty for single draft
            )
            
        except Exception as e:
            logger.error(f"❌ Single draft processing failed: {str(e)}")
            return ConsensusBundle(
                consensus="Error processing draft",
                confidence=[],
                alternatives={}
            )
    
    def _format_consensus_bundle(self, consensus_text: str, confidence_map: Dict[str, float], 
                               alternatives_map: Dict[str, List[str]]) -> ConsensusBundle:
        """Format consensus results into expected bundle format"""
        
        # Convert confidence map to list (word positions)
        confidence_list = []
        alternatives_dict = {}
        
        # Extract word positions from confidence map
        max_word_idx = -1
        for word_key in confidence_map.keys():
            if word_key.startswith("word_"):
                try:
                    word_idx = int(word_key.split("_")[1])
                    max_word_idx = max(max_word_idx, word_idx)
                except ValueError:
                    continue
        
        # Build confidence list and alternatives dict
        for i in range(max_word_idx + 1):
            word_key = f"word_{i}"
            confidence = confidence_map.get(word_key, 0.0)
            confidence_list.append(confidence)
            
            if word_key in alternatives_map and alternatives_map[word_key]:
                alternatives_dict[i] = alternatives_map[word_key]
        
        return ConsensusBundle(
            consensus=consensus_text,
            confidence=confidence_list,
            alternatives=alternatives_dict
        )

# Main function for API integration
def merge_drafts(drafts: List[Dict[str, Any]], opts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Public API function for merging JSON drafts
    
    Args:
        drafts: List of JSON draft documents
        opts: Optional configuration (debug flag, etc.)
        
    Returns:
        Dictionary with consensus bundle data
    """
    opts = opts or {}
    debug = opts.get("debug", False)
    
    engine = JsonAlignmentEngine()
    result = engine.merge_drafts(drafts, debug=debug)
    
    return result.to_dict()

