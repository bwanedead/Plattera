"""Path helpers for dossier transcription runs and transcript-edit artifacts (tooling-internal)."""

from __future__ import annotations

from pathlib import Path

from config.paths import dossier_run_root, dossiers_root, dossiers_transcript_edit_artifacts_root


class UnsafeArtifactPathSegmentError(ValueError):
    """Raised when a dossier/transcription/workspace segment is empty or would escape its directory."""


def require_safe_path_segment(value: str, *, field: str) -> str:
    """
    Validate a single path component for dossier-scoped tooling paths in this module:
    T0 run dirs, association filenames, and transcript-edit artifact roots.
    Rejects empty, path separators, parent hops, and leading dots (launch-context safe).
    """
    s = str(value).strip()
    if not s:
        raise UnsafeArtifactPathSegmentError(f"{field}_empty")
    if ".." in s or "/" in s or "\\" in s:
        raise UnsafeArtifactPathSegmentError(f"{field}_unsafe_path_characters")
    if s.startswith("."):
        raise UnsafeArtifactPathSegmentError(f"{field}_unsafe_leading_dot")
    return s


def transcription_run_dir(dossier_id: str, transcription_id: str) -> Path:
    did = require_safe_path_segment(dossier_id, field="dossier_id")
    tid = require_safe_path_segment(transcription_id, field="transcription_id")
    return dossier_run_root(did, tid)


def run_json_path(dossier_id: str, transcription_id: str) -> Path:
    return transcription_run_dir(dossier_id, transcription_id) / "run.json"


def raw_drafts_dir(dossier_id: str, transcription_id: str) -> Path:
    return transcription_run_dir(dossier_id, transcription_id) / "raw"


def transcript_edit_workspace_root(dossier_id: str, transcription_id: str, workspace_id: str) -> Path:
    """Domain-owned transcript-edit workspace (not under views/.../raw or harness/)."""
    did = require_safe_path_segment(dossier_id, field="dossier_id")
    tid = require_safe_path_segment(transcription_id, field="transcription_id")
    wid = require_safe_path_segment(workspace_id, field="workspace_id")
    return dossiers_transcript_edit_artifacts_root(did) / tid / wid


def transcript_edit_derived_images_dir(dossier_id: str, transcription_id: str, workspace_id: str) -> Path:
    """Per-workspace directory for derived image artifacts created by ``transform_artifact``."""
    return transcript_edit_workspace_root(dossier_id, transcription_id, workspace_id) / "derived_images"


def transcript_edit_working_dir(dossier_id: str, transcription_id: str, workspace_id: str) -> Path:
    return transcript_edit_workspace_root(dossier_id, transcription_id, workspace_id) / "working"


def transcript_edit_latest_pointer_path(dossier_id: str, transcription_id: str, workspace_id: str) -> Path:
    return transcript_edit_working_dir(dossier_id, transcription_id, workspace_id) / "latest.json"


def transcript_edit_output_path(dossier_id: str, transcription_id: str, workspace_id: str) -> Path:
    return transcript_edit_workspace_root(dossier_id, transcription_id, workspace_id) / "output" / "output.json"


def transcript_edit_manifest_path(dossier_id: str, transcription_id: str, workspace_id: str) -> Path:
    return transcript_edit_workspace_root(dossier_id, transcription_id, workspace_id) / "manifest.json"


def require_safe_workspace_relative_path(relative_path: str) -> str:
    """
    Reject path escapes when joining pointer targets under a workspace root.
    Allows e.g. ``working/rev_0001.json``; rejects ``..``, absolute, or empty segments.
    """
    s = str(relative_path).replace("\\", "/").strip().lstrip("/")
    if not s or s.startswith("/"):
        raise UnsafeArtifactPathSegmentError("relative_path_empty_or_absolute")
    for part in s.split("/"):
        if part in ("", ".", "..") or part.startswith("."):
            raise UnsafeArtifactPathSegmentError("relative_path_unsafe_segment")
    return s


def require_safe_revision_digits(value: str) -> str:
    """Four-digit revision stem only (matches ``transcript_edit:working:rev:NNNN`` files)."""
    rev = str(value).strip()
    if len(rev) != 4 or not rev.isdigit():
        raise UnsafeArtifactPathSegmentError("revision_digits_invalid")
    return rev


def transcript_edit_revision_path(
    dossier_id: str, transcription_id: str, workspace_id: str, revision_digits: str
) -> Path:
    rev = require_safe_revision_digits(revision_digits)
    return transcript_edit_working_dir(dossier_id, transcription_id, workspace_id) / f"rev_{rev}.json"


def association_path(dossier_id: str) -> Path:
    did = require_safe_path_segment(dossier_id, field="dossier_id")
    return dossiers_root() / "associations" / f"assoc_{did}.json"
