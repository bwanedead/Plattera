"""
Section Count Normalizer
========================

Handles the post-processing normalization of drafts when they have different section counts.
Uses alignment-based matching to split under-sectioned drafts.
"""

import logging
import json
from typing import List, Dict, Any, Tuple
from collections import defaultdict, Counter
import difflib
import bisect
import re
import unicodedata

logger = logging.getLogger(__name__)

# Add these helper functions at the top
_pat = re.compile(r"[^\w']+")
_token_re = re.compile(r"\S+")

def _norm(w: str) -> str:
    """lower + strip diacritics + remove punct"""
    w = unicodedata.normalize("NFKD", w).encode("ascii", "ignore").decode()
    return _pat.sub("", w.lower())

def _jaccard(a: list[str], b: list[str]) -> float:
    """Compute Jaccard similarity between two token lists."""
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)

def _words_similar(a: str, b: str, thresh: float = .75) -> bool:
    """Check if two words are similar using stricter normalization."""
    a_n, b_n = _norm(a), _norm(b)
    if not a_n or not b_n:
        return False
    return difflib.SequenceMatcher(None, a_n, b_n).ratio() >= thresh

def _tokenise_with_pos(text: str) -> tuple[list[str], list[int]]:
    """
    Return tokens **and** their start positions in `text`.
    positions[i] is the char‑offset of tokens[i].
    """
    tokens, starts = [], []
    for m in _token_re.finditer(text):
        tokens.append(m.group())
        starts.append(m.start())
    return tokens, starts

class SectionNormalizer:
    """
    Normalizes section counts across redundant drafts by intelligently splitting 
    under-sectioned drafts to match the most granular draft.
    """
    
    def __init__(self, similarity_threshold: float = 0.6):
        self.sim_threshold = similarity_threshold
    
    # ---------------------------------------------------------------------
    #  A.  Text used for ALIGNMENT     (header+body for FIRST section only)
    # ---------------------------------------------------------------------
    def _get_alignment_text(self, section: Dict) -> str:
        hdr, body = section.get('header', ''), section.get('body', '')
        return (hdr + " " + body).strip() if hdr else body

    # ---------------------------------------------------------------------
    #  B.  Text saved back into JSON   (body-only, header lives in `header`)
    # ---------------------------------------------------------------------
    def _get_section_text(self, section: Dict) -> str:
        return section.get('body', '')
    
    def _best_boundary(self,
                       tokens: list[str],
                       left_tmpl: list[str],
                       right_tmpl: list[str],
                       window: int = 8) -> int:
        """
        Return token-index that maximises suffix/prefix Jaccard similarity.
        """
        best_k, best_score = 0, -1.0
        for k in range(1, len(tokens)):             # gap between tokens[k-1] | tokens[k]
            left_slice  = tokens[max(0, k-window):k]
            right_slice = tokens[k:min(len(tokens), k+window)]
            s = (_jaccard(left_slice, left_tmpl[-window:]) +
                 _jaccard(right_slice, right_tmpl[:window]))
            if s > best_score:
                best_score, best_k = s, k
        return best_k

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
        target_full = ''.join(self._get_alignment_text(s) for s in target_sections)
        current_full = ''.join(self._get_alignment_text(s) for s in current_sections)
        
        # FIX: Correct order - compare current to target (not target to current)
        sm = difflib.SequenceMatcher(None, current_full, target_full)
        
        if sm.real_quick_ratio() < self.sim_threshold:
            logger.warning(f"   ⚠️ Low overall similarity, using fallback mapping")
            return self._create_fallback_mapping(len(current_sections), len(target_sections))
        
        # Target section starts in target text
        target_starts = [0]
        for s in target_sections:
            target_starts.append(target_starts[-1] + len(self._get_alignment_text(s)))
        target_starts = target_starts[:-1]
        
        # Map target starts to positions in current text
        mapped_starts = [self._map_position(p, sm) for p in target_starts]
        
        # Current section boundaries in current text
        current_starts = [0]
        for s in current_sections:
            current_starts.append(current_starts[-1] + len(self._get_alignment_text(s)))
        
        # Assign target sections to current sections
        mapping_dict = defaultdict(list)
        for t_idx, mapped_pos in enumerate(mapped_starts):
            # Use bisect_right to avoid boundary mis-alignments
            c_idx = bisect.bisect_right(current_starts, mapped_pos) - 1
            # FIX: Ensure we don't go below 0
            c_idx = max(0, min(c_idx, len(current_sections) - 1))
            mapping_dict[c_idx].append(t_idx)
        
        # FIX: Ensure all target sections are mapped
        mapped_targets = set()
        for t_list in mapping_dict.values():
            mapped_targets.update(t_list)
        
        # Add unmapped target sections to the last current section
        unmapped_targets = set(range(len(target_sections))) - mapped_targets
        if unmapped_targets:
            last_current = len(current_sections) - 1
            mapping_dict[last_current].extend(sorted(unmapped_targets))
            logger.info(f"   🔧 Added unmapped targets {sorted(unmapped_targets)} to current section {last_current}")
        
        mapping = [(k, sorted(mapping_dict[k])) for k in sorted(mapping_dict) if mapping_dict[k]]
        
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
    
    def _snap_to_boundary(self, text: str, pos: int, max_shift: int = 10) -> int:
        """
        Move `pos` to the closest whitespace boundary.
        Prefer moving left; only move right if no whitespace found within `max_shift`.
        """
        # Early exits
        if pos <= 0 or pos >= len(text) or text[pos].isspace():
            return pos

        # First look for newline to the left
        ln_left = text.rfind("\n", max(0, pos - max_shift), pos)
        if ln_left != -1:
            return ln_left + 1  # character right after newline

        # Otherwise ← search left for any whitespace
        left = pos
        for _ in range(max_shift):
            if left > 0 and not text[left - 1].isspace():
                left -= 1
            else:
                return left

        # → search right
        right = pos
        for _ in range(max_shift):
            if right < len(text) and not text[right].isspace():
                right += 1
            else:
                return right

        # nothing found, return original
        return pos

    def _validate_split_points(self, current_txt: str,
                               target_chunks: List[str],
                               split_pts: List[int]) -> List[int]:
        """
        If the trailing 3-gram of each produced slice is dissimilar to
        the trailing 3-gram of its template chunk, nudge boundary by one word.
        """
        def last_ngram(text, n=3):
            return " ".join(text.rstrip().split()[-n:]).lower()

        validated = []
        start = 0
        for idx, pt in enumerate(split_pts + [len(current_txt)]):
            slice_txt = current_txt[start:pt]
            template_txt = target_chunks[idx] if idx < len(target_chunks) else ""
            sim = difflib.SequenceMatcher(None,
                                  last_ngram(slice_txt),
                                  last_ngram(template_txt)).ratio()
            if sim < 0.5:       # low similarity → boundary probably off by one word
                # try shifting left by one more word
                new_pt = self._snap_to_boundary(current_txt, pt - 1, 30)
                new_slice_txt = current_txt[start:new_pt]
                new_sim = difflib.SequenceMatcher(None,
                                          last_ngram(new_slice_txt),
                                          last_ngram(template_txt)).ratio()
                if new_sim > sim:
                    pt = new_pt
                    logger.info(f"        🔧 Adjusted boundary: similarity improved from {sim:.2f} to {new_sim:.2f}")
            
            # Extra guard: if the *last word* mismatches, try shifting once more
            if validated:
                prev_end = validated[-1]
            else:
                prev_end = 0
            
            # Safety check: ensure valid slice indices
            if prev_end < pt and pt <= len(current_txt):
                last_word_slice = current_txt[prev_end:pt].rstrip().split()[-1:]
                last_word_tmpl = template_txt.rstrip().split()[-1:]
                if last_word_slice and last_word_tmpl and last_word_slice[0].lower() != last_word_tmpl[0].lower():
                    # try moving boundary left until words align or max 30 chars
                    adjust = 0
                    while adjust < 30 and pt > 0 and not current_txt[pt - 1].isspace():
                        pt -= 1
                        adjust += 1
                    logger.info(f"        🔧 Nudged {adjust} chars for word‑match correction")
            
            validated.append(pt)
            start = pt
        return validated[:-1]  # last element is len(current_txt) – not stored

    def _audit_boundary(self, prev_txt: str, next_txt: str,
                        tmpl_prev: str, tmpl_next: str,
                        original: str, start_char: int) -> int:
        """
        Check if the last token of prev / first token of next
        really match their respective templates.
        If not, walk left ≤20 chars or right ≤20 chars to find the
        first position that satisfies both tail & head similarity.
        Return the corrected char-offset or None when already good.
        """
        tokens_prev = prev_txt.rstrip().split()
        tokens_next = next_txt.lstrip().split()
        if not tokens_prev or not tokens_next:
            return start_char

        tail, head = tokens_prev[-1], tokens_next[0]
        t_tail = tmpl_prev.rstrip().split()[-1] if tmpl_prev else ""
        t_head = tmpl_next.lstrip().split()[0] if tmpl_next else ""

        if _words_similar(tail, t_tail) and _words_similar(head, t_head):
            return start_char          # looks good

        # search window
        for delta in range(1, 21):
            # ← left
            if start_char - delta > 0 and original[start_char-delta] == " ":
                new_prev = original[: start_char-delta]
                new_next = original[start_char-delta :]
                if (new_prev.rstrip().split() and new_next.lstrip().split() and
                    _words_similar(new_prev.rstrip().split()[-1], t_tail) and
                    _words_similar(new_next.lstrip().split()[0],  t_head)):
                    logger.info(f"        🔧 Audit: moved boundary left by {delta} chars")
                    return start_char - delta
            # → right
            if start_char+delta < len(original) and start_char+delta > 0 and original[start_char+delta-1] == " ":
                new_prev = original[: start_char+delta]
                new_next = original[start_char+delta :]
                if (new_prev.rstrip().split() and new_next.lstrip().split() and
                    _words_similar(new_prev.rstrip().split()[-1], t_tail) and
                    _words_similar(new_next.lstrip().split()[0],  t_head)):
                    logger.info(f"        🔧 Audit: moved boundary right by {delta} chars")
                    return start_char + delta
        return start_char

    def _split_sections_using_mapping(self, current_sections: List[Dict], target_sections: List[Dict], 
                                      mapping: List[Tuple[int, List[int]]]) -> List[Dict]:
        """Split sections based on mapping."""
        # Create a list to hold all sections in the correct order
        all_sections = [None] * len(target_sections)
        
        # Keep track of which current sections have been processed
        processed_current = set()
        
        for c_idx, t_indices in mapping:
            processed_current.add(c_idx)
            
            if len(t_indices) == 1:
                # 1:1 mapping - just copy the section
                target_idx = t_indices[0]
                new_section = current_sections[c_idx].copy()
                new_section['id'] = target_idx + 1
                all_sections[target_idx] = new_section
                logger.info(f"      📋 Current {c_idx} → Target {target_idx} (1:1 copy)")
                
            else:
                # 1:many mapping - split the section
                splits = self._split_single_section(current_sections[c_idx], [target_sections[i] for i in t_indices], t_indices)
                
                # Place each split section in the correct position
                for i, split_section in enumerate(splits):
                    if i < len(t_indices):  # Safety check
                        target_idx = t_indices[i]
                        all_sections[target_idx] = split_section
                        logger.info(f"      ✂️ Current {c_idx} split → Target {target_idx}")
        
        # Handle any unprocessed current sections - place them in remaining empty slots
        # Preserve section order after a split
        unprocessed_current = sorted(
            i for i in range(len(current_sections))
            if i not in processed_current
        )
        empty_target_slots = sorted(
            i for i, section in enumerate(all_sections)
            if section is None
        )
        
        for current_idx, target_idx in zip(unprocessed_current, empty_target_slots):
            new_section = current_sections[current_idx].copy()
            new_section['id'] = target_idx + 1
            all_sections[target_idx] = new_section
            logger.info(f"      📌 Current {current_idx} → Target {target_idx}")
        
        # Handle any remaining None values by creating placeholder sections
        for i, section in enumerate(all_sections):
            if section is None:
                logger.warning(f"   🔧 Creating placeholder section for missing target {i}")
                all_sections[i] = {
                    "id": i + 1,
                    "header": None,
                    "body": f"[Placeholder section {i + 1}]"
                }
        
        # Remove None values and return (should be none now)
        normalized = [section for section in all_sections if section is not None]
        
        # Ensure we have the right number of sections
        if len(normalized) != len(target_sections):
            logger.warning(f"   ⚠️ Expected {len(target_sections)} sections, got {len(normalized)}")
        
        return normalized
    
    def _split_single_section(self, current_section: Dict, target_group: List[Dict], target_indices: List[int]) -> List[Dict]:
        """Split one section into multiple using token-based boundary scoring."""
        local_text = self._get_alignment_text(current_section)
        group_texts = [self._get_alignment_text(s) for s in target_group]
        
        # Tokenize once, with positions
        tokens, starts = _tokenise_with_pos(local_text)
        tmpl_tokens = [gt.split() for gt in group_texts]
        
        split_points = []
        start_tok = 0
        
        for i in range(len(target_group) - 1):
            left_tmpl = tmpl_tokens[i]
            right_tmpl = tmpl_tokens[i + 1]
            
            # Find best boundary
            best_k = self._best_boundary(tokens[start_tok:], left_tmpl, right_tmpl)
            
            # Convert to character position using real offsets
            char_pos = starts[start_tok + best_k]  # exact location in original text
            
            # Optional: still snap to whitespace if needed
            char_pos = self._snap_to_boundary(local_text, char_pos)
            
            split_points.append(char_pos)
            start_tok += best_k
        
        # Create sections from split points
        sections = []
        prev_pos = 0
        
        for i, pos in enumerate(split_points + [len(local_text)]):
            section_text = local_text[prev_pos:pos].strip()
            if section_text:
                hdr = current_section.get('header') if i == 0 else None
                # Strip header from body if it's duplicated
                if hdr and section_text.startswith(hdr):
                    section_text = section_text[len(hdr):].strip()
                
                new_section = {
                    "id": target_indices[i] + 1,
                    "body": section_text,
                    "header": hdr
                }
                sections.append(new_section)
            prev_pos = pos
        
        return sections
    
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