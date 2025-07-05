"""
BioPython Confidence Scoring Module
==================================

Calculates confidence scores based on draft agreement in BioPython alignments.
Provides detailed analysis for heatmap visualization and difference detection.
"""

import logging
from typing import List, Dict, Any, Tuple
from collections import Counter
import numpy as np

logger = logging.getLogger(__name__)


class BioPythonConfidenceScorer:
    """Calculates confidence scores from BioPython alignment results"""
    
    def __init__(self):
        # Confidence thresholds for classification
        self.high_confidence_threshold = 0.8
        self.medium_confidence_threshold = 0.4
    
    def calculate_confidence_scores(self, aligned_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate confidence scores for all blocks
        
        Args:
            aligned_results: BioPython alignment results
            
        Returns:
            Dict with confidence scores and analysis
        """
        logger.info("🎯 CONFIDENCE SCORING ► Starting confidence calculation")
        
        block_confidences = {}
        overall_stats = {
            'total_positions': 0,
            'high_confidence_positions': 0,
            'medium_confidence_positions': 0, 
            'low_confidence_positions': 0,
            'average_confidence': 0.0,
            'total_differences': 0
        }
        
        for block_id, block_data in aligned_results['blocks'].items():
            logger.info(f"   📊 Analyzing confidence for block '{block_id}'")
            
            confidence_data = self._calculate_block_confidence(block_data)
            block_confidences[block_id] = confidence_data
            
            # Update overall stats
            overall_stats['total_positions'] += len(confidence_data['scores'])
            overall_stats['high_confidence_positions'] += confidence_data['high_confidence_count']
            overall_stats['medium_confidence_positions'] += confidence_data['medium_confidence_count']
            overall_stats['low_confidence_positions'] += confidence_data['low_confidence_count']
            overall_stats['total_differences'] += confidence_data['difference_count']
        
        # Calculate overall average
        if overall_stats['total_positions'] > 0:
            all_scores = []
            for block_data in block_confidences.values():
                all_scores.extend(block_data['scores'])
            overall_stats['average_confidence'] = np.mean(all_scores)
        
        logger.info(f"✅ CONFIDENCE COMPLETE ► Average confidence: {overall_stats['average_confidence']:.3f}")
        
        return {
            'block_confidences': block_confidences,
            'overall_stats': overall_stats
        }
    
    def _calculate_block_confidence(self, block_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate confidence scores for a single block
        
        Args:
            block_data: Single block alignment data
            
        Returns:
            Dict with confidence scores and statistics
        """
        aligned_sequences = block_data.get('aligned_sequences', [])
        
        if not aligned_sequences:
            return self._empty_confidence_result()
        
        # Get alignment length and draft count
        alignment_length = len(aligned_sequences[0]['tokens']) if aligned_sequences else 0
        draft_count = len(aligned_sequences)
        
        if alignment_length == 0:
            return self._empty_confidence_result()
        
        scores = []
        confidence_levels = []
        token_agreements = []
        differences = []
        
        # Calculate confidence for each position
        for pos in range(alignment_length):
            position_tokens = []
            
            # Get token at this position from each draft
            for seq in aligned_sequences:
                if pos < len(seq['tokens']):
                    token = seq['tokens'][pos]
                    position_tokens.append(token)
                else:
                    position_tokens.append('-')  # Gap if sequence is shorter
            
            # Calculate agreement for this position
            confidence, level, agreement_info = self._calculate_position_confidence(
                position_tokens, pos, aligned_sequences
            )
            
            scores.append(confidence)
            confidence_levels.append(level)
            token_agreements.append(agreement_info)
            
            # Check if this position represents a difference
            if self._is_difference_position(agreement_info):
                differences.append({
                    'position': pos,
                    'tokens': position_tokens,
                    'confidence': confidence,
                    'agreement_info': agreement_info
                })
        
        # Count confidence levels
        high_count = sum(1 for level in confidence_levels if level == 'high')
        medium_count = sum(1 for level in confidence_levels if level == 'medium')
        low_count = sum(1 for level in confidence_levels if level == 'low')
        
        return {
            'scores': scores,
            'confidence_levels': confidence_levels,
            'token_agreements': token_agreements,
            'differences': differences,
            'high_confidence_count': high_count,
            'medium_confidence_count': medium_count,
            'low_confidence_count': low_count,
            'difference_count': len(differences),
            'average_confidence': np.mean(scores) if scores else 0.0,
            'alignment_length': alignment_length,
            'draft_count': draft_count
        }
    
    def _calculate_position_confidence(self, tokens: List[str], position: int, 
                                     aligned_sequences: List[Dict[str, Any]]) -> Tuple[float, str, Dict[str, Any]]:
        """
        Calculate confidence for a single alignment position
        
        Args:
            tokens: List of tokens at this position from all drafts
            position: Position index in alignment
            aligned_sequences: All aligned sequences for context
            
        Returns:
            Tuple of (confidence_score, confidence_level, agreement_info)
        """
        # Remove gaps for confidence calculation
        non_gap_tokens = [token for token in tokens if token != '-']
        
        if not non_gap_tokens:
            # All gaps - this could be valid if all drafts have gaps here
            return 0.0, 'low', {
                'type': 'all_gaps',
                'tokens': tokens,
                'position': position,
                'analysis': 'All drafts have gaps at this position'
            }
        
        # Count token frequencies
        token_counts = Counter(non_gap_tokens)
        total_drafts = len(tokens)
        
        if len(token_counts) == 1 and len(non_gap_tokens) == total_drafts:
            # Perfect agreement among all drafts (no gaps)
            confidence = 1.0
            level = 'high'
            analysis = 'Perfect agreement among all drafts'
        else:
            # Some disagreement or gaps are present
            if not token_counts: # This happens if all tokens are gaps
                 most_common_count = 0
            else:
                most_common_token, most_common_count = token_counts.most_common(1)[0]
            
            confidence = most_common_count / total_drafts # Divide by total drafts
            
            if confidence >= self.high_confidence_threshold:
                level = 'high'
                analysis = f'Strong majority agreement ({most_common_count}/{total_drafts})'
            elif confidence >= self.medium_confidence_threshold:
                level = 'medium'
                analysis = f'Partial agreement ({most_common_count}/{total_drafts})'
            else:
                level = 'low'
                analysis = f'Low agreement or gaps present ({most_common_count}/{total_drafts})'
        
        # Create detailed agreement info
        agreement_info = {
            'type': 'token_agreement',
            'tokens': tokens,
            'position': position,
            'non_gap_tokens': non_gap_tokens,
            'total_drafts': len(tokens),
            'total_non_gap': len(non_gap_tokens),
            'unique_tokens': len(token_counts),
            'token_counts': dict(token_counts),
            'most_common_token': token_counts.most_common(1)[0][0] if token_counts else None,
            'most_common_count': token_counts.most_common(1)[0][1] if token_counts else 0,
            'analysis': analysis
        }
        
        return confidence, level, agreement_info
    
    def _is_difference_position(self, agreement_info: Dict[str, Any]) -> bool:
        """
        Check if a position represents a significant difference.
        A difference occurs if there is more than one unique token OR if there is a
        mix of tokens and gaps.
        """
        if agreement_info.get('type') == 'all_gaps':
            return False  # All gaps is not a difference, it's agreement.

        # A difference exists if there are multiple unique tokens
        has_multiple_tokens = agreement_info.get('unique_tokens', 0) > 1
        
        # Or if there's a mix of gaps and tokens
        is_mixed_gaps_and_tokens = (
            agreement_info.get('total_non_gap', 0) > 0 and 
            agreement_info.get('total_non_gap', 0) < agreement_info.get('total_drafts', 0)
        )
        
        return has_multiple_tokens or is_mixed_gaps_and_tokens
    
    def _empty_confidence_result(self) -> Dict[str, Any]:
        """Return empty confidence result for blocks with no data"""
        return {
            'scores': [],
            'confidence_levels': [],
            'token_agreements': [],
            'differences': [],
            'high_confidence_count': 0,
            'medium_confidence_count': 0,
            'low_confidence_count': 0,
            'difference_count': 0,
            'average_confidence': 0.0,
            'alignment_length': 0,
            'draft_count': 0
        }
    
    def detect_differences(self, confidence_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Detect and categorize differences across all blocks
        
        Args:
            confidence_results: Results from calculate_confidence_scores
            
        Returns:
            Dict with detailed difference analysis
        """
        logger.info("🔍 DIFFERENCE DETECTION ► Analyzing differences across blocks")
        
        all_differences = []
        difference_categories = {
            'coordinate_differences': [],
            'word_differences': [],
            'punctuation_differences': [],
            'other_differences': []
        }
        
        for block_id, block_confidence in confidence_results['block_confidences'].items():
            for diff in block_confidence['differences']:
                diff_with_block = {
                    'block_id': block_id,
                    **diff
                }
                all_differences.append(diff_with_block)
                
                # Categorize difference
                category = self._categorize_difference(diff)
                difference_categories[category].append(diff_with_block)
        
        # Create reference vs alternatives format
        formatted_differences = self._format_differences_for_suggestions(all_differences)
        
        logger.info(f"   📊 Found {len(all_differences)} total differences across all blocks")
        
        return {
            'all_differences': all_differences,
            'difference_categories': difference_categories,
            'formatted_differences': formatted_differences,
            'total_differences': len(all_differences),
            'category_counts': {cat: len(diffs) for cat, diffs in difference_categories.items()}
        }
    
    def _categorize_difference(self, difference: Dict[str, Any]) -> str:
        """Categorize a difference by type"""
        tokens = difference.get('tokens', [])
        non_gap_tokens = [t for t in tokens if t != '-']
        
        if not non_gap_tokens:
            return 'other_differences'
        
        # Check for coordinate patterns
        coordinate_patterns = [r'[NS]', r'\d+°', r'[EW]', r'\.']
        for token in non_gap_tokens:
            for pattern in coordinate_patterns:
                if pattern in token:
                    return 'coordinate_differences'
        
        # Check for punctuation
        if all(len(token) == 1 and not token.isalnum() for token in non_gap_tokens):
            return 'punctuation_differences'
        
        # Check for words
        if all(token.isalpha() for token in non_gap_tokens):
            return 'word_differences'
        
        return 'other_differences'
    
    def _format_differences_for_suggestions(self, differences: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Format differences for suggestion panel (reference vs alternatives)
        
        Args:
            differences: List of difference dictionaries
            
        Returns:
            List of formatted differences with reference and alternatives
        """
        formatted = []
        
        for diff in differences:
            tokens = diff.get('tokens', [])
            if not tokens:
                continue
            
            # Use first draft as reference (index 0)
            reference_token = tokens[0] if len(tokens) > 0 else '-'
            
            # Get alternatives from other drafts
            alternatives = []
            for i, token in enumerate(tokens[1:], 1):  # Start from draft 1 (index 1)
                if token != reference_token:  # Only include different tokens
                    alternatives.append({
                        'draft_index': i,
                        'draft_id': f'Draft_{i+1}',  # Assuming draft naming convention
                        'token': token
                    })
            
            # Only include if there are actual alternatives
            if alternatives:
                formatted.append({
                    'block_id': diff['block_id'],
                    'position': diff['position'],
                    'reference_token': reference_token,
                    'reference_draft': 'Draft_1',
                    'alternatives': alternatives,
                    'confidence': diff['confidence']
                })
        
        return formatted
    
    def generate_confidence_heatmap_data(self, confidence_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate data structure for confidence heatmap visualization
        
        Args:
            confidence_results: Results from calculate_confidence_scores
            
        Returns:
            Dict with heatmap visualization data
        """
        logger.info("🔥 HEATMAP GENERATION ► Preparing confidence heatmap data")
        
        heatmap_data = {}
        
        for block_id, block_confidence in confidence_results['block_confidences'].items():
            scores = block_confidence['scores']
            
            if not scores:
                continue
            
            # Create heatmap matrix
            # For now, create a single row with confidence scores
            # Could be extended to show per-draft confidence
            heatmap_matrix = [scores]  # Single row with confidence scores
            
            heatmap_data[block_id] = {
                'matrix': heatmap_matrix,
                'row_labels': ['Consensus Confidence'],
                'column_count': len(scores),
                'min_confidence': min(scores),
                'max_confidence': max(scores),
                'average_confidence': block_confidence['average_confidence'],
                'high_confidence_positions': block_confidence['high_confidence_count'],
                'medium_confidence_positions': block_confidence['medium_confidence_count'],
                'low_confidence_positions': block_confidence['low_confidence_count']
            }
        
        logger.info(f"   📊 Generated heatmap data for {len(heatmap_data)} blocks")
        
        return {
            'blocks': heatmap_data,
            'overall_stats': confidence_results['overall_stats']
        }
    
    def get_confidence_summary(self, confidence_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get a summary of confidence analysis results
        
        Args:
            confidence_results: Results from calculate_confidence_scores
            
        Returns:
            Dict with summary statistics
        """
        overall_stats = confidence_results['overall_stats']
        
        total_positions = overall_stats['total_positions']
        if total_positions == 0:
            return {
                'message': 'No alignment data available for confidence analysis'
            }
        
        high_pct = (overall_stats['high_confidence_positions'] / total_positions) * 100
        medium_pct = (overall_stats['medium_confidence_positions'] / total_positions) * 100
        low_pct = (overall_stats['low_confidence_positions'] / total_positions) * 100
        
        return {
            'total_positions': total_positions,
            'total_differences': overall_stats['total_differences'],
            'average_confidence': overall_stats['average_confidence'],
            'confidence_distribution': {
                'high_confidence': {
                    'count': overall_stats['high_confidence_positions'],
                    'percentage': high_pct
                },
                'medium_confidence': {
                    'count': overall_stats['medium_confidence_positions'], 
                    'percentage': medium_pct
                },
                'low_confidence': {
                    'count': overall_stats['low_confidence_positions'],
                    'percentage': low_pct
                }
            },
            'quality_assessment': self._assess_alignment_quality(overall_stats),
            'block_count': len(confidence_results['block_confidences'])
        }
    
    def _assess_alignment_quality(self, overall_stats: Dict[str, Any]) -> str:
        """Assess overall alignment quality based on confidence distribution"""
        total_positions = overall_stats['total_positions']
        if total_positions == 0:
            return 'No data'
        
        high_pct = (overall_stats['high_confidence_positions'] / total_positions) * 100
        avg_confidence = overall_stats['average_confidence']
        
        if avg_confidence >= 0.9 and high_pct >= 80:
            return 'Excellent - Very high agreement across drafts'
        elif avg_confidence >= 0.8 and high_pct >= 70:
            return 'Very Good - Strong agreement with minor differences'
        elif avg_confidence >= 0.7 and high_pct >= 60:
            return 'Good - Generally consistent with some variations'
        elif avg_confidence >= 0.6:
            return 'Fair - Moderate agreement, review differences carefully'
        else:
            return 'Poor - Significant disagreements, manual review required' 