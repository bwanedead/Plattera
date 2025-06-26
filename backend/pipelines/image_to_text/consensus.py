"""
Segmented Fuzzy Matching Consensus Module

Breaks drafts into segments and uses fuzzy matching to align and merge them.
This approach handles word order changes, OCR errors, and variations much better.
"""

import re
import string
from typing import List, Tuple, Dict, Any
from collections import Counter
import logging

try:
    from fuzzywuzzy import fuzz
    from fuzzywuzzy import process
    FUZZY_AVAILABLE = True
except ImportError:
    print("⚠️ FuzzyWuzzy not available - consensus will use basic matching")
    FUZZY_AVAILABLE = False
    fuzz = None
    process = None

logger = logging.getLogger(__name__)

# 🧹 PREPROCESSING UTILITIES
# ==========================

def _preprocess_text(raw: str) -> str:
    """Clean up text - join hyphenated words, normalize whitespace"""
    # Join hyphenated line breaks: "considera-\n    tion" → "consideration"
    text = re.sub(r'(\w+)-\s*\n\s*(\w+)', r'\1\2', raw)
    # Normalize all whitespace to single spaces
    return re.sub(r'\s+', ' ', text.strip())

def _normalize_token(token: str) -> str:
    """Normalize token for comparison - lowercase, strip punctuation"""
    return token.strip(string.punctuation).lower()

# 🔥 SEGMENTED FUZZY CONSENSUS STRATEGY
# =====================================

class SegmentedFuzzyConsensus:
    """
    Segments each draft and uses fuzzy matching to align and merge segments.
    word_match_threshold – Levenshtein ratio (%) needed for two words to be
    regarded as "the same" when computing confidence.
    """
    
    def __init__(self,
                 segment_size: int = 50,
                 fuzzy_threshold: int = 70,
                 word_match_threshold: int = 88):
        self.segment_size          = segment_size
        self.fuzzy_threshold       = fuzzy_threshold
        self.word_match_threshold  = word_match_threshold
        
    def _segment_text(self, text: str) -> List[str]:
        """Break text into segments of roughly equal word count"""
        words = text.split()
        segments = []
        
        for i in range(0, len(words), self.segment_size):
            segment_words = words[i:i + self.segment_size]
            segments.append(' '.join(segment_words))
        
        return segments
    
    def _find_best_segment_match(self, target_segment: str, candidate_segments: List[str]) -> Tuple[int, int]:
        """
        Find the best matching segment using fuzzy matching
        Returns (segment_index, match_score)
        """
        if not FUZZY_AVAILABLE or not candidate_segments:
            return -1, 0
        
        try:
            # Use fuzzywuzzy to find best match
            result = process.extractOne(
                target_segment, 
                candidate_segments, 
                scorer=fuzz.ratio,
                score_cutoff=self.fuzzy_threshold
            )
            
            if result:
                matched_segment, score = result
                segment_idx = candidate_segments.index(matched_segment)
                return segment_idx, score
            
            return -1, 0
        except Exception as e:
            logger.warning(f"Fuzzy matching failed: {e}")
            return -1, 0
    
    def _merge_segments(self, primary_segment: str, matching_segments: List[Tuple[str, int]]) -> Tuple[str, Dict[str, float], Dict[str, List[str]]]:
        """
        Merge a primary segment with its matches from other drafts
        Returns (merged_text, word_confidences, word_alternatives)
        """
        if not matching_segments:
            # No matches - use primary segment with low confidence
            words = primary_segment.split()
            confidences = {f"word_{i}": 0.3 for i in range(len(words))}
            return primary_segment, confidences, {}
        
        # Tokenize all segments
        primary_words = primary_segment.split()
        all_segments = [primary_segment] + [seg for seg, _ in matching_segments]
        all_word_lists = [segment.split() for segment in all_segments]
        
        # For each position in the primary segment, collect candidates
        merged_words = []
        word_confidences = {}
        word_alternatives = {}
        
        for i, primary_word in enumerate(primary_words):
            word_id = f"word_{len(merged_words)}"
            candidates = [primary_word]
            
            # Collect words from matching segments at similar positions
            for word_list in all_word_lists[1:]:  # Skip primary (already added)
                # Try to find corresponding word in other segments
                # Look at same position, then nearby positions
                for offset in [0, -1, 1, -2, 2]:
                    candidate_pos = i + offset
                    if 0 <= candidate_pos < len(word_list):
                        candidate_word = word_list[candidate_pos]
                        if candidate_word not in candidates:
                            candidates.append(candidate_word)
                        break
            
            # -----  NEW  agreement logic  -----
            agree_candidates  = []
            alt_candidates    = []

            for cand in candidates:
                same = (
                    _normalize_token(cand) == _normalize_token(primary_word)
                    or (FUZZY_AVAILABLE and
                        fuzz.ratio(_normalize_token(cand),
                                   _normalize_token(primary_word)) >=
                        self.word_match_threshold)
                )
                (agree_candidates if same else alt_candidates).append(cand)

            consensus_word = primary_word if agree_candidates else candidates[0]
            confidence     = len(agree_candidates) / len(all_segments)

            if alt_candidates:
                # Deduplicate while preserving order
                seen=set()
                word_alternatives[word_id] = [w for w in alt_candidates
                                              if not (seen.add(_normalize_token(w)))]
            
            merged_words.append(consensus_word)
            word_confidences[word_id] = confidence
        
        merged_text = ' '.join(merged_words)
        return merged_text, word_confidences, word_alternatives
    
    def calculate_consensus(self, texts: List[str]) -> Tuple[str, Dict[str, float], Dict[str, List[str]]]:
        """
        🔥 SEGMENTED FUZZY CONSENSUS ALGORITHM 🔥
        
        1. Segment each draft into chunks
        2. Fuzzy match segments across drafts  
        3. Merge aligned segments
        4. Combine into final consensus
        """
        logger.info(f"🔥 SEGMENTED FUZZY CONSENSUS: Processing {len(texts)} drafts with {self.segment_size}-word segments")
        
        if not FUZZY_AVAILABLE:
            logger.warning("FuzzyWuzzy not available - using first draft")
            words = texts[0].split()
            confidence_map = {f"word_{i}": 0.5 for i in range(len(words))}
            return texts[0], confidence_map, {}
        
        # Preprocess all texts
        preprocessed_texts = [_preprocess_text(text) for text in texts]
        
        if len(preprocessed_texts) == 1:
            words = preprocessed_texts[0].split()
            confidence_map = {f"word_{i}": 1.0 for i in range(len(words))}
            return preprocessed_texts[0], confidence_map, {}
        
        # Segment all drafts
        all_segments = [self._segment_text(text) for text in preprocessed_texts]
        
        # Choose the draft with most segments as primary (usually the most complete)
        primary_idx = max(range(len(all_segments)), key=lambda i: len(all_segments[i]))
        primary_segments = all_segments[primary_idx]
        other_segments = [segments for i, segments in enumerate(all_segments) if i != primary_idx]
        
        logger.info(f"📊 Primary draft has {len(primary_segments)} segments")
        logger.info(f"📊 Other drafts have {[len(segs) for segs in other_segments]} segments")
        
        # Process each primary segment
        final_segments = []
        all_word_confidences = {}
        all_word_alternatives = {}
        word_counter = 0
        
        for seg_idx, primary_segment in enumerate(primary_segments):
            logger.info(f"🔍 Processing segment {seg_idx + 1}/{len(primary_segments)}")
            
            # Find best matching segments in other drafts
            segment_matches = []
            
            for other_draft_segments in other_segments:
                match_idx, match_score = self._find_best_segment_match(primary_segment, other_draft_segments)
                
                if match_idx >= 0:
                    matched_segment = other_draft_segments[match_idx]
                    segment_matches.append((matched_segment, match_score))
                    logger.info(f"  ✅ Found match with score {match_score}: '{matched_segment[:50]}...'")
                else:
                    logger.info(f"  ❌ No match found for segment")
            
            # Merge this segment with its matches
            merged_segment, segment_confidences, segment_alternatives = self._merge_segments(
                primary_segment, segment_matches
            )
            
            # Adjust word IDs to be globally unique
            adjusted_confidences = {}
            adjusted_alternatives = {}
            
            for local_word_id, confidence in segment_confidences.items():
                global_word_id = f"word_{word_counter}"
                adjusted_confidences[global_word_id] = confidence
                word_counter += 1
            
            for local_word_id, alternatives in segment_alternatives.items():
                local_idx = int(local_word_id.split('_')[1])
                global_word_id = f"word_{word_counter - len(segment_confidences) + local_idx}"
                adjusted_alternatives[global_word_id] = alternatives
            
            final_segments.append(merged_segment)
            all_word_confidences.update(adjusted_confidences)
            all_word_alternatives.update(adjusted_alternatives)
        
        # Combine all segments into final text
        final_text = ' '.join(final_segments)
        
        logger.info(f"📝 Final consensus: {len(final_text)} characters, {len(all_word_confidences)} words")
        logger.info(f"📊 Found alternatives for {len(all_word_alternatives)} words")
        
        return final_text, all_word_confidences, all_word_alternatives

# 🎯 CONSENSUS ENGINE
# ===================

class ConsensusEngine:
    """
    Simple consensus engine with segmented fuzzy matching
    """
    
    def __init__(self):
        self.strategies = {
            'segmented_fuzzy': SegmentedFuzzyConsensus(segment_size=50, fuzzy_threshold=70),
            'small_segments': SegmentedFuzzyConsensus(segment_size=20, fuzzy_threshold=80),
            'large_segments': SegmentedFuzzyConsensus(segment_size=100, fuzzy_threshold=60),
        }
    
    def calculate_consensus(self, texts: List[str], strategy: str = 'segmented_fuzzy') -> Tuple[str, Dict[str, float], Dict[str, List[str]]]:
        """
        Calculate consensus using segmented fuzzy matching
        
        Args:
            texts: List of text drafts
            strategy: 'segmented_fuzzy', 'small_segments', or 'large_segments'
            
        Returns:
            Tuple of (consensus_text, confidence_map, word_alternatives)
        """
        logger.info(f"🎯 CONSENSUS ENGINE: Using strategy '{strategy}' with {len(texts)} texts")
        
        if strategy not in self.strategies:
            logger.warning(f"Unknown strategy '{strategy}', falling back to 'segmented_fuzzy'")
            strategy = 'segmented_fuzzy'
        
        strategy_obj = self.strategies[strategy]
        result = strategy_obj.calculate_consensus(texts)
        
        consensus_text, confidence_map, word_alternatives = result
        logger.info(f"📊 Generated consensus with {len(confidence_map)} words, {len(word_alternatives)} alternatives")
        
        return result
    
    def get_available_strategies(self) -> List[str]:
        """Get list of available consensus strategies"""
        return list(self.strategies.keys()) 