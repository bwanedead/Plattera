"""Tests for concrete kernel tool dependency integrations."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
import sys

# Ensure repo root is importable when pytest is invoked from any cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import config.paths as legacy_paths
from backend.agent_kernel.run_artifact import ArtifactRef
from backend.agent_kernel.tooling import (
    CorpusArtifactOpener,
    CorpusDeedHydrator,
    DraftIRFilesystemProposer,
)


def _write_json(path: Path, obj: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def test_hydrate_deed_uses_corpus_provider_and_persists_artifact() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original_legacy_dossiers_root = legacy_paths.dossiers_root

        def _patched_root() -> Path:
            return root / "dossiers_data"

        legacy_paths.dossiers_root = _patched_root  # type: ignore[assignment]
        try:
            dossier_id = "D_TOOLING"
            finalized = (
                _patched_root()
                / "views"
                / "transcriptions"
                / dossier_id
                / "final"
                / "dossier_final.json"
            )
            _write_json(
                finalized,
                {
                    "dossier_id": dossier_id,
                    "dossier_title": "Tooling Test",
                    "generated_at": "2026-01-01T00:00:00Z",
                    "stitched_text": "Hydrated deed body",
                    "sha256": "dummy",
                },
            )
            hydrator = CorpusDeedHydrator()
            result = hydrator.hydrate_deed({"dossier_id": dossier_id})

            artifact_ref = ArtifactRef.model_validate(result["artifact_ref"])
            payload = json.loads(Path(artifact_ref.artifact_path).read_text(encoding="utf-8"))
            assert result["reason_codes"] == ["deed_hydrated"]
            assert payload["artifact_type"] == "hydrated_deed"
            assert payload["text"] == "Hydrated deed body"
        finally:
            legacy_paths.dossiers_root = original_legacy_dossiers_root  # type: ignore[assignment]


def test_open_artifact_summarizes_referenced_json_file() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "artifact.json"
        _write_json(path, {"alpha": 1, "beta": 2})
        opener = CorpusArtifactOpener()
        result = opener.open_artifact({"artifact_ref": {"artifact_path": str(path)}})

        assert result["reason_codes"] == ["artifact_opened"]
        assert str(result["summary"]).startswith("json_keys=")


def test_draft_ir_proposer_persists_stub_artifact_ref() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original_legacy_dossiers_root = legacy_paths.dossiers_root

        def _patched_root() -> Path:
            return root / "dossiers_data"

        legacy_paths.dossiers_root = _patched_root  # type: ignore[assignment]
        try:
            proposer = DraftIRFilesystemProposer()
            ref = proposer.draft_ir({"dossier_id": "D_DRAFT"})

            payload = json.loads(Path(ref.artifact_path).read_text(encoding="utf-8"))
            assert payload["artifact_type"] == "ir_draft_stub"
            assert payload["dossier_id"] == "D_DRAFT"
            assert "graph" in payload
        finally:
            legacy_paths.dossiers_root = original_legacy_dossiers_root  # type: ignore[assignment]
