"""
Final Draft Selector
===================

Simple service for selecting the final draft output from image-to-text processing.
Handles consensus drafts, individual drafts, and edited drafts as final output.
"""

from typing import Dict, Any, Optional, Union
import logging

logger = logging.getLogger(__name__)

class FinalDraftSelector:
    """
    Service for selecting and preparing the final draft output.
    """
    
    def select_final_draft(
        self,
        redundancy_analysis: Dict[str, Any],
        alignment_result: Optional[Dict[str, Any]] = None,
        selected_draft: Union[int, str] = 'consensus',
        edited_draft_content: Optional[str] = None,
        edited_from_draft: Optional[Union[int, str]] = None
    ) -> Dict[str, Any]:
        """
        Select and prepare the final draft output.
        
        Args:
            redundancy_analysis: Results from redundancy analysis
            alignment_result: Optional alignment results (for consensus)
            selected_draft: Which draft to select ('consensus', 'best', or draft index)
            edited_draft_content: Optional edited content
            edited_from_draft: Which draft was edited (if applicable)
            
        Returns:
            Final draft selection result with metadata
        """
        logger.info(f"�� FINAL DRAFT SELECTION ► Selecting draft: {selected_draft}")
        
        # Determine the source of the final draft
        if edited_draft_content and edited_from_draft is not None:
            final_content = edited_draft_content
            selection_method = 'user_edited'
            logger.info(f"�� Using edited draft content ({len(edited_draft_content)} chars)")
        elif selected_draft == 'consensus':
            final_content = self._get_consensus_draft(alignment_result, redundancy_analysis)
            selection_method = 'consensus'
            logger.info("🎯 Using consensus draft")
        elif selected_draft == 'best':
            final_content = self._get_best_draft(redundancy_analysis)
            selection_method = 'best_draft'
            logger.info("⭐ Using best draft")
        else:
            final_content = self._get_individual_draft(selected_draft, redundancy_analysis)
            selection_method = 'individual_draft'
            logger.info(f"📄 Using individual draft {selected_draft + 1}")
        
        # Prepare final result
        final_result = {
            'final_text': final_content,
            'selection_method': selection_method,
            'selected_draft': selected_draft,
            'metadata': {
                'redundancy_analysis': redundancy_analysis,
                'alignment_available': alignment_result is not None,
                'has_edits': edited_draft_content is not None,
                'original_draft_count': len(redundancy_analysis.get('individual_results', [])),
                'consensus_available': self._has_consensus(alignment_result)
            }
        }
        
        logger.info(f"✅ FINAL DRAFT SELECTED ► Method: {selection_method}")
        return final_result
    
    def _get_consensus_draft(
        self, 
        alignment_result: Optional[Dict[str, Any]], 
        redundancy_analysis: Dict[str, Any]
    ) -> str:
        """Get consensus draft from alignment results or redundancy analysis"""
        if alignment_result and alignment_result.get('success'):
            # Try to get consensus from alignment results
            consensus_text = alignment_result.get('consensus_text')
            if consensus_text:
                return consensus_text
        
        # Fallback to redundancy analysis consensus
        consensus_text = redundancy_analysis.get('consensus_text')
        if consensus_text:
            return consensus_text
        
        # Final fallback to best draft
        logger.warning("⚠️ No consensus available, falling back to best draft")
        return self._get_best_draft(redundancy_analysis)
    
    def _get_best_draft(self, redundancy_analysis: Dict[str, Any]) -> str:
        """Get the best draft from redundancy analysis"""
        best_text = redundancy_analysis.get('best_formatted_text')
        if best_text:
            return best_text
        
        # Fallback to first successful result
        individual_results = redundancy_analysis.get('individual_results', [])
        successful_results = [r for r in individual_results if r.get('success')]
        if successful_results:
            return successful_results[0].get('text', '')
        
        return "No valid draft available"
    
    def _get_individual_draft(self, draft_index: int, redundancy_analysis: Dict[str, Any]) -> str:
        """Get specific individual draft"""
        individual_results = redundancy_analysis.get('individual_results', [])
        if 0 <= draft_index < len(individual_results):
            result = individual_results[draft_index]
            if result.get('success'):
                return result.get('text', '')
        
        logger.warning(f"⚠️ Draft {draft_index + 1} not available, falling back to best")
        return self._get_best_draft(redundancy_analysis)
    
    def _has_consensus(self, alignment_result: Optional[Dict[str, Any]]) -> bool:
        """Check if consensus is available"""
        if not alignment_result:
            return False
        return bool(alignment_result.get('consensus_text') or 
                   alignment_result.get('alignment_results', {}).get('blocks')) 