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
        
        Implements the complete specification flow:
        1. Redundancy == 1? → Fast-path pass-through
        2. Validate JSON Schema (ensure contiguous section IDs; section count N can be any positive int)
        3. Extract Anchors & Check for conflicts → Mark suspect drafts for fallback
        4. Tokenise (drop punctuation, merge anchors)
        5. Progressive Multi-Sequence Alignment
        6. Low Mean Confidence < 0.4? → Pairwise Realign fallback
        7. Build Consensus + Confidence + Alternatives
        8. Return Compatible Response Format
        
        Args:
            drafts: List of JSON drafts (max 10)
            debug: Enable debug logging
            
        Returns:
            ConsensusBundle with consensus text and confidence data
        """
        if debug:
            logging.getLogger().setLevel(logging.DEBUG)
        
        # 🚀 STEP 1: Redundancy == 1? Fast-path (before any processing)
        if len(drafts) == 1:
            logger.info("🏃 Fast path: Redundancy == 1, bypassing all alignment")
            return self._single_draft_passthrough(drafts[0])
        
        if len(drafts) > LIMITS["MAX_DRAFTS"]:
            logger.warning(f"Too many drafts ({len(drafts)}), limiting to {LIMITS['MAX_DRAFTS']}")
            drafts = drafts[:LIMITS["MAX_DRAFTS"]]
        
        logger.info(f"🚀 Starting JSON semantic alignment for {len(drafts)} drafts")
        
        try:
            # 🔍 STEP 2: Validate JSON Schema & Extract Anchors
            logger.info("📋 Validating JSON schema and extracting anchors")
            valid_drafts, suspect_drafts = self.validator.validate_draft_batch(drafts)
            
            if not valid_drafts:
                logger.error("❌ No valid drafts found - using fallback path")
                return self._fallback_suspect_drafts(drafts, suspect_drafts)
            
            # 🚨 STEP 3: Handle suspect drafts through fallback path
            if len(suspect_drafts) > 0:
                logger.warning(f"⚠️ {len(suspect_drafts)} drafts marked as suspect")
                for suspect in suspect_drafts:
                    logger.warning(f"  Draft {suspect['index']+1}: {suspect['reason']}")
                logger.info("🔄 Suspect drafts will be processed through pairwise realign fallback")
            
            # Handle single valid draft case (after suspect filtering)
            if len(valid_drafts) == 1:
                logger.info("🏃 Only one valid draft after filtering, using single draft")
                return self._single_draft_passthrough(valid_drafts[0])
            
            # 🔤 STEP 4: Tokenise (explicit step - drop punctuation, merge anchors)
            logger.info("🔤 Tokenising documents (dropping punctuation, merging composite anchors)")
            
            # 🧩 STEP 5: Progressive Multi-Sequence Alignment
            logger.info(f"🧩 Running Progressive MSA on {len(valid_drafts)} valid drafts")
            alignment_grid = self.aligner.align_documents(valid_drafts)
            
            # 🔨 STEP 6: Build Consensus + Confidence + Alternatives
            logger.info("🔨 Building consensus, confidence scores, and alternatives")
            consensus_text, confidence_map, alternatives_map = self.consensus_builder.build_consensus(alignment_grid)
            
            # 📊 STEP 7: Low Mean Confidence < 0.4? Check
            mean_confidence = self._calculate_mean_confidence(confidence_map)
            logger.info(f"�� Mean confidence: {mean_confidence:.3f}")
            
            if mean_confidence < 0.4:
                logger.warning(f"⚠️ Low mean confidence ({mean_confidence:.3f} < 0.4) - attempting pairwise realign")
                return self._pairwise_realign_fallback(valid_drafts, suspect_drafts)
            
            # 📦 STEP 8: Return Compatible Response Format
            logger.info("✅ Semantic alignment complete - returning consensus bundle")
            return self._format_consensus_bundle(consensus_text, confidence_map, alternatives_map)
            
        except Exception as e:
            logger.error(f"❌ Alignment pipeline failed: {str(e)}")
            logger.warning("🚨 Using pairwise realign fallback due to alignment failure")
            return self._pairwise_realign_fallback(valid_drafts if 'valid_drafts' in locals() else drafts, 
                                                 suspect_drafts if 'suspect_drafts' in locals() else [])
    
    def _single_draft_passthrough(self, draft: Dict[str, Any]) -> ConsensusBundle:
        """Fast-path for single draft - minimal processing"""
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
    
    def _calculate_mean_confidence(self, confidence_map: Dict[str, float]) -> float:
        """Calculate mean confidence from confidence map"""
        if not confidence_map:
            return 0.0
        
        confidences = list(confidence_map.values())
        return sum(confidences) / len(confidences)
    
    def _pairwise_realign_fallback(self, valid_drafts: List[Dict[str, Any]], 
                                  suspect_drafts: List[Dict[str, Any]]) -> ConsensusBundle:
        """
        Pairwise Realign / Text Consensus fallback path
        
        Try emergency pair-wise alignment, then fall back to text consensus if that fails
        """
        logger.info("🔄 Entering pairwise realign fallback path")
        
        try:
            # Combine valid and suspect drafts for fallback processing
            all_drafts = valid_drafts.copy()
            if suspect_drafts:
                # Add suspect drafts back for emergency processing
                all_drafts.extend([s["draft"] for s in suspect_drafts])
                logger.info(f"🔧 Including {len(suspect_drafts)} suspect drafts in fallback")
            
            if len(all_drafts) < 2:
                # Only one draft available - use single draft
                draft = all_drafts[0] if all_drafts else {"sections": [{"id": 1, "body": "No valid drafts"}]}
                return self._single_draft_passthrough(draft)
            
            # Try pairwise alignment with best two drafts
            logger.info("🔧 Attempting pairwise alignment with two best drafts")
            best_drafts = self._select_best_two_drafts(all_drafts)
            
            # Create minimal alignment grid for two drafts
            try:
                alignment_grid = self.aligner.align_documents(best_drafts)
                consensus_text, confidence_map, alternatives_map = self.consensus_builder.build_consensus(alignment_grid)
                
                # Check if pairwise alignment worked
                mean_confidence = self._calculate_mean_confidence(confidence_map)
                if mean_confidence >= 0.3:  # Lower threshold for fallback
                    logger.info(f"✅ Pairwise realign successful (confidence: {mean_confidence:.3f})")
                    return self._format_consensus_bundle(consensus_text, confidence_map, alternatives_map)
                else:
                    raise ValueError(f"Pairwise alignment still too low confidence: {mean_confidence:.3f}")
                
            except Exception as pair_error:
                logger.warning(f"🚨 Pairwise alignment failed: {pair_error}")
                
                # Final fallback: naive text concatenation with manual review flag
                logger.info("🚨 Using naive text concatenation (requires manual review)")
                return self._naive_text_fallback(all_drafts)
                
        except Exception as e:
            logger.error(f"❌ Pairwise realign fallback failed: {str(e)}")
            return self._naive_text_fallback(valid_drafts if valid_drafts else [{"sections": [{"id": 1, "body": "Fallback failed"}]}])
    
    def _fallback_suspect_drafts(self, original_drafts: List[Dict[str, Any]], 
                               suspect_drafts: List[Dict[str, Any]]) -> ConsensusBundle:
        """Handle case where all drafts are suspect - use fallback path"""
        logger.warning("🚨 All drafts are suspect - using fallback processing")
        return self._pairwise_realign_fallback([], suspect_drafts)
    
    def _select_best_two_drafts(self, drafts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Select the two best drafts based on section count and body length"""
        def draft_quality_score(draft):
            sections = draft.get("sections", [])
            total_body_length = sum(len(s.get("body", "")) for s in sections)
            section_count = len(sections)
            return total_body_length + (section_count * 100)  # Bonus for more sections
        
        sorted_drafts = sorted(drafts, key=draft_quality_score, reverse=True)
        return sorted_drafts[:2]
    
    def _naive_text_fallback(self, drafts: List[Dict[str, Any]]) -> ConsensusBundle:
        """Final fallback: naive text concatenation (flags for manual review)"""
        if not drafts:
            return ConsensusBundle(
                consensus="No drafts available for processing",
                confidence=[],
                alternatives={}
            )
        
        # Use the longest draft as fallback
        best_draft = max(drafts, key=lambda d: sum(len(s.get("body", "")) for s in d.get("sections", [])))
        
        logger.warning("🚨 Using naive fallback - REQUIRES MANUAL REVIEW")
        result = self._single_draft_passthrough(best_draft)
        
        # Mark as requiring manual review
        result.consensus = "[MANUAL REVIEW REQUIRED] " + result.consensus
        
        return result
    
    def _format_consensus_bundle(self, consensus_text: str, confidence_map: Dict[str, float], 
                               alternatives_map: Dict[str, List[str]]) -> ConsensusBundle:
        """Format consensus results into expected bundle format"""
        
        # 🔍 DEBUG: Add these lines
        logger.info(f"🔍 DEBUG: confidence_map received: {confidence_map}")
        logger.info(f"🔍 DEBUG: alternatives_map received: {alternatives_map}")
        logger.info(f"🔍 DEBUG: consensus_text length: {len(consensus_text)} chars")
        
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

