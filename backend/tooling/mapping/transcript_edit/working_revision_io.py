"""Shared mechanical IO helpers for transcript-edit working revisions.

Used by the write-transaction seam and publish/save surfaces so manifest/ref
parsing stay single-owned.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from tooling.mapping.transcript_edit.paths import transcript_edit_manifest_path

SCHEMA_VERSION = 1

_WORKING_REV_REF_RE = re.compile(r"^transcript_edit:working:rev:(\d{4})$")

JsonObjectKind = Literal["absent", "valid", "invalid"]


class JsonObjectFileInvalid(Exception):
    """Present JSON object file is malformed or noncanonical."""

    def __init__(self, detail: str = "") -> None:
        self.detail = str(detail or "JSON object file is invalid.")
        super().__init__(self.detail)


class ManifestStorageInvalid(Exception):
    """Present manifest.json is malformed; must not be replaced with a default."""

    def __init__(self, detail: str = "") -> None:
        self.detail = str(detail or "manifest.json is invalid.")
        super().__init__(self.detail)


@dataclass(frozen=True)
class JsonObjectProbe:
    """Existence-aware load of a JSON object file."""

    kind: JsonObjectKind
    value: dict[str, Any] | None = None
    detail: str = ""


def parse_working_revision_ref(ref_id: Any) -> str | None:
    """Return four-digit revision stem if ref is ``transcript_edit:working:rev:NNNN``.

    Requires an actual string — never coerces other types via ``str(...)``.
    """
    if type(ref_id) is not str:
        return None
    m = _WORKING_REV_REF_RE.match(ref_id.strip())
    return m.group(1) if m else None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _reject_noncanonical_json_constant(name: str) -> Any:
    raise ValueError(f"noncanonical JSON constant rejected: {name}")


def loads_json_object_text(text: str) -> dict[str, Any]:
    """Parse a JSON object, rejecting NaN/Infinity and non-object roots."""
    raw = json.loads(text, parse_constant=_reject_noncanonical_json_constant)
    if type(raw) is not dict:
        raise ValueError("JSON root must be an object.")
    return raw


def probe_json_object_file(path: Path) -> JsonObjectProbe:
    """Classify a path as absent, valid object, or present-but-invalid."""
    if path.is_symlink():
        return JsonObjectProbe(
            kind="invalid",
            detail=f"{path.name} must not be a symlink.",
        )
    if not path.is_file():
        return JsonObjectProbe(kind="absent")
    try:
        text = path.read_text(encoding="utf-8")
        value = loads_json_object_text(text)
    except Exception as exc:
        return JsonObjectProbe(
            kind="invalid",
            detail=f"{path.name} is present but malformed: {exc}",
        )
    return JsonObjectProbe(kind="valid", value=value)


def load_json_file(path: Path) -> dict[str, Any] | None:
    """Return a valid object, ``None`` if absent, or raise if present-but-invalid."""
    probe = probe_json_object_file(path)
    if probe.kind == "absent":
        return None
    if probe.kind == "invalid":
        raise JsonObjectFileInvalid(probe.detail)
    assert probe.value is not None
    return probe.value


def default_manifest(*, dossier_id: str, transcription_id: str, workspace_id: str) -> dict[str, Any]:
    now = utc_now_iso()
    return {
        "schema_version": SCHEMA_VERSION,
        "dossier_id": dossier_id,
        "transcription_id": transcription_id,
        "workspace_id": workspace_id,
        "created_at": now,
        "updated_at": now,
        "revision_count": 0,
        "latest_revision": 0,
        "latest_working_ref_id": None,
        "latest_saved_at": None,
        "latest_content_sha256": None,
        "output_published_at": None,
        "output_source_revision_ref": None,
    }


def load_or_init_manifest(
    dossier_id: str, transcription_id: str, workspace_id: str
) -> dict[str, Any]:
    """Load manifest.json, or initialize only when the file is truly absent.

    Present malformed manifests raise ``ManifestStorageInvalid`` — never silently
    replaced with a default empty manifest.
    """
    path = transcript_edit_manifest_path(dossier_id, transcription_id, workspace_id)
    probe = probe_json_object_file(path)
    if probe.kind == "absent":
        return default_manifest(
            dossier_id=dossier_id, transcription_id=transcription_id, workspace_id=workspace_id
        )
    if probe.kind == "invalid":
        raise ManifestStorageInvalid(probe.detail)
    assert probe.value is not None
    schema = probe.value.get("schema_version")
    # Exact int equality — never coerce via int(...).
    if type(schema) is not int or isinstance(schema, bool) or schema != SCHEMA_VERSION:
        raise ManifestStorageInvalid(
            "manifest.schema_version must be the exact integer "
            f"{SCHEMA_VERSION}; got {schema!r}."
        )
    return probe.value
