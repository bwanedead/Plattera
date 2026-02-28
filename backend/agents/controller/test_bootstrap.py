from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import config.paths as legacy_paths
from backend.agents.controller.bootstrap import (
    hydrate_and_persist_finalized_dossier_text,
    persist_deed_text_artifact,
)


class _FakeEntry:
    def __init__(self, text: str, provenance: dict[str, str] | None = None) -> None:
        self.text = text
        self.provenance = provenance or {}


class _FakeProvider:
    def __init__(self, text: str, *, error: str | None = None) -> None:
        self._text = text
        self._error = error

    def hydrate_entry(self, ref):  # type: ignore[no-untyped-def]
        del ref
        provenance = {"error": self._error} if self._error else {}
        return _FakeEntry(self._text, provenance=provenance)


def test_persist_deed_text_artifact_writes_full_text_and_excerpt() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original = legacy_paths.dossiers_root

        def _patched_root() -> Path:
            return root / "dossiers_data"

        legacy_paths.dossiers_root = _patched_root  # type: ignore[assignment]
        try:
            text = "A" * 1500
            out = persist_deed_text_artifact(request_id="req1", deed_text=text, dossier_id="D1")
            payload = json.loads(Path(out.artifact_path).read_text(encoding="utf-8"))
            assert payload["artifact_type"] == "deed_text"
            assert payload["text"] == text
            assert len(out.excerpt) == 1000
        finally:
            legacy_paths.dossiers_root = original  # type: ignore[assignment]


def test_hydrate_and_persist_finalized_dossier_text_returns_none_on_error() -> None:
    result = hydrate_and_persist_finalized_dossier_text(
        request_id="req-x",
        dossier_id="D1",
        provider=_FakeProvider("x", error="missing"),
    )
    assert result is None


def test_hydrate_and_persist_finalized_dossier_text_persists_payload() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original = legacy_paths.dossiers_root

        def _patched_root() -> Path:
            return root / "dossiers_data"

        legacy_paths.dossiers_root = _patched_root  # type: ignore[assignment]
        try:
            out = hydrate_and_persist_finalized_dossier_text(
                request_id="req-y",
                dossier_id="D1",
                provider=_FakeProvider("Final deed text"),
            )
            assert out is not None
            payload = json.loads(Path(out.artifact_path).read_text(encoding="utf-8"))
            assert payload["text"] == "Final deed text"
            assert payload["dossier_id"] == "D1"
        finally:
            legacy_paths.dossiers_root = original  # type: ignore[assignment]


def test_hydrate_prefers_promoted_transcript_for_mapping_when_pointer_exists() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original = legacy_paths.dossiers_root

        def _patched_root() -> Path:
            return root / "dossiers_data"

        legacy_paths.dossiers_root = _patched_root  # type: ignore[assignment]
        try:
            tx_root = _patched_root() / "artifacts" / "transcription_edit" / "D1"
            tx_root.mkdir(parents=True, exist_ok=True)
            transcript_path = tx_root / "edited_transcript_x.json"
            transcript_path.write_text(
                json.dumps(
                    {
                        "sections": [
                            {"id": "s1", "body": "Promoted section one."},
                            {"id": "s2", "body": "Promoted section two."},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (tx_root / "latest_transcript_for_mapping.json").write_text(
                json.dumps({"transcript_ref": str(transcript_path)}),
                encoding="utf-8",
            )
            out = hydrate_and_persist_finalized_dossier_text(
                request_id="req-promoted",
                dossier_id="D1",
                provider=_FakeProvider("Finalized fallback text"),
            )
            assert out is not None
            payload = json.loads(Path(out.artifact_path).read_text(encoding="utf-8"))
            assert payload["text"] == "Promoted section one.\n\nPromoted section two."
        finally:
            legacy_paths.dossiers_root = original  # type: ignore[assignment]
