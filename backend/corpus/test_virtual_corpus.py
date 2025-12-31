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
from ..config import paths as paths_mod


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


if __name__ == "__main__":
    # Run micro-tests when executed directly.
    test_enumerate_finalized_empty_ok()
    test_hydrate_finalized_minimal_snapshot()
    test_hydrate_finalized_missing_safe()
    print("backend.corpus.test_virtual_corpus: all checks passed.")


