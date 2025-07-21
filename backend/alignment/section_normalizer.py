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
        
        # FIXED: Only normalize drafts that need it
        normalized_drafts = []
        for i, (draft_json, sections) in enumerate(zip(draft_jsons, draft_sections)):
            if len(sections) == max_sections:
                # Already has correct section count - DON'T PROCESS IT
                logger.info(f"   ✅ Draft {i+1}: Already has {max_sections} sections, no changes needed")
                normalized_drafts.append(draft_json)  # Return original, unchanged
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
                    sections = document_data.get('sections', [])
                    if sections:
                        logger.info(f"Draft {draft_id}: Successfully parsed {len(sections)} sections from JSON")
                        return sections
                    else:
                        logger.warning(f"Draft {draft_id}: JSON parsed but no sections found")
                        return []
                except json.JSONDecodeError as e:
                    logger.warning(f"Draft {draft_id}: Could not parse JSON: {e}")
                    return []
            
            # Handle pre-parsed sections
            if 'sections' in draft_json:
                sections = draft_json['sections']
                logger.info(f"Draft {draft_id}: Found {len(sections)} pre-parsed sections")
                return sections
            
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
        ROBUST MAPPING: Create mapping that works for any section count or content distribution.
        
        Strategy: Use cumulative length matching with fallback to ensure complete coverage.
        """
        mapping = []
        current_text_lengths = [len(self._get_section_text(section)) for section in current_sections]
        target_text_lengths = [len(self._get_section_text(section)) for section in target_sections]
        
        logger.info(f"   📏 Current section lengths: {current_text_lengths}")
        logger.info(f"   📏 Target section lengths: {target_text_lengths}")
        
        # Handle edge cases
        if not current_text_lengths or not target_text_lengths:
            logger.warning("   ⚠️ Empty sections detected, using fallback mapping")
            return self._create_fallback_mapping(len(current_sections), len(target_sections))
        
        # Calculate total lengths
        total_current = sum(current_text_lengths)
        total_target = sum(target_text_lengths)
        
        if total_current == 0 or total_target == 0:
            logger.warning("   ⚠️ Zero content detected, using fallback mapping")
            return self._create_fallback_mapping(len(current_sections), len(target_sections))
        
        # Create cumulative length arrays
        current_cumulative = [0]
        for length in current_text_lengths:
            current_cumulative.append(current_cumulative[-1] + length)
        
        target_cumulative = [0]
        for length in target_text_lengths:
            target_cumulative.append(target_cumulative[-1] + length)
        
        # Map each target section to appropriate current section
        current_idx = 0
        target_indices = []
        
        for target_idx in range(len(target_sections)):
            # Find which current section this target belongs to
            target_ratio = target_cumulative[target_idx + 1] / total_target
            
            # Find current section that contains this ratio
            while current_idx < len(current_sections):
                current_ratio = current_cumulative[current_idx + 1] / total_current
                
                if current_ratio >= target_ratio:
                    # This target belongs to current section
                    target_indices.append(target_idx)
                    break
                else:
                    # Move to next current section
                    if target_indices:
                        mapping.append((current_idx, target_indices))
                        target_indices = []
                    current_idx += 1
            
            # Handle end of current sections
            if current_idx >= len(current_sections):
                target_indices.append(target_idx)
        
        # Add final mapping
        if target_indices:
            mapping.append((current_idx, target_indices))
        
        # Verify complete coverage
        mapped_targets = set()
        for _, target_indices in mapping:
            mapped_targets.update(target_indices)
        
        if mapped_targets != set(range(len(target_sections))):
            logger.warning(f"   ⚠️ Incomplete mapping detected, using fallback")
            return self._create_fallback_mapping(len(current_sections), len(target_sections))
        
        # Log mappings
        for current_idx, target_indices in mapping:
            current_len = current_text_lengths[current_idx]
            logger.info(f"   🎯 Mapping: Current section {current_idx} ({current_len} chars) → Target sections {target_indices}")
        
        return mapping

    def _create_fallback_mapping(self, current_count: int, target_count: int) -> List[Tuple[int, List[int]]]:
        """Fallback mapping when proportional mapping fails."""
        mapping = []
        
        # Handle edge case where current_count is 0
        if current_count == 0:
            logger.warning(f"   ⚠️ Current count is 0, cannot create meaningful mapping")
            # Return empty mapping - this will cause the draft to be skipped
            return []
        
        targets_per_current = target_count // current_count
        remainder = target_count % current_count
        
        target_idx = 0
        for current_idx in range(current_count):
            # Distribute remainder evenly
            extra = 1 if current_idx < remainder else 0
            num_targets = targets_per_current + extra
            
            target_indices = list(range(target_idx, target_idx + num_targets))
            mapping.append((current_idx, target_indices))
            target_idx += num_targets
        
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
        FIXED: Split a single section into multiple sections using improved boundary detection.
        """
        current_text = self._get_section_text(current_section)
        target_texts = [self._get_section_text(section) for section in target_sections]
        
        logger.info(f"      📝 Splitting text: {len(current_text)} chars → {len(target_texts)} parts")
        
        if len(target_texts) <= 1:
            # No split needed
            return [current_section]
        
        # FIXED: Use improved split point detection
        split_points = self._find_improved_split_points(current_text, target_texts)
        
        # Create new sections based on split points
        split_sections = []
        start_pos = 0
        
        for i, target_idx in enumerate(target_indices):
            if i < len(split_points):
                end_pos = split_points[i]
            else:
                end_pos = len(current_text)
            
            section_text = current_text[start_pos:end_pos].strip()
            
            if section_text:
                new_section = {
                    "id": target_idx + 1,  # 1-based indexing
                    "body": section_text
                }
                
                # Preserve header only for the first section
                if i == 0 and current_section.get('header'):
                    new_section['header'] = current_section['header']
                else:
                    new_section['header'] = None
                
                split_sections.append(new_section)
                logger.info(f"      ✂️ Created section {target_idx + 1}: {len(section_text)} chars")
            
            start_pos = end_pos
        
        return split_sections

    def _find_improved_split_points(self, current_text: str, target_texts: List[str]) -> List[int]:
        """
        FIXED: Find split points using semantic boundaries and proportional fallback.
        """
        if len(target_texts) <= 1:
            return []
        
        split_points = []
        
        # Calculate expected proportions based on target text lengths
        target_lengths = [len(text) for text in target_texts]
        total_target_length = sum(target_lengths)
        current_length = len(current_text)
        
        cumulative_proportion = 0
        
        for i in range(len(target_texts) - 1):  # Don't split after the last section
            # Calculate where this split should be based on proportions
            target_proportion = target_lengths[i] / total_target_length
            cumulative_proportion += target_proportion
            expected_position = int(current_length * cumulative_proportion)
            
            # Look for semantic boundaries near the expected position
            semantic_split = self._find_semantic_boundary_near_position(
                current_text, expected_position, window=100
            )
            
            if semantic_split is not None:
                split_points.append(semantic_split)
                logger.info(f"      ✅ Split point {i+1} found at position {semantic_split} (semantic)")
            else:
                # Fallback to proportional split
                split_points.append(expected_position)
                logger.info(f"      📐 Split point {i+1} at position {expected_position} (proportional)")
        
        return split_points

    def _find_semantic_boundary_near_position(self, text: str, position: int, window: int = 100) -> Optional[int]:
        """
        FIXED: Find a good semantic boundary near the target position.
        """
        import re
        
        start = max(0, position - window)
        end = min(len(text), position + window)
        search_area = text[start:end]
        
        # Look for natural break points (in order of preference)
        patterns = [
            r';\s*\n\s*And\s+beginning',  # End of land parcel
            r':-\s*\n',                   # End of description with colon-dash
            r'follows:-\s*\n',            # End of "described as follows:-"
            r'witnesseth:\s*\n',          # End of witnesseth clause
            r'\.\s*\n\s*[A-Z]',          # Sentence end followed by new sentence
            r';\s*\n',                    # Semicolon + newline
            r'\.\s*\n',                   # Period + newline
        ]
        
        for pattern in patterns:
            matches = list(re.finditer(pattern, search_area, re.IGNORECASE))
            if matches:
                # Find the match closest to our target position within the search area
                target_in_area = position - start
                best_match = min(matches, key=lambda m: abs(m.end() - target_in_area))
                return start + best_match.end()
        
        return None
    
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
        """FIXED: Extract full text from a section (header + body) without duplication."""
        header = section.get('header', '')
        body = section.get('body', '')
        
        # Avoid duplication if header is already in body
        if header and body.startswith(header):
            return body.strip()
        elif header:
            return f"{header} {body}".strip()
        else:
            return body.strip()
    
    def _reconstruct_draft_json(self, original_draft: Dict[str, Any], normalized_sections: List[Dict]) -> Dict[str, Any]:
        """Reconstruct the draft JSON with normalized sections."""
        # Create a copy of the original draft
        reconstructed = original_draft.copy()
        
        # Update sections
        reconstructed['sections'] = normalized_sections
        
        # Update section IDs to be consecutive
        for i, section in enumerate(reconstructed['sections']):
            section['id'] = i + 1
        
        # Preserve other fields but handle missing draft_id gracefully
        if 'draft_id' not in reconstructed:
            # Generate a draft_id if it doesn't exist
            reconstructed['draft_id'] = f"normalized_draft_{id(reconstructed)}"
        
        return reconstructed 