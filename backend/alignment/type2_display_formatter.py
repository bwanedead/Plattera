"""
Type 2 Display Formatter
========================

COMPLETELY ISOLATED Type 2 formatting implementation.
Goal: Create formatted tokens for alignment table with consensus anchoring.

This formatter is COMPLETELY UNAWARE of Type 1 formatting and has NO DEPENDENCIES on it.
"""

from typing import Dict, List, Any, Optional, Set
from collections import defaultdict
from .format_mapping import FormatMapping
import logging

logger = logging.getLogger(__name__)


class Type2DisplayFormatter:
    """
    Type 2 Display Formatter - COMPLETELY ISOLATED
    
    Purpose: Create display tokens for Type 2 alignment table by applying consensus groupings
    to formatted tokens, ensuring that multi-token spans are properly anchored across drafts.
    """
    
    GAP = "-"
    
    def create_display_tokens(
        self,
        aligned_tokens: List[str],
        format_mapping: FormatMapping,
        original_to_alignment: List[int],
        consensus_group_sizes: List[int]
    ) -> List[str]:
        """
        Create display tokens for Type 2 alignment table.
        
        Args:
            aligned_tokens: The aligned normalized tokens for this draft
            format_mapping: Mapping from normalized tokens to original formatted tokens
            original_to_alignment: Mapping from original token indices to alignment positions
            consensus_group_sizes: Consensus grouping sizes that determine how to collapse rows
            
        Returns:
            List of formatted display tokens respecting consensus groupings
        """
        try:
            logger.info(f"Creating Type 2 display tokens for draft {format_mapping.draft_id}")
            
            # Step 1: Extract formatted tokens in alignment order
            formatted_tokens = self._extract_formatted_tokens(
                format_mapping, original_to_alignment, len(aligned_tokens)
            )
            
            logger.info(f"Extracted {len(formatted_tokens)} formatted tokens")
            
            # Step 2: Apply consensus groupings to collapse multi-token spans
            display_tokens = self._apply_consensus_grouping(formatted_tokens, consensus_group_sizes)
            
            logger.info(f"Applied consensus grouping: {len(formatted_tokens)} → {len(display_tokens)} tokens")
            
            return display_tokens
            
        except Exception as e:
            logger.error(f"Error creating Type 2 display tokens for {format_mapping.draft_id}: {e}")
            return [self.GAP] * len(consensus_group_sizes) if consensus_group_sizes else []
    
    def _extract_formatted_tokens(
        self,
        format_mapping: FormatMapping,
        original_to_alignment: List[int],
        alignment_length: int
    ) -> List[str]:
        """Extract formatted tokens in alignment order, filling gaps where needed."""
        
        # Create index mapping for quick lookup
        token_index_to_formatted = {
            tp.token_index: tp.original_text
            for tp in format_mapping.token_positions
        }
        
        # Build tokens in alignment order
        formatted_tokens = []
        for i, alignment_pos in enumerate(original_to_alignment):
            if i in token_index_to_formatted:
                formatted_tokens.append(token_index_to_formatted[i])
            else:
                formatted_tokens.append(self.GAP)
        
        return formatted_tokens
    
    def _apply_consensus_grouping(
        self,
        formatted_tokens: List[str],
        group_sizes: List[int]
    ) -> List[str]:
        """
        Apply consensus grouping to collapse multi-token spans.
        
        The key fix: validate by sum(group_sizes) == len(formatted_tokens),
        not len(group_sizes) == len(formatted_tokens).
        """
        if not group_sizes:
            logger.warning("No group sizes provided, returning original tokens")
            return formatted_tokens
            
        # FIXED: Check sum of group sizes, not length
        if sum(group_sizes) != len(formatted_tokens):
            logger.warning(
                f"⚠️ Group-size sum {sum(group_sizes)} ≠ token count {len(formatted_tokens)}")
            return formatted_tokens
        
        logger.info(f"Applying consensus grouping: {group_sizes}")
        
        display_tokens = []
        token_idx = 0
        
        for group_size in group_sizes:
            # Extract tokens for this group
            group_tokens = formatted_tokens[token_idx:token_idx + group_size]
            
            # Merge tokens for display (removes duplicates, joins with " | ")
            merged_token = self._merge_tokens_for_display(group_tokens)
            display_tokens.append(merged_token)
            
            token_idx += group_size
        
        return display_tokens
    
    def _merge_tokens_for_display(self, tokens: List[str]) -> str:
        """
        Merge all tokens that belong to the same consensus group.

        * Removes duplicates
        * Ignores bare gap markers ("-")
        * Uses simple space separation for clean display
        """
        # filter blanks / gaps
        uniq: List[str] = []
        seen = set()
        for t in tokens:
            if t and t != self.GAP and t not in seen:
                uniq.append(t)
                seen.add(t)

        if not uniq:                 # every draft was a gap here
            return self.GAP
        if len(uniq) == 1:           # single token
            return uniq[0]
        return " ".join(uniq)        # clean space-separated tokens


class Type2ConsensusAnalyzer:
    """
    Builds a single **group‑size vector** for every block.

    Algorithm (column‑by‑column):
        1.  For each draft, measure how far the SAME formatted token
            extends to the right of the current column.
        2.  Pick the *longest* such span – that draft is the
            "most‑reduced" at this position.
        3.  Record that span length as the next consensus group and
            skip over it.
    """

    GAP = "-"

    def compute_consensus_groupings(
        self,
        alignment_results: Dict[str, Any],
        format_mappings: Dict[str, Dict[str, FormatMapping]],
    ) -> Dict[str, Dict[str, List[int]]]:

        consensus: Dict[str, Dict[str, List[int]]] = {}

        for block_id, block_res in alignment_results.get("blocks", {}).items():
            seqs = block_res.get("aligned_sequences", [])
            if not seqs:
                continue

            align_len = block_res["alignment_length"]

            # ---- pre‑compute {draft ➜ [fmt_token | None] * align_len} ---- #
            per_draft_fmt: Dict[str, List[Optional[str]]] = {}
            for seq in seqs:
                draft_id = seq["draft_id"]
                fmt_map  = format_mappings.get(block_id, {}).get(draft_id)
                o2a      = seq["original_to_alignment"]

                # default None (= gap)
                fmt_list: List[Optional[str]] = [None] * align_len
                if fmt_map:
                    for tp in fmt_map.token_positions:
                        if tp.token_index < len(o2a):
                            col = o2a[tp.token_index]
                            if 0 <= col < align_len:
                                fmt_list[col] = tp.original_text
                per_draft_fmt[draft_id] = fmt_list

            # ---- build consensus group‑size list ---- #
            group_sizes: List[int] = []
            col = 0
            while col < align_len:
                max_span = 1
                for draft_id in per_draft_fmt:
                    token_here = per_draft_fmt[draft_id][col]
                    if not token_here:
                        continue
                    # how far to the right does this same token extend?
                    span = 1
                    while (col + span < align_len 
                           and per_draft_fmt[draft_id][col + span] == token_here):
                        span += 1
                    max_span = max(max_span, span)
                group_sizes.append(max_span)
                col += max_span

            # ---- assign the same group‑size list to every draft ---- #
            consensus[block_id] = {}
            for seq in seqs:
                consensus[block_id][seq["draft_id"]] = group_sizes

        return consensus
