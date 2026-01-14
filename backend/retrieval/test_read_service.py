"""
Tests for Read-Mode Service
============================

Validates the locate→read bridge: lightweight evidence from lanes can be
expanded to full hydrated CorpusEntry.

Acceptance criteria for S3:
- Read-mode service takes evidence reference and returns full CorpusEntry
- Service is separate from lanes (keeps lanes as locators)
- Pytest demonstrates deterministic expansion of semantic results to full text
"""

import hashlib
from typing import Iterable, List, Optional, Set

import pytest

from corpus.interfaces import CorpusProvider
from corpus.types import (
    CorpusEntry,
    CorpusEntryKind,
    CorpusEntryRef,
    CorpusView,
)

from .evidence.models import EvidenceCard, EvidenceSpan
from .read_service import expand_evidence_to_entry, expand_span_to_entry


class StubCorpusProvider(CorpusProvider):
    """Stub corpus provider for testing."""

    def __init__(self, entries: List[CorpusEntry]):
        self.entries = entries

    def list_entry_refs(
        self,
        view: CorpusView,
        *,
        dossier_id: Optional[str] = None,
        kinds: Optional[Set[CorpusEntryKind]] = None,
    ) -> Iterable[CorpusEntryRef]:
        for entry in self.entries:
            if dossier_id and entry.ref.dossier_id != dossier_id:
                continue
            if entry.ref.view != view:
                continue
            if kinds and entry.ref.kind not in kinds:
                continue
            yield entry.ref

    def hydrate_entry(self, ref: CorpusEntryRef) -> CorpusEntry:
        for entry in self.entries:
            if entry.ref.entry_id == ref.entry_id:
                return entry
        raise ValueError(f"Entry not found: {ref.entry_id}")


def test_expand_evidence_card_to_full_entry():
    """
    Test that EvidenceCard can be expanded to full CorpusEntry.

    Acceptance criteria for S3:
    - Read-mode service takes evidence reference (EvidenceCard) and returns full CorpusEntry
    - Returned entry has non-empty text matching the original corpus entry
    """
    # Create synthetic corpus
    test_text = "This is the full text of a corpus entry that should be hydrated from evidence."
    ref = CorpusEntryRef(
        view=CorpusView.FINAL_SEGMENTS,
        entry_id="seg_read_test",
        kind=CorpusEntryKind.SEGMENT_FINAL_TEXT,
        dossier_id="test_dossier",
        segment_id="seg_001",
    )
    entry = CorpusEntry(
        ref=ref,
        text=test_text,
        content_hash=hashlib.sha256(test_text.encode()).hexdigest(),
    )

    corpus = StubCorpusProvider(entries=[entry])

    # Create evidence card (simulating what a lane would return)
    span = EvidenceSpan(
        entry=ref,
        text="",  # Lightweight locator has empty text
        preview="This is the full text...",  # Preview for triage
    )
    card = EvidenceCard(
        id="test_card",
        spans=[span],
        score=0.95,
        lane="semantic:test",
    )

    # Expand evidence to full entry
    hydrated_entry = expand_evidence_to_entry(card, corpus)

    # Verify hydration succeeded
    assert hydrated_entry is not None, "Hydration should succeed"
    assert hydrated_entry.text == test_text, "Hydrated text should match original"
    assert len(hydrated_entry.text) > 0, "Hydrated text should be non-empty"
    assert hydrated_entry.ref == ref, "Hydrated ref should match original"


def test_expand_evidence_span_to_full_entry():
    """
    Test that EvidenceSpan can be expanded to full CorpusEntry.

    This demonstrates the locate→read workflow for individual spans.
    """
    test_text = "Another full corpus entry text for span expansion testing."
    ref = CorpusEntryRef(
        view=CorpusView.FINAL_SEGMENTS,
        entry_id="seg_span_test",
        kind=CorpusEntryKind.SEGMENT_FINAL_TEXT,
        dossier_id="test_dossier",
    )
    entry = CorpusEntry(
        ref=ref,
        text=test_text,
        content_hash=hashlib.sha256(test_text.encode()).hexdigest(),
    )

    corpus = StubCorpusProvider(entries=[entry])

    # Create evidence span
    span = EvidenceSpan(
        entry=ref,
        text="",
        preview="Another full corpus entry...",
    )

    # Expand using the convenience wrapper
    hydrated_entry = expand_span_to_entry(span, corpus)

    assert hydrated_entry is not None
    assert hydrated_entry.text == test_text
    assert hydrated_entry.ref.entry_id == "seg_span_test"


def test_expand_evidence_missing_entry_returns_none():
    """
    Test that expansion returns None for non-existent entries.

    Safe failure mode: don't crash, return None.
    """
    # Empty corpus
    corpus = StubCorpusProvider(entries=[])

    # Evidence pointing to non-existent entry
    ref = CorpusEntryRef(
        view=CorpusView.FINAL_SEGMENTS,
        entry_id="nonexistent",
        kind=CorpusEntryKind.SEGMENT_FINAL_TEXT,
    )
    span = EvidenceSpan(entry=ref, text="")

    # Expansion should return None, not crash
    result = expand_span_to_entry(span, corpus)
    assert result is None, "Should return None for missing entry"


def test_expand_evidence_empty_card_returns_none():
    """
    Test that expansion handles edge cases gracefully.
    """
    corpus = StubCorpusProvider(entries=[])

    # Card with no spans
    card = EvidenceCard(
        id="empty_card",
        spans=[],
        score=0.0,
        lane="test",
    )

    result = expand_evidence_to_entry(card, corpus)
    assert result is None, "Should return None for empty card"


def test_read_service_is_separate_from_lanes():
    """
    Demonstrate that read service is architecturally separate from lanes.

    This test validates the design principle:
    - Lanes return lightweight evidence (locators)
    - Read service does heavy hydration when needed
    - Consumer controls when to pay hydration cost
    """
    test_text = "Full text that requires hydration."
    ref = CorpusEntryRef(
        view=CorpusView.FINAL_SEGMENTS,
        entry_id="sep_test",
        kind=CorpusEntryKind.SEGMENT_FINAL_TEXT,
    )
    entry = CorpusEntry(ref=ref, text=test_text)
    corpus = StubCorpusProvider(entries=[entry])

    # Step 1: Lane returns lightweight evidence (empty text, preview only)
    lightweight_span = EvidenceSpan(
        entry=ref,
        text="",  # Lightweight
        preview="Full text that requires...",  # Small preview for triage
    )

    # Verify lane output is lightweight
    assert lightweight_span.text == "", "Lane should return empty text"
    assert lightweight_span.preview is not None, "Lane should include preview"

    # Step 2: Read service hydrates when needed (separate operation)
    full_entry = expand_span_to_entry(lightweight_span, corpus)

    # Verify read service provides full hydration
    assert full_entry is not None
    assert full_entry.text == test_text, "Read service should return full text"
    assert len(full_entry.text) > len(lightweight_span.preview or "")
