"""Safe artifact opening for Agent Viewer endpoints."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.paths import dossiers_artifacts_root, harness_cli_artifacts_root


class ArtifactAccessError(ValueError):
    pass


@dataclass(frozen=True)
class ArtifactFile:
    path: Path
    media_type: str


@dataclass(frozen=True)
class JsonArtifact:
    path: Path
    json: dict[str, Any] | list[Any]


_JSON_SUFFIXES = {".json"}
_IMAGE_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}
_SENSITIVE_NAMES = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.production",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
}
_SENSITIVE_SUFFIXES = {".pem", ".key", ".pfx", ".p12", ".crt"}


def read_json_artifact(artifact_ref: str) -> dict[str, Any] | list[Any]:
    return json_artifact(artifact_ref).json


def json_artifact(artifact_ref: str) -> JsonArtifact:
    path = resolve_artifact_path(artifact_ref, allowed_suffixes=_JSON_SUFFIXES)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ArtifactAccessError("artifact_json_invalid") from exc
    except OSError as exc:
        raise ArtifactAccessError("artifact_unreadable") from exc
    if not isinstance(payload, (dict, list)):
        raise ArtifactAccessError("artifact_json_root_invalid")
    return JsonArtifact(path=path, json=payload)


def image_artifact(artifact_ref: str) -> ArtifactFile:
    path = resolve_artifact_path(artifact_ref, allowed_suffixes=set(_IMAGE_MEDIA_TYPES))
    return ArtifactFile(path=path, media_type=_IMAGE_MEDIA_TYPES[path.suffix.lower()])


def resolve_artifact_path(artifact_ref: str, *, allowed_suffixes: set[str]) -> Path:
    root, relative = _parse_artifact_ref(artifact_ref)
    _reject_unsafe_relative(relative)
    candidate = (root / relative).resolve()
    root_resolved = root.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise ArtifactAccessError("artifact_ref_outside_allowed_root") from exc
    suffix = candidate.suffix.lower()
    if suffix not in allowed_suffixes:
        raise ArtifactAccessError("artifact_type_not_allowed")
    if not candidate.exists() or not candidate.is_file():
        raise ArtifactAccessError("artifact_not_found")
    return candidate


def _parse_artifact_ref(artifact_ref: str) -> tuple[Path, Path]:
    ref = str(artifact_ref or "").strip()
    if not ref:
        raise ArtifactAccessError("artifact_ref_required")
    if "\x00" in ref:
        raise ArtifactAccessError("artifact_ref_invalid")
    if "?" in ref or "#" in ref:
        raise ArtifactAccessError("artifact_ref_invalid")

    if ref.startswith("artifact://harness-cli/"):
        return harness_cli_artifacts_root(), Path(ref.removeprefix("artifact://harness-cli/"))
    if ref.startswith("artifact://dossiers/"):
        return dossiers_artifacts_root(), Path(ref.removeprefix("artifact://dossiers/"))
    if ref.startswith("artifact://"):
        return dossiers_artifacts_root(), Path(ref.removeprefix("artifact://"))
    return dossiers_artifacts_root(), Path(ref)


def _reject_unsafe_relative(relative: Path) -> None:
    if relative.is_absolute():
        raise ArtifactAccessError("artifact_ref_absolute_path_forbidden")
    parts = [part for part in relative.parts if part not in ("", ".")]
    if not parts:
        raise ArtifactAccessError("artifact_ref_required")
    for part in parts:
        lower = part.lower()
        if lower == "..":
            raise ArtifactAccessError("artifact_ref_path_traversal_forbidden")
        if lower in _SENSITIVE_NAMES or Path(lower).suffix in _SENSITIVE_SUFFIXES:
            raise ArtifactAccessError("artifact_ref_sensitive_path_forbidden")
