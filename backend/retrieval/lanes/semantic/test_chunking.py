"""
Deterministic tests for the chunking system.

These tests verify:
1. Determinism: same entry + policy => identical chunk_ids
2. Version-awareness: different content_hash => different chunk_ids
3. Sections-first: entries with sections use section strategy
4. Oversize section splitting: produces section_window chunks
5. Fallback chunking: entries without sections use paragraph/window

Run with:
    python -m retrieval.lanes.semantic.test_chunking
"""

from __future__ import annotations

from corpus.types import CorpusEntry, CorpusEntryKind, CorpusEntryRef, CorpusView

from .chunking import (
    FINAL_SEGMENTS_POLICY,
    ChunkPolicy,
    ChunkSelector,
    Chunker,
    canonical_json,
    chunk_entry,
    compute_chunk_id,
)


def _make_entry_ref(entry_id: str = "test:entry:001") -> CorpusEntryRef:
    """Helper to create a test entry ref."""
    return CorpusEntryRef(
        view=CorpusView.FINAL_SEGMENTS,
        entry_id=entry_id,
        kind=CorpusEntryKind.SEGMENT_FINAL_TEXT,
        dossier_id="test_dossier",
        segment_id="seg_001",
        draft_id="draft_001",
    )


def _make_entry(
    entry_id: str = "test:entry:001",
    text: str = "",
    content_hash: str = "abc123hash",
    structured_json: dict | None = None,
    title: str | None = None,
) -> CorpusEntry:
    """Helper to create a test corpus entry."""
    return CorpusEntry(
        ref=_make_entry_ref(entry_id),
        text=text,
        content_hash=content_hash,
        structured_json=structured_json,
        title=title,
        provenance={"source": "test"},
    )


# -----------------------------------------------------------------------------
# Test: canonical_json produces stable output
# -----------------------------------------------------------------------------


def test_canonical_json_stability() -> None:
    """canonical_json produces identical output for equivalent objects."""
    obj1 = {"z": 1, "a": 2, "m": {"b": 3, "a": 4}}
    obj2 = {"a": 2, "m": {"a": 4, "b": 3}, "z": 1}

    result1 = canonical_json(obj1)
    result2 = canonical_json(obj2)

    assert result1 == result2, "canonical_json should produce identical output for equivalent dicts"
    # Verify sorted keys
    assert '"a":2' in result1
    assert '"z":1' in result1


# -----------------------------------------------------------------------------
# Test: Determinism - same entry + policy => identical chunk_ids
# -----------------------------------------------------------------------------


def test_determinism_same_entry_same_chunks() -> None:
    """Same entry + same policy produces identical chunk_ids across runs."""
    entry = _make_entry(
        text="First paragraph here.\n\nSecond paragraph here.",
        content_hash="hash_v1",
    )
    policy = FINAL_SEGMENTS_POLICY

    chunker = Chunker()
    chunks_run1 = chunker.chunk_entry(entry, policy)
    chunks_run2 = chunker.chunk_entry(entry, policy)

    assert len(chunks_run1) == len(chunks_run2), "Same number of chunks"
    for c1, c2 in zip(chunks_run1, chunks_run2):
        assert c1.chunk_id == c2.chunk_id, "chunk_id must be identical"
        assert c1.selector == c2.selector, "selector must be identical"
        assert c1.text == c2.text, "text must be identical"


def test_determinism_with_sections() -> None:
    """Entries with sections produce identical chunks across runs."""
    entry = _make_entry(
        structured_json={
            "sections": [
                {"id": "sec_1", "header": "Introduction", "body": "This is the intro."},
                {"id": "sec_2", "header": "Details", "body": "These are the details."},
            ]
        },
        content_hash="hash_sections",
    )
    policy = FINAL_SEGMENTS_POLICY

    chunks_run1 = chunk_entry(entry, policy)
    chunks_run2 = chunk_entry(entry, policy)

    assert len(chunks_run1) == 2
    assert len(chunks_run2) == 2
    for c1, c2 in zip(chunks_run1, chunks_run2):
        assert c1.chunk_id == c2.chunk_id


# -----------------------------------------------------------------------------
# Test: Version-awareness - different content_hash => different chunk_ids
# -----------------------------------------------------------------------------


def test_version_awareness_different_hash() -> None:
    """Different content_hash produces different chunk_ids."""
    entry_v1 = _make_entry(
        text="Same text content.",
        content_hash="hash_version_1",
    )
    entry_v2 = _make_entry(
        text="Same text content.",
        content_hash="hash_version_2",
    )
    policy = FINAL_SEGMENTS_POLICY

    chunks_v1 = chunk_entry(entry_v1, policy)
    chunks_v2 = chunk_entry(entry_v2, policy)

    assert len(chunks_v1) == len(chunks_v2) == 1
    assert chunks_v1[0].chunk_id != chunks_v2[0].chunk_id, "Different content_hash => different chunk_id"
    assert chunks_v1[0].parent_content_hash == "hash_version_1"
    assert chunks_v2[0].parent_content_hash == "hash_version_2"


def test_version_awareness_different_policy() -> None:
    """Different policy_id produces different chunk_ids."""
    entry = _make_entry(
        text="Some text content.",
        content_hash="hash_fixed",
    )
    policy_v1 = ChunkPolicy(policy_id="policy_v1")
    policy_v2 = ChunkPolicy(policy_id="policy_v2")

    chunks_v1 = chunk_entry(entry, policy_v1)
    chunks_v2 = chunk_entry(entry, policy_v2)

    assert len(chunks_v1) == len(chunks_v2) == 1
    assert chunks_v1[0].chunk_id != chunks_v2[0].chunk_id, "Different policy_id => different chunk_id"


# -----------------------------------------------------------------------------
# Test: Sections-first strategy
# -----------------------------------------------------------------------------


def test_sections_first_prefers_structured_json() -> None:
    """Entries with structured_json.sections use section strategy, not text fallback."""
    entry = _make_entry(
        text="This text should be ignored when sections exist.",
        structured_json={
            "sections": [
                {"id": "sec_A", "header": "Header A", "body": "Body content A."},
            ]
        },
        content_hash="hash_sections_first",
    )
    policy = FINAL_SEGMENTS_POLICY

    chunks = chunk_entry(entry, policy)

    assert len(chunks) == 1
    assert chunks[0].selector.kind == "section"
    assert chunks[0].selector.section_id == "sec_A"
    assert chunks[0].selector.section_index == 0
    assert chunks[0].text == "Body content A."
    assert chunks[0].title_hint == "Header A"


def test_sections_uses_index_when_no_id() -> None:
    """Sections without id use section_index for identification."""
    entry = _make_entry(
        structured_json={
            "sections": [
                {"header": "First", "body": "First body."},
                {"header": "Second", "body": "Second body."},
            ]
        },
        content_hash="hash_no_id",
    )
    policy = FINAL_SEGMENTS_POLICY

    chunks = chunk_entry(entry, policy)

    assert len(chunks) == 2
    assert chunks[0].selector.section_id is None
    assert chunks[0].selector.section_index == 0
    assert chunks[1].selector.section_index == 1


def test_sections_skips_empty_bodies() -> None:
    """Sections with empty/missing bodies are skipped."""
    entry = _make_entry(
        structured_json={
            "sections": [
                {"id": "sec_1", "body": "Valid content."},
                {"id": "sec_2", "body": ""},  # Empty
                {"id": "sec_3", "body": "   "},  # Whitespace only
                {"id": "sec_4"},  # Missing body
                {"id": "sec_5", "body": "Also valid."},
            ]
        },
        content_hash="hash_skip_empty",
    )
    policy = FINAL_SEGMENTS_POLICY

    chunks = chunk_entry(entry, policy)

    assert len(chunks) == 2
    assert chunks[0].selector.section_id == "sec_1"
    assert chunks[1].selector.section_id == "sec_5"


# -----------------------------------------------------------------------------
# Test: Oversize section splitting
# -----------------------------------------------------------------------------


def test_oversize_section_produces_windows() -> None:
    """Oversized sections are split into section_window chunks."""
    # Create a section larger than max_chars
    large_body = "Word " * 600  # ~3000 chars
    entry = _make_entry(
        structured_json={
            "sections": [
                {"id": "large_sec", "header": "Large Section", "body": large_body},
            ]
        },
        content_hash="hash_large",
    )
    policy = ChunkPolicy(
        policy_id="test_split",
        max_chars_per_chunk=1000,
        overlap_chars=100,
        oversize_section_split=True,
    )

    chunks = chunk_entry(entry, policy)

    assert len(chunks) >= 2, "Large section should produce multiple windows"
    for i, chunk in enumerate(chunks):
        assert chunk.selector.kind == "section_window"
        assert chunk.selector.section_id == "large_sec"
        assert chunk.selector.section_index == 0
        assert chunk.selector.window_index == i
        assert len(chunk.text) <= policy.max_chars_per_chunk + 50  # Allow some slack for word boundaries


def test_oversize_section_windows_have_unique_ids() -> None:
    """Each window from an oversized section has a unique chunk_id."""
    large_body = "Content " * 500
    entry = _make_entry(
        structured_json={
            "sections": [{"id": "big", "body": large_body}]
        },
        content_hash="hash_unique_windows",
    )
    policy = ChunkPolicy(
        policy_id="test_unique",
        max_chars_per_chunk=800,
        overlap_chars=80,
    )

    chunks = chunk_entry(entry, policy)

    chunk_ids = [c.chunk_id for c in chunks]
    assert len(chunk_ids) == len(set(chunk_ids)), "All window chunk_ids must be unique"


def test_oversize_section_splitting_disabled() -> None:
    """When oversize_section_split=False, large sections are not split."""
    large_body = "Word " * 600
    entry = _make_entry(
        structured_json={
            "sections": [{"id": "large", "body": large_body}]
        },
        content_hash="hash_no_split",
    )
    policy = ChunkPolicy(
        policy_id="no_split",
        max_chars_per_chunk=1000,
        oversize_section_split=False,
    )

    chunks = chunk_entry(entry, policy)

    assert len(chunks) == 1
    assert chunks[0].selector.kind == "section"
    assert len(chunks[0].text) > policy.max_chars_per_chunk


# -----------------------------------------------------------------------------
# Test: Fallback paragraph/window chunking
# -----------------------------------------------------------------------------


def test_fallback_when_no_sections() -> None:
    """Entries without sections fall back to paragraph chunking."""
    entry = _make_entry(
        text="First paragraph.\n\nSecond paragraph.\n\nThird paragraph.",
        structured_json=None,
        content_hash="hash_fallback",
    )
    policy = ChunkPolicy(
        policy_id="fallback_test",
        min_chars=10,
        merge_small_paragraphs=False,
    )

    chunks = chunk_entry(entry, policy)

    assert len(chunks) == 3
    for i, chunk in enumerate(chunks):
        assert chunk.selector.kind == "paragraph"
        assert chunk.selector.paragraph_index == i


def test_fallback_merges_small_paragraphs() -> None:
    """Small paragraphs are merged when merge_small_paragraphs=True."""
    entry = _make_entry(
        text="Tiny.\n\nAlso tiny.\n\nThis one is definitely long enough to stand alone.",
        content_hash="hash_merge",
    )
    policy = ChunkPolicy(
        policy_id="merge_test",
        min_chars=50,
        merge_small_paragraphs=True,
    )

    chunks = chunk_entry(entry, policy)

    # First two tiny paragraphs should be merged
    assert len(chunks) <= 2


def test_fallback_splits_large_paragraphs() -> None:
    """Large paragraphs are split into windows."""
    large_para = "Word " * 600
    entry = _make_entry(
        text=large_para,
        content_hash="hash_large_para",
    )
    policy = ChunkPolicy(
        policy_id="split_para",
        max_chars_per_chunk=1000,
        overlap_chars=100,
    )

    chunks = chunk_entry(entry, policy)

    assert len(chunks) >= 2
    for i, chunk in enumerate(chunks):
        assert chunk.selector.kind == "window"
        assert chunk.selector.paragraph_index == 0
        assert chunk.selector.window_index == i


def test_fallback_no_empty_chunks() -> None:
    """Fallback chunking never produces empty/whitespace-only chunks."""
    entry = _make_entry(
        text="\n\n  \n\nActual content.\n\n   \n\nMore content.\n\n",
        content_hash="hash_no_empty",
    )
    policy = FINAL_SEGMENTS_POLICY

    chunks = chunk_entry(entry, policy)

    for chunk in chunks:
        assert chunk.text.strip(), "No empty chunks allowed"


def test_fallback_empty_text_no_chunks() -> None:
    """Empty text produces no chunks."""
    entry = _make_entry(
        text="",
        content_hash="hash_empty",
    )

    chunks = chunk_entry(entry, FINAL_SEGMENTS_POLICY)

    assert len(chunks) == 0


def test_fallback_whitespace_only_no_chunks() -> None:
    """Whitespace-only text produces no chunks."""
    entry = _make_entry(
        text="   \n\n   \t\t  ",
        content_hash="hash_whitespace",
    )

    chunks = chunk_entry(entry, FINAL_SEGMENTS_POLICY)

    assert len(chunks) == 0


# -----------------------------------------------------------------------------
# Test: Chunk ID construction
# -----------------------------------------------------------------------------


def test_chunk_id_uses_all_components() -> None:
    """chunk_id changes when any input component changes."""
    ref = _make_entry_ref("entry:base")
    selector = ChunkSelector(kind="section", section_index=0)

    id_base = compute_chunk_id(ref, "hash_a", "policy_a", selector)

    # Different content_hash
    id_diff_hash = compute_chunk_id(ref, "hash_b", "policy_a", selector)
    assert id_base != id_diff_hash

    # Different policy_id
    id_diff_policy = compute_chunk_id(ref, "hash_a", "policy_b", selector)
    assert id_base != id_diff_policy

    # Different selector
    selector2 = ChunkSelector(kind="section", section_index=1)
    id_diff_selector = compute_chunk_id(ref, "hash_a", "policy_a", selector2)
    assert id_base != id_diff_selector

    # Different entry_id
    ref2 = _make_entry_ref("entry:other")
    id_diff_entry = compute_chunk_id(ref2, "hash_a", "policy_a", selector)
    assert id_base != id_diff_entry


def test_chunk_id_stable_across_calls() -> None:
    """Same inputs produce same chunk_id across multiple calls."""
    ref = _make_entry_ref("stable:test")
    selector = ChunkSelector(kind="paragraph", paragraph_index=5)

    ids = [
        compute_chunk_id(ref, "stable_hash", "stable_policy", selector)
        for _ in range(10)
    ]

    assert len(set(ids)) == 1, "All IDs should be identical"


# -----------------------------------------------------------------------------
# Test: Entry ref and content hash propagation
# -----------------------------------------------------------------------------


def test_chunks_include_entry_ref() -> None:
    """Every chunk includes the parent entry_ref."""
    entry = _make_entry(
        entry_id="propagation:test",
        text="Some content here.",
        content_hash="hash_prop",
    )

    chunks = chunk_entry(entry, FINAL_SEGMENTS_POLICY)

    assert len(chunks) >= 1
    for chunk in chunks:
        assert chunk.entry_ref == entry.ref
        assert chunk.entry_ref.entry_id == "propagation:test"


def test_chunks_include_content_hash() -> None:
    """Every chunk includes the parent content_hash."""
    entry = _make_entry(
        text="Content for hash test.",
        content_hash="parent_hash_123",
    )

    chunks = chunk_entry(entry, FINAL_SEGMENTS_POLICY)

    for chunk in chunks:
        assert chunk.parent_content_hash == "parent_hash_123"


# -----------------------------------------------------------------------------
# Integration test: real FINAL_SEGMENTS hydration → chunking
# -----------------------------------------------------------------------------


def test_integration_final_segments_hydration_to_chunking() -> None:
    """
    Integration test: enumerate → hydrate → chunk with real FINAL_SEGMENTS view.

    Verifies that the chunker's sections-first strategy actually triggers
    for real hydrated entries (catches mismatch between draft storage format
    and what chunker expects).
    """
    import json
    import tempfile
    from pathlib import Path

    import config.paths as paths_mod
    from corpus.hydrate import CorpusHydrator
    from corpus.virtual_provider import VirtualCorpusProvider

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Patch paths to point at temp tree
        original_dossiers_root = paths_mod.dossiers_root
        original_dossiers_state_root = paths_mod.dossiers_state_root
        original_dossiers_management_root = paths_mod.dossiers_management_root
        original_dossiers_views_root = paths_mod.dossiers_views_root

        def _patched_dossiers_root() -> Path:
            return root / "dossiers_data"

        def _patched_dossiers_state_root() -> Path:
            return root / "dossiers_data" / "state"

        def _patched_dossiers_management_root() -> Path:
            return root / "dossiers_data" / "management"

        def _patched_dossiers_views_root() -> Path:
            return root / "dossiers_data" / "views" / "transcriptions"

        paths_mod.dossiers_root = _patched_dossiers_root  # type: ignore[assignment]
        paths_mod.dossiers_state_root = _patched_dossiers_state_root  # type: ignore[assignment]
        paths_mod.dossiers_management_root = _patched_dossiers_management_root  # type: ignore[assignment]
        paths_mod.dossiers_views_root = _patched_dossiers_views_root  # type: ignore[assignment]

        try:
            dossier_id = "D_INTEGRATION_TEST"
            draft_id = "T1"

            # Create management file so dossier is enumerable
            mgmt_dir = _patched_dossiers_management_root()
            mgmt_dir.mkdir(parents=True, exist_ok=True)
            (mgmt_dir / f"dossier_{dossier_id}.json").write_text(
                json.dumps({"id": dossier_id}), encoding="utf-8"
            )

            # Create final_registry.json with one segment
            state_dir = _patched_dossiers_state_root() / dossier_id
            state_dir.mkdir(parents=True, exist_ok=True)
            registry = {
                "segments": {
                    "seg_001": {
                        "transcription_id": draft_id,
                        "draft_id": draft_id,
                        "set_at": "2024-01-01T00:00:00Z",
                        "set_by": "test_user",
                    }
                },
                "_version": 1,
            }
            (state_dir / "final_registry.json").write_text(
                json.dumps(registry), encoding="utf-8"
            )

            # Create draft file with sections[] (the real format)
            draft_dir = _patched_dossiers_views_root() / dossier_id / draft_id / "raw"
            draft_dir.mkdir(parents=True, exist_ok=True)
            draft_payload = {
                "sections": [
                    {"id": 1, "header": "Introduction", "body": "This is the introduction section with real content."},
                    {"id": 2, "header": "Details", "body": "These are the details of the document."},
                    {"id": "sec_3", "header": "Conclusion", "body": "Final thoughts and conclusion."},
                ],
                "title": "Integration Test Draft",
                "saved_at": "2024-01-02T00:00:00Z",
            }
            (draft_dir / f"{draft_id}.json").write_text(
                json.dumps(draft_payload), encoding="utf-8"
            )

            # Enumerate from FINAL_SEGMENTS view
            provider = VirtualCorpusProvider()
            refs = list(provider.list_entry_refs(CorpusView.FINAL_SEGMENTS))

            assert len(refs) >= 1, "Expected at least 1 ref from FINAL_SEGMENTS"
            ref = refs[0]
            assert ref.dossier_id == dossier_id

            # Hydrate the entry
            hydrator = CorpusHydrator()
            entry = hydrator.hydrate(ref)

            assert entry.text != "", "Hydrated entry should have text"
            assert entry.structured_json is not None, "Hydrated entry should have structured_json"
            assert "sections" in entry.structured_json, "structured_json should contain sections"

            # Chunk the hydrated entry
            chunks = chunk_entry(entry, FINAL_SEGMENTS_POLICY)

            # Verify sections-first strategy triggered
            assert len(chunks) == 3, f"Expected 3 section chunks, got {len(chunks)}"

            for chunk in chunks:
                assert chunk.selector.kind == "section", (
                    f"Expected 'section' kind for sections-first, got '{chunk.selector.kind}'"
                )
                assert chunk.entry_ref == ref
                assert chunk.parent_content_hash == entry.content_hash

            # Verify section_id coercion to string (id=1 becomes "1")
            section_ids = [c.selector.section_id for c in chunks]
            assert "1" in section_ids, "Integer section id should be coerced to string"
            assert "2" in section_ids
            assert "sec_3" in section_ids

            # Verify text extraction
            assert "introduction section" in chunks[0].text.lower()
            assert "details" in chunks[1].text.lower()
            assert "conclusion" in chunks[2].text.lower()

        finally:
            paths_mod.dossiers_root = original_dossiers_root  # type: ignore[assignment]
            paths_mod.dossiers_state_root = original_dossiers_state_root  # type: ignore[assignment]
            paths_mod.dossiers_management_root = original_dossiers_management_root  # type: ignore[assignment]
            paths_mod.dossiers_views_root = original_dossiers_views_root  # type: ignore[assignment]


# -----------------------------------------------------------------------------
# Run tests
# -----------------------------------------------------------------------------


if __name__ == "__main__":
    test_canonical_json_stability()
    test_determinism_same_entry_same_chunks()
    test_determinism_with_sections()
    test_version_awareness_different_hash()
    test_version_awareness_different_policy()
    test_sections_first_prefers_structured_json()
    test_sections_uses_index_when_no_id()
    test_sections_skips_empty_bodies()
    test_oversize_section_produces_windows()
    test_oversize_section_windows_have_unique_ids()
    test_oversize_section_splitting_disabled()
    test_fallback_when_no_sections()
    test_fallback_merges_small_paragraphs()
    test_fallback_splits_large_paragraphs()
    test_fallback_no_empty_chunks()
    test_fallback_empty_text_no_chunks()
    test_fallback_whitespace_only_no_chunks()
    test_chunk_id_uses_all_components()
    test_chunk_id_stable_across_calls()
    test_chunks_include_entry_ref()
    test_chunks_include_content_hash()
    test_integration_final_segments_hydration_to_chunking()
    print("retrieval.lanes.semantic.test_chunking: all checks passed.")
