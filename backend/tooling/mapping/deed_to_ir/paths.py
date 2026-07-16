"""Path helpers for deed-to-IR published output (tooling-internal)."""

from __future__ import annotations

from pathlib import Path

from config.paths import dossiers_deed_to_ir_artifacts_root


class UnsafeDeedToIrPathSegmentError(ValueError):
    """Raised when a dossier/transcription/workspace segment is unsafe."""


def require_safe_path_segment(value: str, *, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise UnsafeDeedToIrPathSegmentError(f"{field}_empty")
    if ".." in text or "/" in text or "\\" in text:
        raise UnsafeDeedToIrPathSegmentError(f"{field}_unsafe_path_characters")
    if text.startswith("."):
        raise UnsafeDeedToIrPathSegmentError(f"{field}_unsafe_leading_dot")
    return text


def require_safe_revision_digits(value: str) -> str:
    rev = str(value or "").strip()
    if len(rev) != 4 or not rev.isdigit():
        raise UnsafeDeedToIrPathSegmentError("revision_digits_invalid")
    return rev


def deed_to_ir_workspace_root(dossier_id: str, transcription_id: str, workspace_id: str) -> Path:
    did = require_safe_path_segment(dossier_id, field="dossier_id")
    tid = require_safe_path_segment(transcription_id, field="transcription_id")
    wid = require_safe_path_segment(workspace_id, field="workspace_id")
    return dossiers_deed_to_ir_artifacts_root(did) / tid / wid


def deed_to_ir_output_dir(dossier_id: str, transcription_id: str, workspace_id: str) -> Path:
    return deed_to_ir_workspace_root(dossier_id, transcription_id, workspace_id) / "output"


def deed_to_ir_output_latest_pointer_path(dossier_id: str, transcription_id: str, workspace_id: str) -> Path:
    return deed_to_ir_output_dir(dossier_id, transcription_id, workspace_id) / "latest.json"


def deed_to_ir_output_revision_path(
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    revision_digits: str,
) -> Path:
    rev = require_safe_revision_digits(revision_digits)
    return deed_to_ir_output_dir(dossier_id, transcription_id, workspace_id) / f"rev_{rev}.json"


def deed_to_ir_preview_dir(dossier_id: str, transcription_id: str, workspace_id: str) -> Path:
    return deed_to_ir_workspace_root(dossier_id, transcription_id, workspace_id) / "final_package_preview"


def deed_to_ir_preview_latest_pointer_path(dossier_id: str, transcription_id: str, workspace_id: str) -> Path:
    return deed_to_ir_preview_dir(dossier_id, transcription_id, workspace_id) / "latest.json"


def deed_to_ir_preview_revision_path(
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    revision_digits: str,
) -> Path:
    rev = require_safe_revision_digits(revision_digits)
    return deed_to_ir_preview_dir(dossier_id, transcription_id, workspace_id) / f"rev_{rev}.json"


def deed_to_ir_current_mapping_lineage_path(
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
) -> Path:
    """Workspace-root sidecar for the canonical current mapping/IR lineage."""
    return deed_to_ir_workspace_root(dossier_id, transcription_id, workspace_id) / "current_mapping_lineage.json"


def deed_to_ir_finalization_session_path(
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
) -> Path:
    """Workspace-root sidecar for the lineage-bound pending finalization session."""
    return deed_to_ir_workspace_root(dossier_id, transcription_id, workspace_id) / "finalization_session.json"
