"""
Section Count Normalizer
========================

Handles the post-processing normalization of drafts when they have different section counts.
Uses alignment-based matching to split under-sectioned drafts.
"""

import logging
import json
from typing import List, Dict, Any, Tuple
from collections import defaultdict
import difflib
import bisect

logger = logging.getLogger(__name__)

class SectionNormalizer:
    """
    Normalizes section counts across redundant drafts by intelligently splitting 
    under-sectioned drafts to match the most granular draft.
    """
    
    def __init__(self, similarity_threshold: float = 0.6):
        self.sim_threshold = similarity_threshold
    
    def normalize_draft_sections(self, draft_jsons: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Main entry point: normalize section counts across all drafts.
        
        Args:
            draft_jsons: List of draft dictionaries
            
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
        
        logger.info(f"🎯 TARGET DRAFT ► Draft {target_draft_idx + 1} with {max_sections} sections will be the template")
        
        # Normalize drafts that need it
        normalized_drafts = []
        for i, (draft_json, sections) in enumerate(zip(draft_jsons, draft_sections)):
            if len(sections) == max_sections:
                logger.info(f"   ✅ Draft {i+1}: Already has {max_sections} sections, no changes")
                normalized_drafts.append(draft_json)
            else:
                logger.info(f"   🔄 Draft {i+1}: Normalizing {len(sections)} → {max_sections} sections")
                normalized_draft = self._normalize_single_draft(draft_json, sections, target_sections, f"Draft_{i+1}")
                normalized_drafts.append(normalized_draft)
        
        logger.info(f"✅ NORMALIZATION COMPLETE ► All drafts now have {max_sections} sections")
        return normalized_drafts
    
    def _extract_sections_from_draft(self, draft_json: Dict[str, Any], draft_id: str) -> List[Dict[str, Any]]:
        """Extract section data from a draft JSON."""
        try:
            if 'blocks' in draft_json and draft_json['blocks']:
                first_block_text = draft_json['blocks'][0].get('text', '')
                try:
                    document_data = json.loads(first_block_text)
                    sections = document_data.get('sections', [])
                    if sections:
                        logger.info(f"Draft {draft_id}: Parsed {len(sections)} sections from JSON")
                        return sections
                    else:
                        logger.warning(f"Draft {draft_id}: JSON parsed but no sections")
                        return []
                except json.JSONDecodeError as e:
                    logger.warning(f"Draft {draft_id}: Could not parse JSON: {e}")
                    return []
            
            if 'sections' in draft_json:
                sections = draft_json['sections']
                logger.info(f"Draft {draft_id}: Found {len(sections)} pre-parsed sections")
                return sections
            
            logger.error(f"Draft {draft_id}: No recognizable section format")
            return []
            
        except Exception as e:
            logger.error(f"Draft {draft_id}: Error extracting sections: {e}")
            return []
    
    def _normalize_single_draft(self, draft_json: Dict[str, Any], current_sections: List[Dict], 
                              target_sections: List[Dict], draft_id: str) -> Dict[str, Any]:
        """
        Normalize a single draft to match the target section count.
        """
        logger.info(f"🔍 NORMALIZING {draft_id} ► {len(current_sections)} → {len(target_sections)} sections")
        
        # Create mapping
        section_mapping = self._create_section_mapping(current_sections, target_sections)
        
        # Split sections
        normalized_sections = self._split_sections_using_mapping(current_sections, target_sections, section_mapping)
        
        # Reconstruct
        return self._reconstruct_draft_json(draft_json, normalized_sections)
    
    def _create_section_mapping(self, current_sections: List[Dict], target_sections: List[Dict]) -> List[Tuple[int, List[int]]]:
        """
        Create mapping using content alignment.
        """
        target_full = ''.join(self._get_section_text(s) for s in target_sections)
        current_full = ''.join(self._get_section_text(s) for s in current_sections)
        
        # FIX: Correct order - compare current to target (not target to current)
        sm = difflib.SequenceMatcher(None, current_full, target_full)
        
        if sm.real_quick_ratio() < self.sim_threshold:
            logger.warning(f"   ⚠️ Low overall similarity, using fallback mapping")
            return self._create_fallback_mapping(len(current_sections), len(target_sections))
        
        # Target section starts in target text
        target_starts = [0]
        for s in target_sections:
            target_starts.append(target_starts[-1] + len(self._get_section_text(s)))
        target_starts = target_starts[:-1]
        
        # Map target starts to positions in current text
        mapped_starts = [self._map_position(p, sm) for p in target_starts]
        
        # Current section boundaries in current text
        current_starts = [0]
        for s in current_sections:
            current_starts.append(current_starts[-1] + len(self._get_section_text(s)))
        
        # Assign target sections to current sections
        mapping_dict = defaultdict(list)
        for t_idx, mapped_pos in enumerate(mapped_starts):
            c_idx = bisect.bisect_left(current_starts, mapped_pos) - 1
            if 0 <= c_idx < len(current_sections):
                mapping_dict[c_idx].append(t_idx)
        
        mapping = [(k, mapping_dict[k]) for k in sorted(mapping_dict) if mapping_dict[k]]
        
        # Log
        for c_idx, t_list in mapping:
            logger.info(f"   🎯 Mapping: Current {c_idx} → Target {t_list}")
        
        return mapping
    
    def _map_position(self, pos: int, sm: difflib.SequenceMatcher) -> int:
        """Map position from target text to current text using SequenceMatcher opcodes."""
        if pos == len(sm.b):  # sm.b is now target_full
            return len(sm.a)   # sm.a is now current_full
        
        for tag, a_start, a_end, b_start, b_end in sm.get_opcodes():
            if b_start <= pos < b_end:  # Check if position is in target range (b)
                if tag in ['equal', 'replace']:
                    frac = (pos - b_start) / (b_end - b_start) if b_end > b_start else 0
                    return a_start + int(frac * (a_end - a_start))  # Map to current range (a)
                elif tag == 'insert':
                    return a_start
        return len(sm.a)
    
    def _create_fallback_mapping(self, current_count: int, target_count: int) -> List[Tuple[int, List[int]]]:
        """Fallback even distribution mapping."""
        if current_count == 0:
            return []
        
        targets_per = target_count // current_count
        remainder = target_count % current_count
        
        mapping = []
        t_idx = 0
        for c_idx in range(current_count):
            num = targets_per + (1 if c_idx < remainder else 0)
            t_list = list(range(t_idx, t_idx + num))
            mapping.append((c_idx, t_list))
            t_idx += num
        return mapping
    
    def _split_sections_using_mapping(self, current_sections: List[Dict], target_sections: List[Dict], 
                                      mapping: List[Tuple[int, List[int]]]) -> List[Dict]:
        """Split sections based on mapping."""
        normalized = []
        for c_idx, t_indices in mapping:
            if len(t_indices) == 1:
                normalized.append(current_sections[c_idx])
            else:
                splits = self._split_single_section(current_sections[c_idx], [target_sections[i] for i in t_indices], t_indices)
                normalized.extend(splits)
        return normalized
    
    def _split_single_section(self, current_section: Dict, target_group: List[Dict], target_indices: List[int]) -> List[Dict]:
        """Split one section into multiple using alignment."""
        local_text = self._get_section_text(current_section)
        group_texts = [self._get_section_text(s) for s in target_group]
        group_full = ''.join(group_texts)
        
        sm = difflib.SequenceMatcher(None, group_full, local_text)
        
        group_starts = [0]
        for gt in group_texts[:-1]:
            group_starts.append(group_starts[-1] + len(gt))
        
        if sm.real_quick_ratio() < self.sim_threshold:
            logger.warning("      ⚠️ Low similarity for split, using proportional")
            total = len(group_full)
            split_points = []
            cum = 0
            for l in [len(gt) for gt in group_texts[:-1]]:
                cum += l
                pos = int((cum / total) * len(local_text))
                split_points.append(pos)
        else:
            split_points = [self._map_position(p, sm) for p in group_starts[1:]]
        
        # Clamp and sort split points to ensure order
        split_points = sorted([max(0, min(len(local_text), p)) for p in split_points])
        
        # Create sections
        split_sections = []
        start = 0
        for i, t_idx in enumerate(target_indices):
            end = split_points[i] if i < len(split_points) else len(local_text)
            section_text = local_text[start:end]
            
            if section_text:
                new_section = {
                    "id": t_idx + 1,
                    "body": section_text,
                    "header": current_section.get('header') if i == 0 else None
                }
                split_sections.append(new_section)
                logger.info(f"      ✂️ Created section {t_idx + 1}: {len(section_text)} chars")
            
            start = end
        
        return split_sections
    
    def _get_section_text(self, section: Dict) -> str:
        """Extract full text from section without duplication."""
        header = section.get('header', '')
        body = section.get('body', '')
        if header and body.startswith(header):
            return body
        elif header:
            return f"{header} {body}"
        else:
            return body
    
    def _reconstruct_draft_json(self, original_draft: Dict[str, Any], normalized_sections: List[Dict]) -> Dict[str, Any]:
        """Reconstruct draft JSON with normalized sections."""
        reconstructed = original_draft.copy()
        reconstructed['sections'] = normalized_sections
        
        # Reassign consecutive IDs
        for i, section in enumerate(reconstructed['sections']):
            section['id'] = i + 1
        
        if 'draft_id' not in reconstructed:
            reconstructed['draft_id'] = f"normalized_draft_{id(reconstructed)}"
        
        return reconstructed 