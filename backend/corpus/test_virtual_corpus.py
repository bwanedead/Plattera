from __future__ import annotations

"""
Lightweight sanity checks for the virtual corpus layer.

These are intentionally simple "micro-tests" that can be run ad-hoc:

    (.venv) python -m backend.corpus.test_virtual_corpus

They avoid pytest dependencies and exercise only the public corpus surface.
"""

import json
import tempfile
from pathlib import Path
from typing import Any, Dict

from . import (
    CorpusEntryKind,
    CorpusEntryRef,
    CorpusView,
    VirtualCorpusProvider,
)
from .hydrate import CorpusHydrator
from .types import CorpusEntry
import config.paths as paths_mod


def _write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def test_enumerate_finalized_empty_ok() -> None:
    """
    Enumerating finalized entries should not crash on an empty dataset.
    """

    provider = VirtualCorpusProvider()
    refs = list(provider.list_entry_refs(CorpusView.FINALIZED))
    # No specific cardinality requirement here; we just assert it does not raise.
    assert isinstance(refs, list)


def test_enumerate_everything_draft_aware_entry_id() -> None:
    """
    EVERYTHING view should emit draft-aware transcript refs with entry_id == draft_id.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        original_dossiers_root = paths_mod.dossiers_root

        def _patched_dossiers_root() -> Path:
            return root / "dossiers_data"

        paths_mod.dossiers_root = _patched_dossiers_root  # type: ignore[assignment]
        try:
            dossier_id = "D_EVERY"
            transcription_id = "T_HEAD"
            raw_path = (
                _patched_dossiers_root()
                / "views"
                / "transcriptions"
                / dossier_id
                / transcription_id
                / "raw"
                / f"{transcription_id}.json"
            )
            _write_json(raw_path, {"text": "Hello draft"})

            provider = VirtualCorpusProvider()
            refs = list(provider.list_entry_refs(CorpusView.EVERYTHING))

            assert len(refs) >= 1, "Expected at least 1 ref from EVERYTHING view"
            ref = refs[0]
            expected_draft_id = f"draft:head:{dossier_id}:{transcription_id}"
            assert ref.entry_id == expected_draft_id
            assert ref.draft_id == expected_draft_id
            assert ref.kind == CorpusEntryKind.TRANSCRIPT
            assert ref.dossier_id == dossier_id
            assert ref.transcription_id == transcription_id
        finally:
            paths_mod.dossiers_root = original_dossiers_root  # type: ignore[assignment]


def test_hydrate_transcript_head_draft_id_matches_legacy() -> None:
    """
    Hydrating a transcript ref with head-form draft_id loads the same content as legacy.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        original_dossiers_root = paths_mod.dossiers_root

        def _patched_dossiers_root() -> Path:
            return root / "dossiers_data"

        paths_mod.dossiers_root = _patched_dossiers_root  # type: ignore[assignment]
        try:
            dossier_id = "D_DRAFT_HYDRATE"
            transcription_id = "T_HEAD"
            raw_path = (
                _patched_dossiers_root()
                / "views"
                / "transcriptions"
                / dossier_id
                / transcription_id
                / "raw"
                / f"{transcription_id}.json"
            )
            payload = {"sections": [{"body": "Draft body"}], "title": "Draft Title"}
            _write_json(raw_path, payload)

            hydrator = CorpusHydrator()
            legacy_ref = CorpusEntryRef(
                view=CorpusView.EVERYTHING,
                entry_id=f"transcript:{dossier_id}:{transcription_id}",
                kind=CorpusEntryKind.TRANSCRIPT,
                dossier_id=dossier_id,
                transcription_id=transcription_id,
            )
            draft_id = f"draft:head:{dossier_id}:{transcription_id}"
            draft_ref = CorpusEntryRef(
                view=CorpusView.EVERYTHING,
                entry_id=draft_id,
                kind=CorpusEntryKind.TRANSCRIPT,
                draft_id=draft_id,
            )

            legacy_entry = hydrator.hydrate(legacy_ref)
            draft_entry = hydrator.hydrate(draft_ref)

            assert legacy_entry.text == "Draft body"
            assert draft_entry.text == legacy_entry.text
            assert draft_entry.content_hash == legacy_entry.content_hash
            assert draft_entry.provenance.get("draft_id") == draft_id
        finally:
            paths_mod.dossiers_root = original_dossiers_root  # type: ignore[assignment]


def test_hydrate_finalized_minimal_snapshot() -> None:
    """
    Hydrating a FINALIZED_DOSSIER_TEXT entry over a minimal fake snapshot
    yields non-empty text and a content_hash.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Patch dossiers_root() to point at our temp tree
        original_dossiers_root = paths_mod.dossiers_root

        def _patched_dossiers_root() -> Path:
            return root / "dossiers_data"

        paths_mod.dossiers_root = _patched_dossiers_root  # type: ignore[assignment]
        try:
            dossier_id = "D1"
            final_dir = (
                _patched_dossiers_root() / "views" / "transcriptions" / dossier_id / "final"
            )
            payload = {
                "dossier_id": dossier_id,
                "dossier_title": "Test Dossier",
                "generated_at": "2024-01-01T00:00:00Z",
                "stitched_text": "Hello world",
                "sections": [],
                "selection_map": [],
                "counts": {"segments": 0, "text_length": 11},
                "errors": [],
                "sha256": "dummy",
            }
            _write_json(final_dir / "dossier_final.json", payload)

            hydrator = CorpusHydrator()
            ref = CorpusEntryRef(
                view=CorpusView.FINALIZED,
                entry_id=f"final:{dossier_id}",
                kind=CorpusEntryKind.FINALIZED_DOSSIER_TEXT,
                dossier_id=dossier_id,
            )
            entry: CorpusEntry = hydrator.hydrate(ref)
            assert entry.text == "Hello world"
            assert isinstance(entry.content_hash, str) and entry.content_hash
            assert entry.title == "Test Dossier"
        finally:
            # Restore original function to avoid side effects
            paths_mod.dossiers_root = original_dossiers_root  # type: ignore[assignment]


def test_hydrate_finalized_missing_safe() -> None:
    """
    Hydrating a FINALIZED_DOSSIER_TEXT entry for a missing dossier should not
    raise; it should return an entry with empty text and an error marker.
    """

    hydrator = CorpusHydrator()
    ref = CorpusEntryRef(
        view=CorpusView.FINALIZED,
        entry_id="final:NONEXISTENT",
        kind=CorpusEntryKind.FINALIZED_DOSSIER_TEXT,
        dossier_id="NONEXISTENT",
    )
    entry: CorpusEntry = hydrator.hydrate(ref)
    assert entry.text == ""
    assert "error" in (entry.provenance or {})


# ----- FINAL_SEGMENTS view tests -----


def test_enumerate_final_segments_with_registry() -> None:
    """
    Enumerating FINAL_SEGMENTS view with a valid final_registry.json yields
    refs with segment_id and draft_id populated.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Patch paths to point at our temp tree
        original_dossiers_root = paths_mod.dossiers_root
        original_dossiers_state_root = paths_mod.dossiers_state_root
        original_dossiers_management_root = paths_mod.dossiers_management_root

        def _patched_dossiers_root() -> Path:
            return root / "dossiers_data"

        def _patched_dossiers_state_root() -> Path:
            return root / "dossiers_data" / "state"

        def _patched_dossiers_management_root() -> Path:
            return root / "dossiers_data" / "management"

        paths_mod.dossiers_root = _patched_dossiers_root  # type: ignore[assignment]
        paths_mod.dossiers_state_root = _patched_dossiers_state_root  # type: ignore[assignment]
        paths_mod.dossiers_management_root = _patched_dossiers_management_root  # type: ignore[assignment]

        try:
            dossier_id = "D_FINAL_SEG"

            # Create management file so dossier is enumerable
            mgmt_dir = _patched_dossiers_management_root()
            _write_json(mgmt_dir / f"dossier_{dossier_id}.json", {"id": dossier_id})

            # Create final_registry.json with one segment mapping
            state_dir = _patched_dossiers_state_root() / dossier_id
            registry = {
                "segments": {
                    "seg_001": {
                        "transcription_id": "T1",
                        "draft_id": "T1_v1",
                        "set_at": "2024-01-01T00:00:00Z",
                        "set_by": "test_user",
                    }
                },
                "_version": 1,
            }
            _write_json(state_dir / "final_registry.json", registry)

            provider = VirtualCorpusProvider()
            refs = list(provider.list_entry_refs(CorpusView.FINAL_SEGMENTS))

            assert len(refs) >= 1, "Expected at least 1 ref from FINAL_SEGMENTS view"
            ref = refs[0]
            assert ref.view == CorpusView.FINAL_SEGMENTS
            assert ref.kind == CorpusEntryKind.SEGMENT_FINAL_TEXT
            assert ref.segment_id == "seg_001"
            assert ref.draft_id == "T1_v1"
            assert ref.dossier_id == dossier_id
            assert ref.transcription_id == "T1"

        finally:
            paths_mod.dossiers_root = original_dossiers_root  # type: ignore[assignment]
            paths_mod.dossiers_state_root = original_dossiers_state_root  # type: ignore[assignment]
            paths_mod.dossiers_management_root = original_dossiers_management_root  # type: ignore[assignment]


def test_hydrate_segment_final_entry() -> None:
    """
    Hydrating a SEGMENT_FINAL_TEXT entry yields non-empty text and content_hash.
    """

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Patch paths
        original_dossiers_root = paths_mod.dossiers_root
        original_dossiers_views_root = paths_mod.dossiers_views_root

        def _patched_dossiers_root() -> Path:
            return root / "dossiers_data"

        def _patched_dossiers_views_root() -> Path:
            return root / "dossiers_data" / "views" / "transcriptions"

        paths_mod.dossiers_root = _patched_dossiers_root  # type: ignore[assignment]
        paths_mod.dossiers_views_root = _patched_dossiers_views_root  # type: ignore[assignment]

        try:
            dossier_id = "D_HYDRATE_SEG"
            draft_id = "T1"

            # Create the draft JSON file at the expected path
            # Non-versioned: <views_root>/<dossier_id>/<draft_id>/raw/<draft_id>.json
            draft_path = (
                _patched_dossiers_views_root()
                / dossier_id
                / draft_id
                / "raw"
                / f"{draft_id}.json"
            )
            draft_payload = {
                "sections": [
                    {"header": "Section 1", "body": "First section body."},
                    {"header": "Section 2", "body": "Second section body."},
                ],
                "title": "Test Draft",
                "saved_at": "2024-01-02T00:00:00Z",
            }
            _write_json(draft_path, draft_payload)

            ref = CorpusEntryRef(
                view=CorpusView.FINAL_SEGMENTS,
                entry_id=f"segment_final:{dossier_id}:seg_001:{draft_id}",
                kind=CorpusEntryKind.SEGMENT_FINAL_TEXT,
                dossier_id=dossier_id,
                transcription_id=draft_id,
                segment_id="seg_001",
                draft_id=draft_id,
                metadata={"set_at": "2024-01-01T00:00:00Z"},
            )

            hydrator = CorpusHydrator()
            entry: CorpusEntry = hydrator.hydrate(ref)

            # Assertions
            assert entry.text != "", "Expected non-empty text"
            assert "First section body" in entry.text
            assert "Second section body" in entry.text
            assert entry.content_hash is not None and entry.content_hash != ""
            assert entry.ref.segment_id == "seg_001"
            assert entry.provenance.get("draft_id") == draft_id
            assert entry.provenance.get("source") == "segment_final_registry"
            assert entry.title == "Test Draft"

        finally:
            paths_mod.dossiers_root = original_dossiers_root  # type: ignore[assignment]
            paths_mod.dossiers_views_root = original_dossiers_views_root  # type: ignore[assignment]


def test_hydrate_segment_final_missing_draft_safe() -> None:
    """
    Hydrating a SEGMENT_FINAL_TEXT entry where the draft file doesn't exist
    should return empty text with an error marker, not raise.
    """

    hydrator = CorpusHydrator()
    ref = CorpusEntryRef(
        view=CorpusView.FINAL_SEGMENTS,
        entry_id="segment_final:NONEXISTENT:seg_001:MISSING_DRAFT",
        kind=CorpusEntryKind.SEGMENT_FINAL_TEXT,
        dossier_id="NONEXISTENT",
        transcription_id="MISSING_TRANS",
        segment_id="seg_001",
        draft_id="MISSING_DRAFT",
    )

    entry: CorpusEntry = hydrator.hydrate(ref)

    assert entry.text == ""
    assert "error" in (entry.provenance or {})
    assert "not_found" in entry.provenance.get("error", "")


if __name__ == "__main__":
    # Run micro-tests when executed directly.
    test_enumerate_finalized_empty_ok()
    test_hydrate_finalized_minimal_snapshot()
    test_hydrate_finalized_missing_safe()
    test_enumerate_final_segments_with_registry()
    test_hydrate_segment_final_entry()
    test_hydrate_segment_final_missing_draft_safe()
    print("backend.corpus.test_virtual_corpus: all checks passed.")


