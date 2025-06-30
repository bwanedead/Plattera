"""
Draft Validation Module
=====================

Validates JSON drafts and extracts anchors for alignment quality assessment.
"""

import json
import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter

from .alignment_config import ANCHOR_PATTERNS

logger = logging.getLogger(__name__)

class SchemaError(Exception):
    """Raised when draft fails schema validation"""
    pass

class DraftValidator:
    """Validates JSON drafts and assesses alignment quality"""
    
    def __init__(self):
        self.anchor_patterns = {
            name: re.compile(pattern, re.IGNORECASE) 
            for name, pattern in ANCHOR_PATTERNS.items()
        }
    
    def validate_draft(self, draft: Dict[str, Any]) -> Tuple[bool, Optional[str], List[str]]:
        """
        Validate a single draft and extract anchors
        
        Args:
            draft: JSON draft to validate
            
        Returns:
            Tuple of (is_valid, error_message, anchors_list)
        """
        try:
            # Check basic schema
            if not isinstance(draft, dict):
                return False, "Draft must be a dictionary", []
            
            if "sections" not in draft:
                return False, "Draft missing 'sections' field", []
            
            sections = draft["sections"]
            if not isinstance(sections, list) or len(sections) == 0:
                return False, "Sections must be a non-empty list", []
            
            # Validate section IDs are contiguous starting from 1
            section_ids = [s.get("id") for s in sections]
            expected_ids = list(range(1, len(sections) + 1))
            
            if section_ids != expected_ids:
                return False, f"Section IDs must be contiguous 1-{len(sections)}, got {section_ids}", []
            
            # Validate each section has required fields
            for i, section in enumerate(sections):
                if not isinstance(section, dict):
                    return False, f"Section {i+1} must be a dictionary", []
                
                if "id" not in section:
                    return False, f"Section {i+1} missing 'id' field", []
                
                if "body" not in section:
                    return False, f"Section {i+1} missing 'body' field", []
                
                if not isinstance(section["body"], str):
                    return False, f"Section {i+1} 'body' must be a string", []
            
            # Extract anchors from first 50 tokens of each section
            anchors = self._extract_anchors(sections)
            
            logger.info(f"✅ Draft validation passed. Sections: {len(sections)}, Anchors: {len(anchors)}")
            return True, None, anchors
            
        except Exception as e:
            logger.error(f"❌ Draft validation failed: {str(e)}")
            return False, f"Validation error: {str(e)}", []
    
    def validate_draft_batch(self, drafts: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Validate multiple drafts and separate valid from suspect
        
        Args:
            drafts: List of JSON drafts to validate
            
        Returns:
            Tuple of (valid_drafts, suspect_drafts)
        """
        if len(drafts) > 10:
            logger.warning(f"Too many drafts ({len(drafts)}), limiting to 10")
            drafts = drafts[:10]
        
        valid_drafts = []
        suspect_drafts = []
        section_counts = []
        all_anchors = []
        
        # First pass: basic validation and anchor extraction
        for i, draft in enumerate(drafts):
            is_valid, error_msg, anchors = self.validate_draft(draft)
            
            if not is_valid:
                logger.warning(f"Draft {i+1} failed validation: {error_msg}")
                suspect_drafts.append({
                    "draft": draft,
                    "index": i,
                    "reason": error_msg
                })
                continue
            
            section_count = len(draft["sections"])
            section_counts.append(section_count)
            all_anchors.append(anchors)
            valid_drafts.append({
                "draft": draft,
                "index": i,
                "anchors": anchors,
                "section_count": section_count
            })
        
        if not valid_drafts:
            logger.error("❌ No valid drafts found")
            return [], suspect_drafts
        
        # Second pass: check section count consistency
        modal_section_count = Counter(section_counts).most_common(1)[0][0]
        
        final_valid = []
        for draft_info in valid_drafts:
            if draft_info["section_count"] != modal_section_count:
                logger.warning(f"Draft {draft_info['index']+1} has {draft_info['section_count']} sections, expected {modal_section_count}")
                suspect_drafts.append({
                    "draft": draft_info["draft"],
                    "index": draft_info["index"],
                    "reason": f"Section count mismatch: {draft_info['section_count']} vs expected {modal_section_count}"
                })
            else:
                final_valid.append(draft_info)
        
        # Third pass: anchor conflict detection
        if len(final_valid) > 1:
            anchor_conflicts = self._detect_anchor_conflicts([d["anchors"] for d in final_valid])
            
            # Mark drafts with conflicting anchors as suspect
            for conflict_index in anchor_conflicts:
                if conflict_index < len(final_valid):
                    draft_info = final_valid[conflict_index]
                    logger.warning(f"Draft {draft_info['index']+1} has conflicting anchors")
                    suspect_drafts.append({
                        "draft": draft_info["draft"],
                        "index": draft_info["index"],
                        "reason": "Anchor conflicts detected"
                    })
            
            # Remove conflicted drafts
            final_valid = [d for i, d in enumerate(final_valid) if i not in anchor_conflicts]
        
        logger.info(f"📊 Validation complete: {len(final_valid)} valid, {len(suspect_drafts)} suspect")
        return [d["draft"] for d in final_valid], suspect_drafts
    
    def _extract_anchors(self, sections: List[Dict[str, Any]]) -> List[str]:
        """Extract anchor tokens from first 50 tokens of each section"""
        anchors = []
        
        for section in sections:
            body = section.get("body", "")
            words = body.split()[:50]  # First 50 tokens
            section_text = " ".join(words)
            
            # Find all anchor patterns
            for pattern_name in ["NUM", "FRAC", "BEAR", "DEG", "ID"]:
                if pattern_name in self.anchor_patterns:
                    matches = self.anchor_patterns[pattern_name].findall(section_text)
                    anchors.extend(matches)
        
        return anchors
    
    def _detect_anchor_conflicts(self, anchor_lists: List[List[str]]) -> List[int]:
        """
        Detect drafts with conflicting anchor values
        
        Returns:
            List of draft indices that have conflicting anchors
        """
        if len(anchor_lists) < 2:
            return []
        
        # Count occurrences of each anchor value
        anchor_counter = Counter()
        anchor_to_drafts = {}
        
        for draft_idx, anchors in enumerate(anchor_lists):
            for anchor in anchors:
                normalized_anchor = anchor.lower().strip()
                anchor_counter[normalized_anchor] += 1
                
                if normalized_anchor not in anchor_to_drafts:
                    anchor_to_drafts[normalized_anchor] = []
                anchor_to_drafts[normalized_anchor].append(draft_idx)
        
        # Find the modal (most common) value for each anchor type
        modal_anchors = {}
        for anchor, count in anchor_counter.items():
            if count > 1:  # Only consider anchors that appear multiple times
                modal_anchors[anchor] = count
        
        # Mark drafts that have conflicting anchor values
        conflict_drafts = set()
        for anchor, drafts in anchor_to_drafts.items():
            if len(drafts) > 1 and len(set(anchor_lists[d] for d in drafts)) > 1:
                # Multiple drafts have different values for this anchor
                # Mark minority drafts as conflicted
                anchor_values = [anchor_lists[d] for d in drafts]
                value_counts = Counter(str(av) for av in anchor_values)
                modal_value = value_counts.most_common(1)[0][0]
                
                for draft_idx in drafts:
                    if str(anchor_lists[draft_idx]) != modal_value:
                        conflict_drafts.add(draft_idx)
        
        return list(conflict_drafts) 