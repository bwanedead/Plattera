"""
Deterministic Chunking System for Semantic Indexing
====================================================

Consumes hydrated corpus entries and emits stable chunk records suitable
for semantic indexing.

Key invariants:
- Prefers native structure (structured_json.sections[]) when present
- Falls back deterministically to paragraph/window chunking
- Produces stable chunk IDs derived only from stable inputs (no paths/timestamps)
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from corpus.types import CorpusEntry, CorpusEntryRef


# -----------------------------------------------------------------------------
# Canonical JSON helper (hashing-safe)
# -----------------------------------------------------------------------------


def canonical_json(obj: Any) -> str:
    """
    Serialize object to canonical JSON for stable hashing.

    Uses sorted keys and compact separators to ensure identical output
    for semantically identical objects across runs.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# -----------------------------------------------------------------------------
# Chunking types
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class ChunkSelector:
    """
    Identifies a chunk's position within its parent entry.

    Must be canonical-JSON serializable for stable chunk ID generation.

    Selector kinds:
    - section: chunk from a structured section (uses section_id or section_index)
    - section_window: subdivision of an oversized section
    - paragraph: chunk from paragraph-based fallback
    - window: subdivision of an oversized paragraph
    """

    kind: str
    section_id: Optional[str] = None
    section_index: Optional[int] = None
    window_index: Optional[int] = None
    paragraph_index: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for canonical JSON serialization."""
        d: Dict[str, Any] = {"kind": self.kind}
        if self.section_id is not None:
            d["section_id"] = self.section_id
        if self.section_index is not None:
            d["section_index"] = self.section_index
        if self.window_index is not None:
            d["window_index"] = self.window_index
        if self.paragraph_index is not None:
            d["paragraph_index"] = self.paragraph_index
        return d


@dataclass(frozen=True)
class ChunkPolicy:
    """
    Configuration for chunking behavior.

    Attributes:
        policy_id: Unique identifier for this policy version (e.g., "final_segments_v1")
        max_chars_per_chunk: Maximum characters per chunk before splitting
        overlap_chars: Character overlap between consecutive windows
        min_chars: Minimum characters for a chunk (smaller chunks may be merged)
        merge_small_paragraphs: Whether to merge small paragraphs into larger chunks
        oversize_section_split: Whether to split oversized sections into windows
    """

    policy_id: str
    max_chars_per_chunk: int = 2000
    overlap_chars: int = 200
    min_chars: int = 120
    merge_small_paragraphs: bool = True
    oversize_section_split: bool = True


# Default policy for Pool A (FINAL_SEGMENTS)
FINAL_SEGMENTS_POLICY = ChunkPolicy(
    policy_id="final_segments_v1",
    max_chars_per_chunk=2000,
    overlap_chars=200,
    min_chars=120,
    merge_small_paragraphs=True,
    oversize_section_split=True,
)


@dataclass(frozen=True)
class CorpusChunk:
    """
    A chunk of text from a corpus entry, ready for embedding.

    Attributes:
        chunk_id: Stable hash-based identifier
        entry_ref: Reference to the parent corpus entry
        parent_content_hash: Content hash of the parent entry (for version tracking)
        selector: Position/identity of this chunk within the parent
        text: The actual chunk text
        snippet_hint: Optional short preview for evidence cards
        title_hint: Optional title for evidence cards
    """

    chunk_id: str
    entry_ref: CorpusEntryRef
    parent_content_hash: Optional[str]
    selector: ChunkSelector
    text: str
    snippet_hint: Optional[str] = None
    title_hint: Optional[str] = None


# -----------------------------------------------------------------------------
# Chunk ID construction
# -----------------------------------------------------------------------------


def compute_chunk_id(
    entry_ref: CorpusEntryRef,
    content_hash: Optional[str],
    policy_id: str,
    selector: ChunkSelector,
) -> str:
    """
    Compute a stable chunk ID from deterministic inputs only.

    Formula: sha256(entry_id | content_hash | policy_id | canonical_json(selector))
    """
    parts = [
        entry_ref.entry_id,
        content_hash or "",
        policy_id,
        canonical_json(selector.to_dict()),
    ]
    combined = "|".join(parts)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


# -----------------------------------------------------------------------------
# Chunker implementation
# -----------------------------------------------------------------------------


class Chunker:
    """
    Deterministic chunker for corpus entries.

    Strategy order:
    1. Sections strategy: if structured_json.sections[] exists, chunk from that
    2. Fallback strategy: paragraph/window chunking from entry.text
    """

    def chunk_entry(self, entry: CorpusEntry, policy: ChunkPolicy) -> List[CorpusChunk]:
        """
        Chunk a corpus entry according to the given policy.

        Args:
            entry: Hydrated corpus entry to chunk
            policy: Chunking policy configuration

        Returns:
            List of CorpusChunk objects with stable IDs
        """
        # Try sections-first strategy
        sections = self._extract_sections(entry)
        if sections:
            return self._chunk_from_sections(entry, sections, policy)

        # Fallback to paragraph/window chunking
        text = entry.text or ""
        if not text.strip():
            return []

        return self._chunk_from_text(entry, text, policy)

    def _extract_sections(self, entry: CorpusEntry) -> Optional[List[Dict[str, Any]]]:
        """
        Extract sections from structured_json if present and valid.

        Returns None if no usable sections found.
        """
        if not entry.structured_json:
            return None

        sections = entry.structured_json.get("sections")
        if not isinstance(sections, list) or not sections:
            return None

        # Validate that at least one section has body content
        for s in sections:
            if isinstance(s, dict) and s.get("body"):
                return sections

        return None

    def _chunk_from_sections(
        self,
        entry: CorpusEntry,
        sections: List[Dict[str, Any]],
        policy: ChunkPolicy,
    ) -> List[CorpusChunk]:
        """
        Chunk from structured sections.

        Each section becomes one or more chunks depending on size.
        """
        chunks: List[CorpusChunk] = []

        for idx, section in enumerate(sections):
            if not isinstance(section, dict):
                continue

            body = section.get("body")
            if not isinstance(body, str) or not body.strip():
                continue

            section_id_raw = section.get("id") or section.get("section_id")
            section_id = str(section_id_raw) if section_id_raw is not None else None
            header = section.get("header") or section.get("title")

            # Check if section needs splitting
            if len(body) <= policy.max_chars_per_chunk:
                # Single section chunk
                selector = ChunkSelector(
                    kind="section",
                    section_id=section_id,
                    section_index=idx,
                )
                chunk_id = compute_chunk_id(
                    entry.ref, entry.content_hash, policy.policy_id, selector
                )
                chunks.append(
                    CorpusChunk(
                        chunk_id=chunk_id,
                        entry_ref=entry.ref,
                        parent_content_hash=entry.content_hash,
                        selector=selector,
                        text=body.strip(),
                        snippet_hint=body[:200].strip() if len(body) > 200 else None,
                        title_hint=header,
                    )
                )
            elif policy.oversize_section_split:
                # Split into windows
                windows = self._split_into_windows(
                    body, policy.max_chars_per_chunk, policy.overlap_chars
                )
                for win_idx, window_text in enumerate(windows):
                    selector = ChunkSelector(
                        kind="section_window",
                        section_id=section_id,
                        section_index=idx,
                        window_index=win_idx,
                    )
                    chunk_id = compute_chunk_id(
                        entry.ref, entry.content_hash, policy.policy_id, selector
                    )
                    chunks.append(
                        CorpusChunk(
                            chunk_id=chunk_id,
                            entry_ref=entry.ref,
                            parent_content_hash=entry.content_hash,
                            selector=selector,
                            text=window_text.strip(),
                            snippet_hint=window_text[:200].strip() if len(window_text) > 200 else None,
                            title_hint=f"{header} (part {win_idx + 1})" if header else None,
                        )
                    )
            else:
                # No splitting allowed, emit oversized chunk as-is
                selector = ChunkSelector(
                    kind="section",
                    section_id=section_id,
                    section_index=idx,
                )
                chunk_id = compute_chunk_id(
                    entry.ref, entry.content_hash, policy.policy_id, selector
                )
                chunks.append(
                    CorpusChunk(
                        chunk_id=chunk_id,
                        entry_ref=entry.ref,
                        parent_content_hash=entry.content_hash,
                        selector=selector,
                        text=body.strip(),
                        snippet_hint=body[:200].strip() if len(body) > 200 else None,
                        title_hint=header,
                    )
                )

        return chunks

    def _chunk_from_text(
        self,
        entry: CorpusEntry,
        text: str,
        policy: ChunkPolicy,
    ) -> List[CorpusChunk]:
        """
        Fallback chunking from plain text.

        Strategy:
        1. Split into paragraphs (double-newline boundaries)
        2. Optionally merge small paragraphs
        3. Split oversized paragraphs into windows
        """
        # Split into paragraphs
        paragraphs = self._split_into_paragraphs(text)

        # Filter empty paragraphs
        paragraphs = [p for p in paragraphs if p.strip()]

        if not paragraphs:
            return []

        # Optionally merge small paragraphs
        if policy.merge_small_paragraphs:
            paragraphs = self._merge_small_paragraphs(paragraphs, policy.min_chars)

        # Generate chunks
        chunks: List[CorpusChunk] = []
        para_idx = 0

        for para in paragraphs:
            if not para.strip():
                continue

            if len(para) <= policy.max_chars_per_chunk:
                # Single paragraph chunk
                selector = ChunkSelector(
                    kind="paragraph",
                    paragraph_index=para_idx,
                )
                chunk_id = compute_chunk_id(
                    entry.ref, entry.content_hash, policy.policy_id, selector
                )
                chunks.append(
                    CorpusChunk(
                        chunk_id=chunk_id,
                        entry_ref=entry.ref,
                        parent_content_hash=entry.content_hash,
                        selector=selector,
                        text=para.strip(),
                        snippet_hint=para[:200].strip() if len(para) > 200 else None,
                        title_hint=entry.title,
                    )
                )
                para_idx += 1
            else:
                # Split paragraph into windows
                windows = self._split_into_windows(
                    para, policy.max_chars_per_chunk, policy.overlap_chars
                )
                for win_idx, window_text in enumerate(windows):
                    if not window_text.strip():
                        continue
                    selector = ChunkSelector(
                        kind="window",
                        paragraph_index=para_idx,
                        window_index=win_idx,
                    )
                    chunk_id = compute_chunk_id(
                        entry.ref, entry.content_hash, policy.policy_id, selector
                    )
                    chunks.append(
                        CorpusChunk(
                            chunk_id=chunk_id,
                            entry_ref=entry.ref,
                            parent_content_hash=entry.content_hash,
                            selector=selector,
                            text=window_text.strip(),
                            snippet_hint=window_text[:200].strip() if len(window_text) > 200 else None,
                            title_hint=entry.title,
                        )
                    )
                para_idx += 1

        return chunks

    def _split_into_paragraphs(self, text: str) -> List[str]:
        """
        Split text into paragraphs on double-newline boundaries.

        Deterministic: uses regex split on blank lines.
        """
        # Split on one or more blank lines (double newline with optional whitespace)
        return re.split(r"\n\s*\n", text)

    def _merge_small_paragraphs(
        self, paragraphs: List[str], min_chars: int
    ) -> List[str]:
        """
        Merge paragraphs smaller than min_chars into the next paragraph.

        Deterministic: processes in order, merging forward.
        """
        if not paragraphs:
            return []

        merged: List[str] = []
        buffer = ""

        for para in paragraphs:
            if buffer:
                # Append to buffer
                buffer = buffer + "\n\n" + para
            else:
                buffer = para

            # Check if buffer is large enough to emit
            if len(buffer) >= min_chars:
                merged.append(buffer)
                buffer = ""

        # Don't lose trailing buffer
        if buffer.strip():
            if merged:
                # Merge with last paragraph if buffer is too small
                merged[-1] = merged[-1] + "\n\n" + buffer
            else:
                merged.append(buffer)

        return merged

    def _split_into_windows(
        self, text: str, max_chars: int, overlap_chars: int
    ) -> List[str]:
        """
        Split text into overlapping windows of approximately max_chars.

        Deterministic: character-based windowing with fixed overlap.
        Tries to break on word boundaries when possible.
        """
        if len(text) <= max_chars:
            return [text]

        windows: List[str] = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = min(start + max_chars, text_len)

            # Try to break on word boundary if not at end
            if end < text_len:
                # Look for last space within the window
                last_space = text.rfind(" ", start, end)
                if last_space > start + (max_chars // 2):
                    # Found a reasonable break point
                    end = last_space

            window = text[start:end]
            if window.strip():
                windows.append(window)

            # Move start forward, accounting for overlap
            if end >= text_len:
                break

            # Next window starts overlap_chars before end
            prev_start = start
            start = end - overlap_chars
            if start <= prev_start:
                # Avoid infinite loop if overlap is larger than progress
                start = end

        return windows


# Module-level singleton for convenience
_default_chunker = Chunker()


def chunk_entry(entry: CorpusEntry, policy: ChunkPolicy) -> List[CorpusChunk]:
    """
    Chunk a corpus entry using the default chunker.

    Convenience function wrapping Chunker.chunk_entry().
    """
    return _default_chunker.chunk_entry(entry, policy)
