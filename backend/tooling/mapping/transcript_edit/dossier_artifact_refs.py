"""Collision-free dossier-qualified artifact refs for multi-segment transcript-edit.

Grammar:
  dossier_segment:<segment_id>:run:<transcription_id>:<leaf_ref>

``segment_id`` and ``transcription_id`` must be single safe path segments (no
colons). ``leaf_ref`` is the existing per-transcription ref (may contain colons).

Resolution is index-backed only — never guess meaning by parsing arbitrary strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence

from tooling.mapping.transcript_edit.paths import (
    UnsafeArtifactPathSegmentError,
    require_safe_path_segment,
)

_PREFIX = "dossier_segment:"
_RUN_TOKEN = ":run:"


class DossierArtifactRefError(Exception):
    """Mechanical refusal for invalid dossier-qualified artifact refs."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = str(code)
        self.detail = str(detail or "")
        message = self.code if not self.detail else f"{self.code}: {self.detail}"
        super().__init__(message)


@dataclass(frozen=True)
class DossierArtifactRefTarget:
    segment_id: str
    transcription_id: str
    leaf_ref: str


@dataclass(frozen=True)
class DossierArtifactRefIndex:
    """Validated, immutable map from dossier-qualified refs to leaf targets."""

    dossier_id: str
    topology_fingerprint: str
    by_ref: Mapping[str, DossierArtifactRefTarget]

    def resolve(self, qualified_ref: str) -> DossierArtifactRefTarget:
        key = str(qualified_ref or "").strip()
        if not key:
            raise DossierArtifactRefError("ref_empty")
        target = self.by_ref.get(key)
        if target is None:
            raise DossierArtifactRefError("unknown_ref", key)
        return target


def qualify_leaf_ref(
    *,
    segment_id: str,
    transcription_id: str,
    leaf_ref: str,
) -> str:
    """Build a deterministic dossier-qualified ref from validated identities + leaf."""
    sid = _require_ref_identity(segment_id, field="segment_id")
    tid = _require_ref_identity(transcription_id, field="transcription_id")
    leaf = str(leaf_ref or "").strip()
    if not leaf:
        raise DossierArtifactRefError("leaf_ref_empty")
    if "\n" in leaf or "\r" in leaf:
        raise DossierArtifactRefError("leaf_ref_invalid", leaf)
    return f"{_PREFIX}{sid}{_RUN_TOKEN}{tid}:{leaf}"


def build_dossier_artifact_ref_index(
    *,
    dossier_id: str,
    topology_fingerprint: str,
    entries: Mapping[str, DossierArtifactRefTarget]
    | Sequence[tuple[str, DossierArtifactRefTarget]],
) -> DossierArtifactRefIndex:
    """Build an immutable index bound to dossier lineage; rejects blank/duplicate refs."""
    did = _require_bound_identity(dossier_id, field="dossier_id")
    fingerprint = _require_bound_identity(topology_fingerprint, field="topology_fingerprint")
    if isinstance(entries, Mapping):
        items = list(entries.items())
    else:
        items = list(entries)

    by_ref: dict[str, DossierArtifactRefTarget] = {}
    for qualified, target in items:
        key = str(qualified or "").strip()
        if not key:
            raise DossierArtifactRefError("ref_empty")
        if key in by_ref:
            raise DossierArtifactRefError("duplicate_qualified_ref", key)
        if not isinstance(target, DossierArtifactRefTarget):
            raise DossierArtifactRefError("invalid_target", key)
        expected = qualify_leaf_ref(
            segment_id=target.segment_id,
            transcription_id=target.transcription_id,
            leaf_ref=target.leaf_ref,
        )
        if key != expected:
            raise DossierArtifactRefError(
                "qualified_ref_mismatch",
                f"expected {expected}, got {key}",
            )
        by_ref[key] = target
    return DossierArtifactRefIndex(
        dossier_id=did,
        topology_fingerprint=fingerprint,
        by_ref=MappingProxyType(dict(by_ref)),
    )


def _require_bound_identity(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise DossierArtifactRefError("invalid_index_lineage", f"{field}:{value!r}")
    text = value.strip()
    if not text:
        raise DossierArtifactRefError("invalid_index_lineage", f"{field}:{value!r}")
    return text


def _require_ref_identity(value: str, *, field: str) -> str:
    try:
        text = require_safe_path_segment(value, field=field)
    except UnsafeArtifactPathSegmentError as exc:
        raise DossierArtifactRefError("unsafe_identity", f"{field}:{exc}") from exc
    if ":" in text:
        raise DossierArtifactRefError("unsafe_identity", f"{field}_contains_colon")
    return text
