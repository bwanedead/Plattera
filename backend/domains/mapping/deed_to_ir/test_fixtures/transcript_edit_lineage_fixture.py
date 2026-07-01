"""Stable upstream transcript-edit lineage fixture helpers (test/support only)."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from config.paths import dossiers_transcript_edit_artifacts_root
from tooling.mapping.transcript_edit.paths import (
    UnsafeArtifactPathSegmentError,
    transcript_edit_derived_images_dir,
)

_REPO_ROOT = Path(__file__).resolve().parents[5]
_UPSTREAM_RUN_ID = "practice-row-live-20260619-76"
_DOSSIER_ID = "9f5eecb6-cd7e-483c-b691-b76aa7132e8e"
_TRANSCRIPTION_ID = "draft_legal_text_image"
_CRITICAL_EVIDENCE_UUID = "fba6f159e40d4010896245d6525d4acf"
_CRITICAL_EVIDENCE_REF = f"image:derived:{_CRITICAL_EVIDENCE_UUID}"
_MIN_REAL_PNG_BYTES = 10_000
_EXPECTED_CROP_WIDTH_HEIGHT = (3200, 1350)
_FAKE_TEST_PNG_BYTES = 67


def transcript_edit_lineage_fixture_root() -> Path:
    return (
        _REPO_ROOT
        / "practice_deeds"
        / "right_of_way"
        / "transcript_edit"
        / _UPSTREAM_RUN_ID
    )


def critical_evidence_ref() -> str:
    return _CRITICAL_EVIDENCE_REF


def critical_evidence_uuid() -> str:
    return _CRITICAL_EVIDENCE_UUID


def load_lineage_manifest(root: Path | None = None) -> dict[str, Any]:
    fixture_root = root or transcript_edit_lineage_fixture_root()
    return json.loads((fixture_root / "fixture_manifest.json").read_text(encoding="utf-8"))


def critical_descriptor_path(root: Path | None = None) -> Path:
    fixture_root = root or transcript_edit_lineage_fixture_root()
    return fixture_root / "evidence" / "derived_images" / f"{_CRITICAL_EVIDENCE_UUID}.json"


def critical_png_path(root: Path | None = None) -> Path:
    fixture_root = root or transcript_edit_lineage_fixture_root()
    return fixture_root / "evidence" / "derived_images" / f"{_CRITICAL_EVIDENCE_UUID}.png"


def source_image_path(root: Path | None = None) -> Path:
    fixture_root = root or transcript_edit_lineage_fixture_root()
    return fixture_root / "source" / "draft_legal_text_image_original.jpg"


def load_critical_descriptor(root: Path | None = None) -> dict[str, Any]:
    return json.loads(critical_descriptor_path(root).read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def restore_critical_evidence_to_live_artifacts(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    allow_live_restore: bool = False,
    fixture_root: Path | None = None,
) -> dict[str, Any]:
    """Copy critical crop PNG + descriptor from fixture into live derived_images dir."""
    if not allow_live_restore:
        raise ValueError("allow_live_restore_required")

    root = fixture_root or transcript_edit_lineage_fixture_root()
    try:
        derived_dir = transcript_edit_derived_images_dir(dossier_id, transcription_id, workspace_id)
    except UnsafeArtifactPathSegmentError as exc:
        raise ValueError(str(exc)) from exc

    expected_root = dossiers_transcript_edit_artifacts_root(_DOSSIER_ID).resolve()
    if derived_dir.resolve().parent.parent.parent != expected_root:
        raise ValueError("derived_dir_outside_expected_transcript_edit_root")
    if workspace_id != _UPSTREAM_RUN_ID:
        raise ValueError("workspace_id_must_match_lineage_fixture")
    if dossier_id != _DOSSIER_ID or transcription_id != _TRANSCRIPTION_ID:
        raise ValueError("scope_must_match_lineage_fixture")

    derived_dir.mkdir(parents=True, exist_ok=True)
    fixture_png = critical_png_path(root)
    fixture_desc = load_critical_descriptor(root)
    live_png = derived_dir / f"{_CRITICAL_EVIDENCE_UUID}.png"
    live_desc_path = derived_dir / f"{_CRITICAL_EVIDENCE_UUID}.json"

    if not fixture_png.is_file():
        raise FileNotFoundError(f"missing_fixture_png:{fixture_png}")

    shutil.copy2(fixture_png, live_png)
    live_desc = dict(fixture_desc)
    live_desc["absolute_path"] = str(live_png.resolve())
    live_desc["size_bytes"] = live_png.stat().st_size
    live_desc_path.write_text(json.dumps(live_desc, indent=2) + "\n", encoding="utf-8")

    return {
        "restored": True,
        "ref_id": _CRITICAL_EVIDENCE_REF,
        "destination_dir": str(derived_dir),
        "png_byte_length": live_png.stat().st_size,
        "width_height": live_desc.get("width_height"),
    }


def restore_critical_evidence_to_destination(
    *,
    destination_derived_dir: Path,
    fixture_root: Path | None = None,
) -> dict[str, Any]:
    """Copy critical crop into an explicit destination derived_images directory (tests)."""
    root = fixture_root or transcript_edit_lineage_fixture_root()
    destination = destination_derived_dir.resolve()
    if destination.name != "derived_images":
        raise ValueError("destination_must_be_derived_images_dir")

    fixture_png = critical_png_path(root)
    fixture_desc = load_critical_descriptor(root)
    live_png = destination / f"{_CRITICAL_EVIDENCE_UUID}.png"
    live_desc_path = destination / f"{_CRITICAL_EVIDENCE_UUID}.json"

    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(fixture_png, live_png)
    live_desc = dict(fixture_desc)
    live_desc["absolute_path"] = str(live_png.resolve())
    live_desc["size_bytes"] = live_png.stat().st_size
    live_desc_path.write_text(json.dumps(live_desc, indent=2) + "\n", encoding="utf-8")
    return {
        "restored": True,
        "ref_id": _CRITICAL_EVIDENCE_REF,
        "png_byte_length": live_png.stat().st_size,
    }


def is_fake_test_png(path: Path) -> bool:
    return path.is_file() and path.stat().st_size <= _FAKE_TEST_PNG_BYTES
