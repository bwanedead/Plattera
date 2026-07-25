"""Collision-free dossier-qualified artifact refs for multi-segment transcript-edit.

Grammar:
  dossier_segment:<segment_id>:run:<transcription_id>:<leaf_ref>

``segment_id`` and ``transcription_id`` must be single safe path segments (no
colons). ``leaf_ref`` is the existing per-transcription ref (may contain colons).

Exact startup refs resolve via the immutable index. Supported runtime-minted
leaf kinds may also resolve strictly after run-binding validation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence

from tooling.mapping.transcript_edit.draft_persistence import parse_working_revision_ref
from tooling.mapping.transcript_edit.paths import (
    UnsafeArtifactPathSegmentError,
    require_safe_path_segment,
)

_PREFIX = "dossier_segment:"
_RUN_TOKEN = ":run:"
_IMAGE_DERIVED_PREFIX = "image:derived:"
_WORKING_REV_LEAF_RE = re.compile(r"^transcript_edit:working:rev:(\d{4})$")
_DERIVED_OPAQUE_RE = re.compile(r"^[0-9a-fA-F]+$")


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
    run_bindings: frozenset[tuple[str, str]]

    def has_run(self, segment_id: str, transcription_id: str) -> bool:
        return (segment_id, transcription_id) in self.run_bindings

    def resolve(self, qualified_ref: str) -> DossierArtifactRefTarget:
        """Resolve an exact startup ref or a supported runtime-minted qualified ref."""
        key = str(qualified_ref or "").strip()
        if not key:
            raise DossierArtifactRefError("dossier_ref_required")
        hit = self.by_ref.get(key)
        if hit is not None:
            return hit
        return resolve_runtime_qualified_ref(ref_index=self, qualified_ref=key)


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


def parse_dossier_qualified_ref(qualified_ref: str) -> DossierArtifactRefTarget:
    """Parse the exact dossier-qualified grammar; does not prove membership."""
    key = str(qualified_ref or "").strip()
    if not key:
        raise DossierArtifactRefError("dossier_ref_required")
    if not key.startswith(_PREFIX):
        raise DossierArtifactRefError("dossier_ref_invalid", key)
    rest = key[len(_PREFIX) :]
    run_at = rest.find(_RUN_TOKEN)
    if run_at <= 0:
        raise DossierArtifactRefError("dossier_ref_invalid", key)
    segment_raw = rest[:run_at]
    after_run = rest[run_at + len(_RUN_TOKEN) :]
    leaf_at = after_run.find(":")
    if leaf_at <= 0:
        raise DossierArtifactRefError("dossier_ref_invalid", key)
    transcription_raw = after_run[:leaf_at]
    leaf_ref = after_run[leaf_at + 1 :]
    if not leaf_ref.strip() or leaf_ref.strip() != leaf_ref:
        raise DossierArtifactRefError("dossier_ref_invalid", key)
    segment_id = _require_ref_identity(segment_raw, field="segment_id")
    transcription_id = _require_ref_identity(transcription_raw, field="transcription_id")
    return DossierArtifactRefTarget(
        segment_id=segment_id,
        transcription_id=transcription_id,
        leaf_ref=leaf_ref,
    )


def is_runtime_resolvable_leaf_ref(leaf_ref: str) -> bool:
    """True only for leaf kinds tooling may mint after startup."""
    leaf = str(leaf_ref or "").strip()
    if not leaf:
        return False
    if leaf == "transcript_edit:working":
        return True
    if _WORKING_REV_LEAF_RE.fullmatch(leaf):
        return True
    if leaf.startswith(_IMAGE_DERIVED_PREFIX):
        opaque = leaf[len(_IMAGE_DERIVED_PREFIX) :]
        if not opaque or "/" in opaque or "\\" in opaque or ".." in opaque:
            return False
        return bool(_DERIVED_OPAQUE_RE.fullmatch(opaque))
    return False


def resolve_runtime_qualified_ref(
    *,
    ref_index: DossierArtifactRefIndex,
    qualified_ref: str,
) -> DossierArtifactRefTarget:
    """Strictly resolve a runtime-minted qualified ref against topology run bindings."""
    target = parse_dossier_qualified_ref(qualified_ref)
    if not ref_index.has_run(target.segment_id, target.transcription_id):
        raise DossierArtifactRefError(
            "dossier_ref_run_not_in_topology",
            f"{target.segment_id}:{target.transcription_id}",
        )
    leaf = target.leaf_ref
    if leaf == "transcript_edit:working":
        return target
    if leaf.startswith("transcript_edit:working:rev:"):
        if parse_working_revision_ref(leaf) is None:
            raise DossierArtifactRefError("dossier_base_revision_invalid", leaf)
        return target
    if leaf.startswith(_IMAGE_DERIVED_PREFIX):
        if not is_runtime_resolvable_leaf_ref(leaf):
            raise DossierArtifactRefError("dossier_ref_invalid", leaf)
        return target
    raise DossierArtifactRefError("dossier_ref_kind_not_runtime_resolvable", leaf)


def build_dossier_artifact_ref_index(
    *,
    dossier_id: str,
    topology_fingerprint: str,
    entries: Mapping[str, DossierArtifactRefTarget]
    | Sequence[tuple[str, DossierArtifactRefTarget]],
    run_bindings: Sequence[tuple[str, str]] | frozenset[tuple[str, str]],
) -> DossierArtifactRefIndex:
    """Build an immutable index bound to dossier lineage and topology run bindings."""
    did = _require_bound_identity(dossier_id, field="dossier_id")
    fingerprint = _require_bound_identity(topology_fingerprint, field="topology_fingerprint")
    bindings = _normalize_run_bindings(run_bindings)

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
        if (target.segment_id, target.transcription_id) not in bindings:
            raise DossierArtifactRefError(
                "dossier_ref_run_not_in_topology",
                f"{target.segment_id}:{target.transcription_id}",
            )
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
        run_bindings=bindings,
    )


def _normalize_run_bindings(
    run_bindings: Sequence[tuple[str, str]] | frozenset[tuple[str, str]],
) -> frozenset[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for item in run_bindings:
        if not isinstance(item, tuple) or len(item) != 2:
            raise DossierArtifactRefError("invalid_run_binding", repr(item))
        sid = _require_ref_identity(item[0], field="segment_id")
        tid = _require_ref_identity(item[1], field="transcription_id")
        out.add((sid, tid))
    return frozenset(out)


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
