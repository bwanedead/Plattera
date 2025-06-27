"""
Progressive Multi-Sequence Alignment Module
==========================================

Implements anchor-aware Needleman-Wunsch alignment for legal documents.
Handles multiple drafts with semantic section alignment.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from dataclasses import dataclass
from collections import defaultdict

from .alignment_config import ALIGN, LIMITS
from .tokenise import Token, DocumentTokenizer

logger = logging.getLogger(__name__)

@dataclass
class AlignmentColumn:
    """Represents a column in the alignment grid"""
    tokens: List[Optional[Token]]  # One token per draft (None for gaps)
    section_id: int
    position: int

class AlignmentGrid:
    """Holds the complete alignment result"""
    
    def __init__(self, num_drafts: int):
        self.num_drafts = num_drafts
        self.columns: List[AlignmentColumn] = []
        self.section_alignments: Dict[int, List[AlignmentColumn]] = defaultdict(list)
    
    def add_column(self, tokens: List[Optional[Token]], section_id: int, position: int):
        """Add a column to the alignment"""
        if len(tokens) != self.num_drafts:
            raise ValueError(f"Column must have {self.num_drafts} tokens, got {len(tokens)}")
        
        column = AlignmentColumn(tokens, section_id, position)
        self.columns.append(column)
        self.section_alignments[section_id].append(column)
    
    def get_section_alignment(self, section_id: int) -> List[AlignmentColumn]:
        """Get alignment columns for a specific section"""
        return self.section_alignments.get(section_id, [])

class DocumentAligner:
    """Handles progressive multi-sequence alignment of legal documents"""
    
    def __init__(self):
        self.tokenizer = DocumentTokenizer()
    
    def align_documents(self, documents: List[Dict[str, Any]]) -> AlignmentGrid:
        """
        Align multiple JSON documents using progressive MSA
        
        Args:
            documents: List of validated JSON documents
            
        Returns:
            AlignmentGrid with complete alignment
        """
        if len(documents) > LIMITS["MAX_DRAFTS"]:
            logger.warning(f"Too many documents ({len(documents)}), limiting to {LIMITS['MAX_DRAFTS']}")
            documents = documents[:LIMITS["MAX_DRAFTS"]]
        
        if len(documents) < 2:
            logger.warning("Need at least 2 documents for alignment")
            if len(documents) == 1:
                # Single document - create trivial alignment
                return self._create_single_document_alignment(documents[0])
            else:
                raise ValueError("No documents to align")
        
        logger.info(f"🔥 Starting progressive MSA with {len(documents)} documents")
        
        # Tokenize all documents by section
        tokenized_docs = []
        for i, doc in enumerate(documents):
            sections = doc.get("sections", [])
            tokenized_sections = self.tokenizer.tokenize_sections(sections)
            tokenized_docs.append(tokenized_sections)
            logger.debug(f"Document {i+1}: {sum(len(tokens) for tokens in tokenized_sections.values())} total tokens")
        
        # Progressive alignment: start with best pair, then add others
        draft_quality_scores = self._assess_draft_quality(tokenized_docs)
        sorted_indices = sorted(range(len(documents)), key=lambda i: draft_quality_scores[i], reverse=True)
        
        logger.info(f"📊 Draft quality scores: {dict(enumerate(draft_quality_scores))}")
        logger.info(f"📊 Processing order: {[i+1 for i in sorted_indices]}")
        
        # Start with the two highest quality drafts
        primary_idx = sorted_indices[0]
        secondary_idx = sorted_indices[1]
        
        logger.info(f"🎯 Starting with drafts {primary_idx+1} and {secondary_idx+1}")
        
        # Initial pairwise alignment
        current_alignment = self._align_two_documents(
            tokenized_docs[primary_idx], 
            tokenized_docs[secondary_idx],
            [primary_idx, secondary_idx]
        )
        
        # Progressively add remaining documents
        for i in range(2, len(sorted_indices)):
            doc_idx = sorted_indices[i]
            logger.info(f"🔄 Adding document {doc_idx+1} to alignment")
            
            current_alignment = self._add_document_to_alignment(
                current_alignment,
                tokenized_docs[doc_idx],
                doc_idx
            )
        
        logger.info(f"✅ Progressive MSA complete: {len(current_alignment.columns)} aligned columns")
        return current_alignment
    
    def _assess_draft_quality(self, tokenized_docs: List[Dict[int, List[Token]]]) -> List[float]:
        """Assess quality of each draft based on token count and anchor density"""
        quality_scores = []
        
        for doc in tokenized_docs:
            total_tokens = sum(len(tokens) for tokens in doc.values())
            anchor_tokens = sum(sum(1 for token in tokens if token.is_anchor) for tokens in doc.values())
            
            # Quality = token count + anchor bonus
            anchor_ratio = anchor_tokens / max(total_tokens, 1)
            quality_score = total_tokens + (anchor_ratio * 100)  # Bonus for anchor density
            quality_scores.append(quality_score)
        
        return quality_scores
    
    def _align_two_documents(self, doc1: Dict[int, List[Token]], doc2: Dict[int, List[Token]], 
                           doc_indices: List[int]) -> AlignmentGrid:
        """Align two documents section by section using Needleman-Wunsch"""
        
        # Get common sections
        common_sections = set(doc1.keys()) & set(doc2.keys())
        alignment = AlignmentGrid(2)
        
        for section_id in sorted(common_sections):
            tokens1 = doc1[section_id]
            tokens2 = doc2[section_id]
            
            logger.debug(f"Aligning section {section_id}: {len(tokens1)} vs {len(tokens2)} tokens")
            
            # Needleman-Wunsch alignment for this section
            section_alignment = self._needleman_wunsch(tokens1, tokens2)
            
            # Add section alignment to grid
            for pos, (token1, token2) in enumerate(section_alignment):
                tokens = [token1, token2]
                alignment.add_column(tokens, section_id, pos)
        
        return alignment
    
    def _needleman_wunsch(self, seq1: List[Token], seq2: List[Token]) -> List[Tuple[Optional[Token], Optional[Token]]]:
        """
        Needleman-Wunsch alignment with legal document scoring
        
        Returns:
            List of aligned token pairs (token1, token2) with gaps as None
        """
        m, n = len(seq1), len(seq2)
        
        # Use banded alignment for efficiency
        band_width = max(ALIGN["BAND_MIN"], int(ALIGN["BAND_FRAC"] * min(m, n)))
        
        # Initialize scoring matrix
        dp = np.full((m + 1, n + 1), float('-inf'))
        dp[0, 0] = 0
        
        # Fill first row and column (gaps)
        for i in range(1, min(m + 1, band_width + 1)):
            dp[i, 0] = dp[i-1, 0] + ALIGN["GAP"]
        for j in range(1, min(n + 1, band_width + 1)):
            dp[0, j] = dp[0, j-1] + ALIGN["GAP"]
        
        # Fill DP matrix with banding
        for i in range(1, m + 1):
            j_start = max(1, i - band_width)
            j_end = min(n + 1, i + band_width + 1)
            
            for j in range(j_start, j_end):
                token1 = seq1[i-1]
                token2 = seq2[j-1]
                
                # Calculate match/mismatch score
                match_score = self._score_token_pair(token1, token2)
                
                # Three possible moves
                diagonal = dp[i-1, j-1] + match_score  # Match/mismatch
                up = dp[i-1, j] + ALIGN["GAP"]         # Gap in seq2
                left = dp[0, j-1] + ALIGN["GAP"]       # Gap in seq1
                
                dp[i, j] = max(diagonal, up, left)
        
        # Traceback to get alignment
        return self._traceback_alignment(dp, seq1, seq2)
    
    def _score_token_pair(self, token1: Token, token2: Token) -> int:
        """Score a pair of tokens for alignment"""
        if token1.text.lower() == token2.text.lower():
            return ALIGN["MATCH"]
        
        # Anchor mismatch penalty
        if token1.is_anchor or token2.is_anchor:
            if token1.is_anchor and token2.is_anchor and token1.type == token2.type:
                # Both anchors of same type - check fuzzy match
                if self._fuzzy_match(token1.text, token2.text):
                    return ALIGN["FUZZY"]
                else:
                    return ALIGN["ANCHOR_MISMATCH"]  # Critical mismatch
            elif token1.is_anchor != token2.is_anchor:
                return ALIGN["ANCHOR_MISMATCH"]  # One anchor, one not
        
        # Regular fuzzy match
        if self._fuzzy_match(token1.text, token2.text):
            return ALIGN["FUZZY"]
        
        return ALIGN["MISMATCH"]
    
    def _fuzzy_match(self, text1: str, text2: str) -> bool:
        """Check if two texts are fuzzy matches"""
        if not text1 or not text2:
            return False
        
        # Levenshtein distance check
        if self._levenshtein_distance(text1.lower(), text2.lower()) <= 2:
            return True
        
        # TODO: Add cosine similarity check if needed
        return False
    
    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Calculate Levenshtein distance between two strings"""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = list(range(len(s2) + 1))
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    def _traceback_alignment(self, dp: np.ndarray, seq1: List[Token], seq2: List[Token]) -> List[Tuple[Optional[Token], Optional[Token]]]:
        """Traceback through DP matrix to get optimal alignment"""
        alignment = []
        i, j = len(seq1), len(seq2)
        
        while i > 0 or j > 0:
            if i > 0 and j > 0:
                diagonal = dp[i-1, j-1] + self._score_token_pair(seq1[i-1], seq2[j-1])
                up = dp[i-1, j] + ALIGN["GAP"]
                left = dp[i, j-1] + ALIGN["GAP"]
                
                if dp[i, j] == diagonal:
                    alignment.append((seq1[i-1], seq2[j-1]))
                    i -= 1
                    j -= 1
                elif dp[i, j] == up:
                    alignment.append((seq1[i-1], None))
                    i -= 1
                else:
                    alignment.append((None, seq2[j-1]))
                    j -= 1
            elif i > 0:
                alignment.append((seq1[i-1], None))
                i -= 1
            else:
                alignment.append((None, seq2[j-1]))
                j -= 1
        
        return list(reversed(alignment))
    
    def _add_document_to_alignment(self, current_alignment: AlignmentGrid, new_doc: Dict[int, List[Token]], 
                                 doc_idx: int) -> AlignmentGrid:
        """Add a new document to existing alignment using profile alignment"""
        
        # Create new alignment grid with one more draft
        new_alignment = AlignmentGrid(current_alignment.num_drafts + 1)
        
        # For each section, align new document tokens with existing alignment
        for section_id in sorted(current_alignment.section_alignments.keys()):
            if section_id not in new_doc:
                logger.warning(f"Section {section_id} not found in new document {doc_idx+1}")
                continue
            
            existing_columns = current_alignment.get_section_alignment(section_id)
            new_tokens = new_doc[section_id]
            
            # Create profile from existing alignment
            profile_alignment = self._align_sequence_to_profile(new_tokens, existing_columns)
            
            # Add aligned columns to new grid
            for pos, (existing_column, new_token) in enumerate(profile_alignment):
                if existing_column is not None:
                    # Extend existing column with new token
                    extended_tokens = existing_column.tokens + [new_token]
                else:
                    # Create new column with gaps for existing drafts
                    extended_tokens = [None] * current_alignment.num_drafts + [new_token]
                
                new_alignment.add_column(extended_tokens, section_id, pos)
        
        return new_alignment
    
    def _align_sequence_to_profile(self, sequence: List[Token], profile: List[AlignmentColumn]) -> List[Tuple[Optional[AlignmentColumn], Optional[Token]]]:
        """Align a sequence to an existing alignment profile"""
        if not profile:
            return [(None, token) for token in sequence]
        
        # Simplified profile alignment - align to consensus of profile
        profile_consensus = []
        for column in profile:
            # Find most common non-gap token in column
            non_gap_tokens = [t for t in column.tokens if t is not None]
            if non_gap_tokens:
                # Use first non-gap token as representative
                profile_consensus.append(non_gap_tokens[0])
            else:
                profile_consensus.append(None)
        
        # Align sequence to consensus using Needleman-Wunsch
        consensus_alignment = self._align_to_consensus(sequence, profile_consensus)
        
        # Map back to profile columns
        result = []
        profile_idx = 0
        
        for seq_token, consensus_token in consensus_alignment:
            if consensus_token is not None:
                # Aligned to existing profile column
                result.append((profile[profile_idx], seq_token))
                profile_idx += 1
            else:
                # Gap in profile - new column needed
                result.append((None, seq_token))
        
        return result
    
    def _align_to_consensus(self, sequence: List[Token], consensus: List[Optional[Token]]) -> List[Tuple[Optional[Token], Optional[Token]]]:
        """Align sequence to consensus using simplified Needleman-Wunsch"""
        # Filter out None values from consensus for alignment
        filtered_consensus = [t for t in consensus if t is not None]
        
        if not filtered_consensus:
            return [(token, None) for token in sequence]
        
        # Use regular Needleman-Wunsch
        return self._needleman_wunsch(sequence, filtered_consensus)
    
    def _create_single_document_alignment(self, document: Dict[str, Any]) -> AlignmentGrid:
        """Create trivial alignment for single document"""
        sections = document.get("sections", [])
        tokenized_sections = self.tokenizer.tokenize_sections(sections)
        
        alignment = AlignmentGrid(1)
        
        for section_id in sorted(tokenized_sections.keys()):
            tokens = tokenized_sections[section_id]
            for pos, token in enumerate(tokens):
                alignment.add_column([token], section_id, pos)
        
        return alignment
