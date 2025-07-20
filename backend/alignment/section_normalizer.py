"""
Section Count Normalizer
========================

Handles the post-processing normalization of drafts when they have different section counts.
Uses n-gram matching and section size intelligence to split under-sectioned drafts.
"""

import logging
import json
import re
from typing import List, Dict, Any, Tuple, Optional
from collections import defaultdict
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

class SectionNormalizer:
    """
    Normalizes section counts across redundant drafts by intelligently splitting 
    under-sectioned drafts to match the most granular draft.
    """
    
    def __init__(self, ngram_size: int = 3, similarity_threshold: float = 0.6):
        self.ngram_size = ngram_size
        self.similarity_threshold = similarity_threshold
    
    def normalize_draft_sections(self, draft_jsons: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Main entry point: normalize section counts across all drafts.
        
        Args:
            draft_jsons: List of draft dictionaries from alignment processing
            
        Returns:
            List of normalized draft dictionaries with consistent section counts
        """
        logger.info(f"🔧 SECTION NORMALIZER ► Processing {len(draft_jsons)} drafts for section consistency")
        
        # Extract section data from each draft
        draft_sections = []
        for i, draft_json in enumerate(draft_jsons):
            sections = self._extract_sections_from_draft(draft_json, f"Draft_{i+1}")
            draft_sections.append(sections)
            logger.info(f"   📋 Draft {i+1}: {len(sections)} sections")
        
        # Check if normalization is needed
        section_counts = [len(sections) for sections in draft_sections]
        if len(set(section_counts)) <= 1:
            logger.info(f"   ✅ All drafts have the same section count ({section_counts[0]}), no normalization needed")
            return draft_jsons
        
        # Find the draft with the most sections (our target)
        max_sections = max(section_counts)
        target_draft_idx = section_counts.index(max_sections)
        target_sections = draft_sections[target_draft_idx]
        
        logger.info(f"🎯 TARGET DRAFT ► Draft {target_draft_idx + 1} with {max_sections} sections will be the sectioning template")
        
        # Normalize all other drafts to match the target
        normalized_drafts = []
        for i, (draft_json, sections) in enumerate(zip(draft_jsons, draft_sections)):
            if len(sections) == max_sections:
                # Already has correct section count
                logger.info(f"   ✅ Draft {i+1}: Already has {max_sections} sections, no changes needed")
                normalized_drafts.append(draft_json)
            else:
                # Need to normalize this draft
                logger.info(f"   🔄 Draft {i+1}: Normalizing {len(sections)} sections → {max_sections} sections")
                normalized_draft = self._normalize_single_draft(draft_json, sections, target_sections, f"Draft_{i+1}")
                normalized_drafts.append(normalized_draft)
        
        logger.info(f"✅ NORMALIZATION COMPLETE ► All drafts now have {max_sections} sections")
        return normalized_drafts
    
    def _extract_sections_from_draft(self, draft_json: Dict[str, Any], draft_id: str) -> List[Dict[str, Any]]:
        """Extract section data from a draft JSON."""
        try:
            # Handle the case where the JSON is in the first block's text
            if 'blocks' in draft_json and draft_json['blocks']:
                first_block_text = draft_json['blocks'][0].get('text', '')
                try:
                    document_data = json.loads(first_block_text)
                    return document_data.get('sections', [])
                except json.JSONDecodeError:
                    logger.warning(f"Draft {draft_id}: Could not parse JSON, assuming pre-parsed sections")
                    return []
            
            # Handle pre-parsed sections
            if 'sections' in draft_json:
                return draft_json['sections']
            
            logger.error(f"Draft {draft_id}: No recognizable section format found")
            return []
            
        except Exception as e:
            logger.error(f"Draft {draft_id}: Error extracting sections: {e}")
            return []
    
    def _normalize_single_draft(self, draft_json: Dict[str, Any], current_sections: List[Dict], 
                               target_sections: List[Dict], draft_id: str) -> Dict[str, Any]:
        """
        Normalize a single draft to match the target section count.
        
        Strategy:
        1. Find section mapping between current and target
        2. Split under-sectioned content using n-gram boundary detection
        3. Reconstruct draft with normalized sections
        """
        logger.info(f"🔍 NORMALIZING {draft_id} ► {len(current_sections)} → {len(target_sections)} sections")
        
        # Create mapping between current and target sections
        section_mapping = self._create_section_mapping(current_sections, target_sections)
        
        # Split sections that need to be divided
        normalized_sections = self._split_sections_using_mapping(current_sections, target_sections, section_mapping)
        
        # Reconstruct the draft JSON
        return self._reconstruct_draft_json(draft_json, normalized_sections)
    
    def _create_section_mapping(self, current_sections: List[Dict], target_sections: List[Dict]) -> List[Tuple[int, List[int]]]:
        """
        Create mapping showing which current sections should map to which target sections.
        
        Returns:
            List of tuples: (current_section_index, [target_section_indices])
        """
        mapping = []
        current_text_lengths = [len(self._get_section_text(section)) for section in current_sections]
        target_text_lengths = [len(self._get_section_text(section)) for section in target_sections]
        
        logger.info(f"   📏 Current section lengths: {current_text_lengths}")
        logger.info(f"   📏 Target section lengths: {target_text_lengths}")
        
        # Simple heuristic: map based on cumulative text length
        current_idx = 0
        current_cumulative = 0
        target_cumulative = 0
        target_indices = []
        
        for target_idx, target_len in enumerate(target_text_lengths):
            target_cumulative += target_len
            target_indices.append(target_idx)
            
            # Check if we should close this current section
            if current_idx < len(current_sections):
                current_len = current_text_lengths[current_idx]
                current_potential_cumulative = current_cumulative + current_len
                
                # If adding this current section would exceed target cumulative by too much,
                # or if we're at the end, finalize the mapping
                ratio = target_cumulative / current_potential_cumulative if current_potential_cumulative > 0 else 1.0
                
                if (ratio >= 0.7 and ratio <= 1.3) or target_idx == len(target_sections) - 1:
                    # Good match, finalize this mapping
                    mapping.append((current_idx, target_indices.copy()))
                    logger.info(f"   🎯 Mapping: Current section {current_idx} → Target sections {target_indices}")
                    
                    current_idx += 1
                    current_cumulative += current_len
                    target_indices = []
        
        return mapping
    
    def _split_sections_using_mapping(self, current_sections: List[Dict], target_sections: List[Dict], 
                                    mapping: List[Tuple[int, List[int]]]) -> List[Dict]:
        """
        Split current sections based on mapping using n-gram boundary detection.
        """
        normalized_sections = []
        
        for current_idx, target_indices in mapping:
            if len(target_indices) == 1:
                # 1:1 mapping, no split needed
                normalized_sections.append(current_sections[current_idx])
                logger.info(f"   ✅ Section {current_idx}: No split needed (1:1 mapping)")
            else:
                # 1:many mapping, need to split
                logger.info(f"   🔪 Section {current_idx}: Splitting into {len(target_indices)} parts")
                split_sections = self._split_single_section(
                    current_sections[current_idx], 
                    [target_sections[i] for i in target_indices],
                    target_indices
                )
                normalized_sections.extend(split_sections)
        
        return normalized_sections
    
    def _split_single_section(self, current_section: Dict, target_sections: List[Dict], 
                            target_indices: List[int]) -> List[Dict]:
        """
        Split a single section into multiple sections using n-gram boundary detection.
        """
        current_text = self._get_section_text(current_section)
        target_texts = [self._get_section_text(section) for section in target_sections]
        
        logger.info(f"      📝 Splitting text: {len(current_text)} chars → {len(target_texts)} parts")
        
        # Find split points using n-gram matching
        split_points = self._find_split_points_with_ngrams(current_text, target_texts)
        
        # Create new sections based on split points
        split_sections = []
        start_pos = 0
        
        for i, (end_pos, target_idx) in enumerate(zip(split_points + [len(current_text)], target_indices)):
            section_text = current_text[start_pos:end_pos].strip()
            
            if section_text:
                new_section = {
                    "id": target_idx + 1,  # 1-based indexing
                    "body": section_text
                }
                
                # Try to preserve header if it exists and is appropriate
                if i == 0 and current_section.get('header'):
                    new_section['header'] = current_section['header']
                
                split_sections.append(new_section)
                logger.info(f"      ✂️ Created section {target_idx + 1}: {len(section_text)} chars")
            
            start_pos = end_pos
        
        return split_sections
    
    def _find_split_points_with_ngrams(self, current_text: str, target_texts: List[str]) -> List[int]:
        """
        Find optimal split points in current_text using n-gram matching with target texts.
        
        Strategy:
        1. Extract end n-grams from each target text
        2. Find best matching positions in current text
        3. Use both forward and backward n-gram matching for accuracy
        """
        if len(target_texts) <= 1:
            return []
        
        split_points = []
        search_start = 0
        
        # For each boundary (except the last), find the split point
        for i in range(len(target_texts) - 1):
            # Get n-grams from the end of current target and start of next target
            current_target_end = self._extract_end_ngrams(target_texts[i])
            next_target_start = self._extract_start_ngrams(target_texts[i + 1])
            
            logger.info(f"      🔍 Finding split {i+1}: end_ngrams={current_target_end}, start_ngrams={next_target_start}")
            
            # Find best match position in current text
            best_position = self._find_best_ngram_match(
                current_text, current_target_end, next_target_start, search_start
            )
            
            if best_position is not None:
                split_points.append(best_position)
                search_start = best_position
                logger.info(f"      ✅ Split point {i+1} found at position {best_position}")
            else:
                # Fallback: split proportionally
                remaining_targets = len(target_texts) - i
                remaining_text = len(current_text) - search_start
                proportional_split = search_start + remaining_text // remaining_targets
                split_points.append(proportional_split)
                search_start = proportional_split
                logger.info(f"      📐 Split point {i+1} fallback at position {proportional_split}")
        
        return split_points
    
    def _extract_end_ngrams(self, text: str, count: int = 3) -> List[str]:
        """Extract the last few n-grams from text."""
        words = text.split()
        if len(words) < self.ngram_size:
            return [' '.join(words)] if words else []
        
        ngrams = []
        for i in range(max(0, len(words) - count - self.ngram_size + 1), len(words) - self.ngram_size + 1):
            ngram = ' '.join(words[i:i + self.ngram_size])
            ngrams.append(ngram.lower())
        
        return ngrams
    
    def _extract_start_ngrams(self, text: str, count: int = 3) -> List[str]:
        """Extract the first few n-grams from text."""
        words = text.split()
        if len(words) < self.ngram_size:
            return [' '.join(words)] if words else []
        
        ngrams = []
        for i in range(min(count, len(words) - self.ngram_size + 1)):
            ngram = ' '.join(words[i:i + self.ngram_size])
            ngrams.append(ngram.lower())
        
        return ngrams
    
    def _find_best_ngram_match(self, text: str, end_ngrams: List[str], start_ngrams: List[str], 
                              search_start: int) -> Optional[int]:
        """
        Find the best position to split text based on n-gram matching.
        """
        best_position = None
        best_score = 0
        
        # Create sliding window to test potential split points
        words = text.split()
        text_lower = text.lower()
        
        # Search for end n-grams (indicating end of current section)
        for end_ngram in end_ngrams:
            end_positions = self._find_ngram_positions(text_lower, end_ngram, search_start)
            
            for pos in end_positions:
                # Check if start n-grams appear after this position
                section_after_start = max(0, pos - search_start)
                start_score = 0
                
                for start_ngram in start_ngrams:
                    start_positions = self._find_ngram_positions(text_lower, start_ngram, pos)
                    if start_positions:
                        # Score based on proximity
                        closest_start = min(start_positions)
                        distance = closest_start - pos
                        if distance < 200:  # Within reasonable distance
                            start_score += 1.0 / (distance + 1)
                
                total_score = 1.0 + start_score  # Base score for finding end ngram
                
                if total_score > best_score:
                    best_score = total_score
                    best_position = pos + len(end_ngram)
        
        return best_position
    
    def _find_ngram_positions(self, text: str, ngram: str, start: int = 0) -> List[int]:
        """Find all positions where an n-gram appears in text."""
        positions = []
        search_pos = start
        
        while True:
            pos = text.find(ngram, search_pos)
            if pos == -1:
                break
            positions.append(pos)
            search_pos = pos + 1
        
        return positions
    
    def _get_section_text(self, section: Dict) -> str:
        """Extract full text from a section (header + body)."""
        header = section.get('header', '')
        body = section.get('body', '')
        return f"{header} {body}".strip()
    
    def _reconstruct_draft_json(self, original_draft: Dict[str, Any], normalized_sections: List[Dict]) -> Dict[str, Any]:
        """Reconstruct the draft JSON with normalized sections."""
        # Create new document structure
        new_document = {
            "documentId": f"normalized_{original_draft.get('draft_id', 'unknown')}",
            "sections": normalized_sections
        }
        
        # Wrap in the same structure as original
        if 'blocks' in original_draft:
            return {
                "draft_id": original_draft['draft_id'],
                "blocks": [
                    {
                        "id": "document",
                        "text": json.dumps(new_document, indent=2)
                    }
                ]
            }
        else:
            # Direct section format
            return {
                "draft_id": original_draft['draft_id'],
                **new_document
            } 