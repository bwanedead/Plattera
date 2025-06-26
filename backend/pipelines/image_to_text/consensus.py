"""
Consensus Algorithm Module for Image-to-Text Pipeline

Provides multiple strategies for mapping words across text drafts
and calculating consensus with confidence scores.
"""

import re
import string
from typing import List, Tuple, Dict, Any
from difflib import SequenceMatcher
from collections import Counter
import logging

logger = logging.getLogger(__name__)

# 🔴 PREPROCESSING UTILITIES (MOVED FROM PIPELINE.PY) 🔴
# ========================================================

def _preprocess_text(raw: str) -> str:
    """
    Join hyphen-linebreak splits & collapse whitespace.
    
    Handles cases like:
    - 'considera-\n    tions' → 'considerations'
    - Multiple whitespace → single space
    """
    # Join 'word-\n    more' → 'wordmore'
    text = re.sub(r'(\w+)-\s*\n\s*(\w+)', r'\1\2', raw)
    # Unify all whitespace to single spaces
    return re.sub(r'\s+', ' ', text)

def _normalize_token(token: str) -> str:
    """
    Lower-case, strip leading/trailing punctuation for comparison.
    
    Handles cases like:
    - 'less:' vs 'less.' → both become 'less'
    - 'Word,' vs 'word' → both become 'word'
    """
    return token.strip(string.punctuation).lower()

def _build_context_key(tokens: List[str], idx: int, win: int = 5) -> tuple:
    """
    Return a tuple of 11 tokens: 5 left, token, 5 right (normalised).
    
    This creates a unique fingerprint for each word based on its context.
    Used to match words that appear in the same context across drafts,
    even when SequenceMatcher gets confused by insertions/deletions.
    """
    pad = "␢"  # Special padding token for out-of-bounds positions
    left = [_normalize_token(tokens[i]) if i >= 0 else pad
            for i in range(idx - win, idx)]
    token = [_normalize_token(tokens[idx])]
    right = [_normalize_token(tokens[i]) if i < len(tokens) else pad
             for i in range(idx + 1, idx + win + 1)]
    return tuple(left + token + right)

# 🔥 CONSENSUS STRATEGIES 🔥
# ===========================

class ConsensusStrategy:
    """Base class for consensus strategies"""
    
    def calculate_consensus(self, texts: List[str]) -> Tuple[str, Dict[str, float], Dict[str, List[str]]]:
        """Calculate consensus text, confidence map, and word alternatives"""
        raise NotImplementedError

class SequentialStrategy(ConsensusStrategy):
    """
    Current sequential alignment strategy with context-anchor correction
    (Moved from pipeline.py - PRESERVES EXISTING FUNCTIONALITY)
    """
    
    def calculate_consensus(self, texts: List[str]) -> Tuple[str, Dict[str, float], Dict[str, List[str]]]:
        """
        🔴 CURRENT ALGORITHM - PRESERVED EXACTLY 🔴
        """
        # Step 0: Pre-process all drafts
        prepared_texts = [_preprocess_text(text) for text in texts]
        
        if len(prepared_texts) == 1:
            # Single result - perfect confidence for all words
            words = re.findall(r'\S+', prepared_texts[0])
            confidence_map = {f"word_{i}": 1.0 for i in range(len(words))}
            word_alternatives = {}  # No alternatives for single result
            return prepared_texts[0], confidence_map, word_alternatives

        # Step 1: Use longest text as base to preserve document structure
        base_index = max(range(len(prepared_texts)), key=lambda i: len(prepared_texts[i]))
        base_text = prepared_texts[base_index]
        base_tokens = re.findall(r'\S+', base_text)
        base_normalized = [_normalize_token(token) for token in base_tokens]
        
        # Get word positions in base text for replacement (skip pure punctuation)
        word_spans = []
        for match in re.finditer(r'\S+', base_text):
            token = match.group(0)
            if _normalize_token(token):  # Skip punctuation-only tokens
                word_spans.append(match.span())
        
        # Step 2: Initialize candidate lists - each base word starts with itself
        word_candidates = [[base_tokens[i]] for i in range(len(base_normalized))]

        # Step 3: Align every other draft to the base using normalized tokens
        for i, draft_text in enumerate(prepared_texts):
            if i == base_index:
                continue  # Skip the base text itself
                
            other_tokens = re.findall(r'\S+', draft_text)
            other_normalized = [_normalize_token(token) for token in other_tokens]
            
            # Use SequenceMatcher on normalized tokens for better alignment
            matcher = SequenceMatcher(None, base_normalized, other_normalized, autojunk=False)
            
            # Process alignment opcodes - only handle equal and same-length replace
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag == "equal" or (tag == "replace" and (i2 - i1) == (j2 - j1)):
                    # Safe 1-to-1 word mapping
                    for k in range(i2 - i1):
                        word_candidates[i1 + k].append(other_tokens[j1 + k])
                        
                # Note: "insert" and "delete" operations are ignored on purpose
                # This prevents neighbor words from drifting into wrong positions

        # ---------- PASS-2: CONTEXT-ANCHOR CORRECTION ----------
        # Fix alignment errors by matching words with identical 5-word context
        prepared_token_lists = [re.findall(r'\S+', t) for t in prepared_texts]

        # Build lookup tables for every non-base draft
        ctx_lookups = []
        for d_idx, tok_list in enumerate(prepared_token_lists):
            if d_idx == base_index:
                ctx_lookups.append(None)
                continue
            tbl = {}
            for i, _ in enumerate(tok_list):
                ck = _build_context_key(tok_list, i)
                if ck in tbl:
                    tbl[ck] = None          # duplicate – mark as ambiguous
                else:
                    tbl[ck] = i
            ctx_lookups.append(tbl)

        # Walk the base tokens again - add context matches
        for b_idx, b_tok in enumerate(base_tokens):
            ck = _build_context_key(base_tokens, b_idx)
            for d_idx, lookup in enumerate(ctx_lookups):
                if lookup is None:
                    continue
                match_idx = lookup.get(ck)
                if match_idx is None:
                    continue
                # Found a context match - add the token as candidate
                matched_token = prepared_token_lists[d_idx][match_idx]
                if matched_token not in word_candidates[b_idx]:
                    word_candidates[b_idx].append(matched_token)

        # Step 4: Calculate confidence and find consensus for each word
        confidence_map = {}
        consensus_replacements = {}
        word_alternatives = {}
        total_drafts = len(prepared_texts)

        for idx, candidates in enumerate(word_candidates):
            if idx >= len(base_tokens):
                continue  # Safety check
                
            base_token = base_tokens[idx]
            base_norm = base_normalized[idx]
            word_id = f"word_{idx}"
            
            # Calculate confidence based on normalized matches
            exact_matches = sum(1 for word in candidates if _normalize_token(word) == base_norm)
            confidence = exact_matches / total_drafts
            confidence_map[word_id] = confidence

            # Store alternatives - only different normalized forms
            unique_alternatives = {}
            for word in candidates:
                norm = _normalize_token(word)
                if norm != base_norm and norm not in unique_alternatives:
                    unique_alternatives[norm] = word  # Keep first spelling of each variant
            
            # Only store alternatives if there are actual differences
            if unique_alternatives:
                word_alternatives[word_id] = list(unique_alternatives.values())

            # Find consensus word (most common normalized form)
            if len(candidates) > 1:
                # Count occurrences by normalized form
                norm_counts = {}
                for word in candidates:
                    norm = _normalize_token(word)
                    norm_counts[norm] = norm_counts.get(norm, 0) + 1
                
                # Get most common normalized form
                most_common_norm = max(norm_counts.items(), key=lambda x: x[1])[0]
                
                # Find original case version of most common normalized form
                consensus_word = next(word for word in candidates 
                                    if _normalize_token(word) == most_common_norm)
                
                # Only replace if consensus differs from base word
                if consensus_word != base_token:
                    consensus_replacements[idx] = consensus_word

        # Step 5: Build consensus text by applying replacements
        consensus_text = base_text
        
        # Apply replacements from right to left to maintain character positions
        for word_index in sorted(consensus_replacements.keys(), reverse=True):
            if word_index < len(word_spans):
                start_pos, end_pos = word_spans[word_index]
                replacement_word = consensus_replacements[word_index]
                consensus_text = (consensus_text[:start_pos] + 
                                replacement_word + 
                                consensus_text[end_pos:])

        return consensus_text, confidence_map, word_alternatives

class NgramOverlapStrategy(ConsensusStrategy):
    """
    Enhanced N-gram overlap strategy for better word mapping
    """
    
    def __init__(self, ngram_size: int = 3, overlap_threshold: float = 0.3):
        self.ngram_size = ngram_size
        self.overlap_threshold = overlap_threshold
    
    def _get_ngrams(self, tokens: List[str], n: int) -> List[Tuple[str, ...]]:
        """Get n-grams from token list"""
        normalized = [_normalize_token(token) for token in tokens]
        return [tuple(normalized[i:i+n]) for i in range(len(normalized) - n + 1)]
    
    def _calculate_overlap_score(self, word1_context: List[str], word2_context: List[str]) -> float:
        """Calculate overlap score between two word contexts"""
        if not word1_context or not word2_context:
            return 0.0
        
        ngrams1 = set(self._get_ngrams(word1_context, self.ngram_size))
        ngrams2 = set(self._get_ngrams(word2_context, self.ngram_size))
        
        if not ngrams1 or not ngrams2:
            return 0.0
        
        intersection = len(ngrams1.intersection(ngrams2))
        union = len(ngrams1.union(ngrams2))
        
        return intersection / union if union > 0 else 0.0
    
    def _get_word_context(self, tokens: List[str], word_idx: int, window: int = 5) -> List[str]:
        """Get context window around a word"""
        start_idx = max(0, word_idx - window)
        end_idx = min(len(tokens), word_idx + window + 1)
        return tokens[start_idx:end_idx]
    
    def calculate_consensus(self, texts: List[str]) -> Tuple[str, Dict[str, float], Dict[str, List[str]]]:
        """
        🔥 N-GRAM OVERLAP STRATEGY 🔥
        Map words based on surrounding context overlap rather than sequential position
        """
        # Step 0: Pre-process all drafts
        prepared_texts = [_preprocess_text(text) for text in texts]
        
        if len(prepared_texts) == 1:
            words = re.findall(r'\S+', prepared_texts[0])
            confidence_map = {f"word_{i}": 1.0 for i in range(len(words))}
            word_alternatives = {}
            return prepared_texts[0], confidence_map, word_alternatives

        # Step 1: Use longest text as base
        base_index = max(range(len(prepared_texts)), key=lambda i: len(prepared_texts[i]))
        base_text = prepared_texts[base_index]
        base_tokens = re.findall(r'\S+', base_text)
        
        # Get word positions for replacement
        word_spans = []
        for match in re.finditer(r'\S+', base_text):
            token = match.group(0)
            if _normalize_token(token):
                word_spans.append(match.span())
        
        # Step 2: For each base word, find best matches in other drafts using n-gram overlap
        word_candidates = [[] for _ in range(len(base_tokens))]
        
        for base_idx, base_token in enumerate(base_tokens):
            base_context = self._get_word_context(base_tokens, base_idx)
            word_candidates[base_idx].append(base_token)  # Always include base word
            
            # Find matches in other drafts
            for draft_idx, draft_text in enumerate(prepared_texts):
                if draft_idx == base_index:
                    continue
                
                draft_tokens = re.findall(r'\S+', draft_text)
                best_score = 0.0
                best_match = None
                
                # Try each word in the draft
                for word_idx, word in enumerate(draft_tokens):
                    word_context = self._get_word_context(draft_tokens, word_idx)
                    overlap_score = self._calculate_overlap_score(base_context, word_context)
                    
                    if overlap_score > best_score and overlap_score >= self.overlap_threshold:
                        best_score = overlap_score
                        best_match = word
                
                if best_match and best_match not in word_candidates[base_idx]:
                    word_candidates[base_idx].append(best_match)
        
        # Step 3: Calculate confidence and consensus
        confidence_map = {}
        consensus_replacements = {}
        word_alternatives = {}
        total_drafts = len(prepared_texts)

        for idx, candidates in enumerate(word_candidates):
            if idx >= len(base_tokens):
                continue
                
            base_token = base_tokens[idx]
            base_norm = _normalize_token(base_token)
            word_id = f"word_{idx}"
            
            # Calculate confidence based on normalized matches
            exact_matches = sum(1 for word in candidates if _normalize_token(word) == base_norm)
            confidence = exact_matches / total_drafts
            confidence_map[word_id] = confidence

            # Store alternatives - only different normalized forms
            unique_alternatives = {}
            for word in candidates:
                norm = _normalize_token(word)
                if norm != base_norm and norm not in unique_alternatives:
                    unique_alternatives[norm] = word
            
            if unique_alternatives:
                word_alternatives[word_id] = list(unique_alternatives.values())

            # Find consensus word (most common normalized form)
            if len(candidates) > 1:
                norm_counts = Counter(_normalize_token(word) for word in candidates)
                most_common_norm = norm_counts.most_common(1)[0][0]
                
                consensus_word = next(word for word in candidates 
                                    if _normalize_token(word) == most_common_norm)
                
                if consensus_word != base_token:
                    consensus_replacements[idx] = consensus_word

        # Step 4: Build consensus text
        consensus_text = base_text
        for word_index in sorted(consensus_replacements.keys(), reverse=True):
            if word_index < len(word_spans):
                start_pos, end_pos = word_spans[word_index]
                replacement_word = consensus_replacements[word_index]
                consensus_text = (consensus_text[:start_pos] + 
                                replacement_word + 
                                consensus_text[end_pos:])

        return consensus_text, confidence_map, word_alternatives

class StrictMajorityStrategy(ConsensusStrategy):
    """
    Only accept words that appear in majority of drafts
    """
    
    def calculate_consensus(self, texts: List[str]) -> Tuple[str, Dict[str, float], Dict[str, List[str]]]:
        logger.info("🔥 STRICT MAJORITY STRATEGY: Processing consensus")
        
        prepared_texts = [_preprocess_text(text) for text in texts]
        
        if len(prepared_texts) == 1:
            words = re.findall(r'\S+', prepared_texts[0])
            confidence_map = {f"word_{i}": 1.0 for i in range(len(words))}
            return prepared_texts[0], confidence_map, {}

        # Use longest text as base
        base_index = max(range(len(prepared_texts)), key=lambda i: len(prepared_texts[i]))
        base_text = prepared_texts[base_index]
        base_tokens = re.findall(r'\S+', base_text)
        
        # Map words across drafts using sequential alignment
        all_draft_tokens = [re.findall(r'\S+', text) for text in prepared_texts]
        
        confidence_map = {}
        word_alternatives = {}
        majority_threshold = len(prepared_texts) / 2
        
        for i, base_token in enumerate(base_tokens):
            word_id = f"word_{i}"
            candidates = [base_token]  # Always include base word
            
            # Get corresponding words from other drafts
            for draft_tokens in all_draft_tokens:
                if i < len(draft_tokens):
                    candidates.append(draft_tokens[i])
            
            # Count occurrences of each normalized word
            norm_counts = Counter(_normalize_token(word) for word in candidates)
            base_norm = _normalize_token(base_token)
            
            # Only keep words that appear in majority
            majority_words = [norm for norm, count in norm_counts.items() if count > majority_threshold]
            
            if base_norm in majority_words:
                confidence_map[word_id] = norm_counts[base_norm] / len(prepared_texts)
            else:
                # Word doesn't have majority support - low confidence
                confidence_map[word_id] = 0.3
                
            # Store alternatives that have majority support
            unique_alternatives = []
            for word in candidates:
                norm = _normalize_token(word)
                if norm != base_norm and norm in majority_words and word not in unique_alternatives:
                    unique_alternatives.append(word)
            
            if unique_alternatives:
                word_alternatives[word_id] = unique_alternatives

        return base_text, confidence_map, word_alternatives

class LengthWeightedStrategy(ConsensusStrategy):
    """
    Weight consensus by text length - longer texts have more influence
    """
    
    def calculate_consensus(self, texts: List[str]) -> Tuple[str, Dict[str, float], Dict[str, List[str]]]:
        logger.info("🔥 LENGTH WEIGHTED STRATEGY: Processing consensus")
        
        prepared_texts = [_preprocess_text(text) for text in texts]
        
        if len(prepared_texts) == 1:
            words = re.findall(r'\S+', prepared_texts[0])
            confidence_map = {f"word_{i}": 1.0 for i in range(len(words))}
            return prepared_texts[0], confidence_map, {}

        # Calculate weights based on text length
        text_lengths = [len(text) for text in prepared_texts]
        max_length = max(text_lengths)
        weights = [length / max_length for length in text_lengths]
        
        logger.info(f"📏 LENGTH WEIGHTS: {weights}")
        
        # Use longest text as base
        base_index = max(range(len(prepared_texts)), key=lambda i: len(prepared_texts[i]))
        base_text = prepared_texts[base_index]
        base_tokens = re.findall(r'\S+', base_text)
        
        # Map words and calculate weighted confidence
        all_draft_tokens = [re.findall(r'\S+', text) for text in prepared_texts]
        
        confidence_map = {}
        word_alternatives = {}
        
        for i, base_token in enumerate(base_tokens):
            word_id = f"word_{i}"
            candidates = []
            candidate_weights = []
            
            # Collect candidates with their weights
            for draft_idx, draft_tokens in enumerate(all_draft_tokens):
                if i < len(draft_tokens):
                    candidates.append(draft_tokens[i])
                    candidate_weights.append(weights[draft_idx])
            
            # Calculate weighted confidence for base word
            base_norm = _normalize_token(base_token)
            weighted_support = sum(candidate_weights[j] for j, word in enumerate(candidates) 
                                 if _normalize_token(word) == base_norm and j < len(candidate_weights))
            
            confidence_map[word_id] = min(1.0, weighted_support)
            
            # Store weighted alternatives
            unique_alternatives = []
            for word in candidates:
                norm = _normalize_token(word)
                if norm != base_norm and word not in unique_alternatives:
                    unique_alternatives.append(word)
            
            if unique_alternatives:
                word_alternatives[word_id] = unique_alternatives

        return base_text, confidence_map, word_alternatives

class ConfidenceWeightedStrategy(ConsensusStrategy):
    """
    Hybrid approach combining multiple factors
    """
    
    def calculate_consensus(self, texts: List[str]) -> Tuple[str, Dict[str, float], Dict[str, List[str]]]:
        logger.info("🔥 CONFIDENCE WEIGHTED STRATEGY: Processing consensus")
        
        # Use sequential strategy as base, then apply confidence weighting
        sequential = SequentialStrategy()
        base_consensus, base_confidence, base_alternatives = sequential.calculate_consensus(texts)
        
        # Apply additional confidence adjustments
        adjusted_confidence = {}
        for word_id, confidence in base_confidence.items():
            # Boost confidence for words with alternatives (more evidence)
            alternative_boost = 0.1 if word_id in base_alternatives else 0.0
            
            # Boost confidence for longer words (more specific)
            word_idx = int(word_id.split('_')[1]) if '_' in word_id else 0
            word_tokens = re.findall(r'\S+', base_consensus)
            if word_idx < len(word_tokens):
                word_length = len(word_tokens[word_idx])
                length_boost = min(0.2, word_length * 0.02)  # Up to 0.2 boost
            else:
                length_boost = 0.0
            
            adjusted_confidence[word_id] = min(1.0, confidence + alternative_boost + length_boost)
        
        return base_consensus, adjusted_confidence, base_alternatives

class ChunkedConsensusStrategy(ConsensusStrategy):
    def calculate_consensus(self, texts):
        # TODO: Implement chunked consensus
        # For now, fall back to sequential strategy
        sequential = SequentialStrategy()
        return sequential.calculate_consensus(texts)

class GraphBasedStrategy(ConsensusStrategy):
    def calculate_consensus(self, texts):
        # TODO: Implement graph-based consensus
        # For now, fall back to sequential strategy
        sequential = SequentialStrategy()
        return sequential.calculate_consensus(texts)

# 🎯 CONSENSUS ENGINE 🎯
# =======================

class ConsensusEngine:
    """
    Main consensus engine that can use different strategies
    """
    
    def __init__(self):
        self.strategies = {
            'sequential': SequentialStrategy(),
            'ngram_overlap': NgramOverlapStrategy(),
            'strict_majority': StrictMajorityStrategy(),
            'length_weighted': LengthWeightedStrategy(),
            'confidence_weighted': ConfidenceWeightedStrategy(),
            # Remove these until they're properly implemented:
            # 'chunked_consensus': ChunkedConsensusStrategy(),
            # 'graph_based': GraphBasedStrategy(),
        }
    
    def calculate_consensus(self, texts: List[str], strategy: str = 'sequential') -> Tuple[str, Dict[str, float], Dict[str, List[str]]]:
        """
        Calculate consensus using specified strategy
        
        Args:
            texts: List of text drafts
            strategy: Strategy name ('sequential', 'ngram_overlap', etc.)
            
        Returns:
            Tuple of (consensus_text, confidence_map, word_alternatives)
        """
        # ADD DEBUG LOGGING
        logger.info(f"🎯 CONSENSUS ENGINE: Using strategy '{strategy}' with {len(texts)} texts")
        
        if strategy not in self.strategies:
            logger.warning(f"Unknown strategy '{strategy}', falling back to 'sequential'")
            strategy = 'sequential'
        
        # ADD DEBUG LOGGING FOR STRATEGY SELECTION
        strategy_obj = self.strategies[strategy]
        logger.info(f"🔧 CONSENSUS ENGINE: Selected strategy object: {type(strategy_obj).__name__}")
        
        result = strategy_obj.calculate_consensus(texts)
        
        # ADD DEBUG LOGGING FOR RESULTS
        consensus_text, confidence_map, word_alternatives = result
        logger.info(f"📊 CONSENSUS ENGINE: Generated {len(confidence_map)} confidence scores, {len(word_alternatives)} alternatives")
        
        return result
    
    def get_available_strategies(self) -> List[str]:
        """Get list of available consensus strategies"""
        return list(self.strategies.keys()) 