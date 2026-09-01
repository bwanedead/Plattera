"""STORAGE-BR-008: transform-source assoc refusal containment."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import config.paths as paths_mod
import tooling.mapping.transcript_edit.paths as te_paths_mod
from tooling.mapping.transcript_edit.artifact_transform import make_transform_artifact_handler
from tooling.mapping.transcript_edit.transform_source_image import resolve_transform_source_image

_WINDOWS_PATH = r"C:\Users\dawki\secret\dossiers_data\associations\assoc_d1.json"
_MALFORMED_JSON = "{not-valid-json"


def _root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "data"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(te_paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    return root


def test_assoc_missing_file_refusal_never_leaks_windows_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Production-shaped: missing association file carries a host path internally only."""
    root = _root(tmp_path, monkeypatch)
    # Intentionally absent: association_path(d1) resolves under dossiers_root.
    assert not (root / "associations" / "assoc_d1.json").exists()

    _, err = resolve_transform_source_image(
        ref_id="image:assoc:tx-1:original",
        dossier_id="d1",
        transcription_id="tx-1",
        workspace_key="ws-1",
    )
    assert err is not None
    assert err["code"] == "association_missing"
    blob = json.dumps(err)
    assert _WINDOWS_PATH not in blob
    assert ":\\" not in blob
    assert "Users" not in blob
    assert err["message"] == "Association metadata file is missing."


def test_assoc_malformed_json_refusal_never_leaks_exception_detail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path, monkeypatch)
    assoc_dir = root / "associations"
    assoc_dir.mkdir(parents=True)
    (assoc_dir / "assoc_d1.json").write_text(_MALFORMED_JSON, encoding="utf-8")

    _, err = resolve_transform_source_image(
        ref_id="image:assoc:tx-1:original",
        dossier_id="d1",
        transcription_id="tx-1",
        workspace_key="ws-1",
    )
    assert err is not None
    assert err["code"] == "association_read_error"
    blob = json.dumps(err)
    assert _MALFORMED_JSON not in blob
    assert "Expecting" not in blob
    assert "JSONDecodeError" not in blob
    assert err["message"] == "Association metadata could not be read."


def test_transform_handler_serializes_assoc_refusal_without_path_leakage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path, monkeypatch)
    assoc_dir = root / "associations"
    assoc_dir.mkdir(parents=True)
    (assoc_dir / "assoc_d1.json").write_text(_MALFORMED_JSON, encoding="utf-8")

    handler = make_transform_artifact_handler(
        dossier_id="d1", transcription_id="tx-1", workspace_key="ws-1"
    )
    result = handler(
        {
            "ref_id": "image:assoc:tx-1:original",
            "sub_action": "crop",
            "params": {"box_norm": [0.0, 0.0, 0.5, 0.5]},
        }
    )
    assert result["executed"] is False
    blob = json.dumps(result)
    assert _MALFORMED_JSON not in blob
    assert "Expecting" not in blob
    assert "JSONDecodeError" not in blob
    assert result["refusal"]["reason_code"] == "association_read_error"
    assert result["outputs"]["error"]["message"] == "Association metadata could not be read."
