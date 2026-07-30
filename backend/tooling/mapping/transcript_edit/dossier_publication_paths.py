"""Collision-free dossier-level transcript-edit publication paths."""

from __future__ import annotations

import re
from pathlib import Path

from config.paths import dossiers_transcript_edit_dossier_artifacts_root

from tooling.mapping.transcript_edit.paths import (
    UnsafeArtifactPathSegmentError,
    require_safe_path_segment,
)

_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


def require_safe_sha256_hex(value: str, *, field: str = "candidate_fingerprint") -> str:
    text = str(value or "").strip()
    if not _SHA256_HEX_RE.fullmatch(text):
        raise UnsafeArtifactPathSegmentError(f"{field}_invalid")
    return text


def dossier_transcript_edit_dossier_workspace_root(
    dossier_id: str, workspace_id: str
) -> Path:
    """Root: artifacts/transcript_edit_dossier/<dossier_id>/<workspace_id>/."""
    did = require_safe_path_segment(dossier_id, field="dossier_id")
    wid = require_safe_path_segment(workspace_id, field="workspace_id")
    return dossiers_transcript_edit_dossier_artifacts_root(did) / wid


def dossier_transcript_edit_dossier_output_dir(dossier_id: str, workspace_id: str) -> Path:
    return dossier_transcript_edit_dossier_workspace_root(dossier_id, workspace_id) / "output"


def dossier_transcript_edit_dossier_output_revisions_dir(
    dossier_id: str, workspace_id: str
) -> Path:
    return dossier_transcript_edit_dossier_output_dir(dossier_id, workspace_id) / "revisions"


def dossier_transcript_edit_dossier_output_latest_pointer_path(
    dossier_id: str, workspace_id: str
) -> Path:
    return dossier_transcript_edit_dossier_output_dir(dossier_id, workspace_id) / "latest.json"


def dossier_transcript_edit_dossier_publish_lock_path(
    dossier_id: str, workspace_id: str
) -> Path:
    return dossier_transcript_edit_dossier_output_dir(dossier_id, workspace_id) / ".publish.lock"


def dossier_transcript_edit_dossier_output_revision_path(
    dossier_id: str, workspace_id: str, candidate_fingerprint: str
) -> Path:
    fingerprint = require_safe_sha256_hex(candidate_fingerprint)
    return (
        dossier_transcript_edit_dossier_output_revisions_dir(dossier_id, workspace_id)
        / f"{fingerprint}.json"
    )
