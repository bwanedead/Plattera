"""Shared path-segment validation for feature-graph artifact storage."""

from __future__ import annotations


class UnsafeFeatureGraphPathError(ValueError):
    """Raised when dossier_id or artifact_id would escape the artifacts root."""


def require_safe_dossier_id(dossier_id: str) -> str:
    text = str(dossier_id or "").strip()
    if not text:
        raise UnsafeFeatureGraphPathError("dossier_id_empty")
    if ".." in text or "/" in text or "\\" in text:
        raise UnsafeFeatureGraphPathError("dossier_id_unsafe_path_characters")
    if text.startswith("."):
        raise UnsafeFeatureGraphPathError("dossier_id_unsafe_leading_dot")
    return text
