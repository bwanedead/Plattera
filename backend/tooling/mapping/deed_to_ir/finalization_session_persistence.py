"""Persistence and lifecycle for deed-to-IR finalization sessions.

Stored under the same dossier / transcription / workspace identity as
``current_mapping_lineage.json``. Successful remaps replace the session; newer
IR writes mark it stale. Decisions never migrate across lineages.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .dependency_candidates_projection import project_known_dependency_candidates
from .finalization_scope_inventory import project_finalization_scope_inventory
from .finalization_session import (
    SCHEMA_VERSION,
    build_pending_finalization_session,
    compact_finalization_session_for_prompt,
    mark_session_stale,
)
from .persistence_io import atomic_write_json, read_json, resolve_workspace_key, utc_now_iso
from .paths import UnsafeDeedToIrPathSegmentError, deed_to_ir_finalization_session_path


def build_finalization_session_for_mapping_submission(
    *,
    mapping_artifact_ref: str,
    source_ir_artifact_ref: str,
    ir_graph: Mapping[str, Any] | Any | None = None,
    mapping_artifact: Mapping[str, Any] | Any | None = None,
    correction_posture: Mapping[str, Any] | None = None,
    resolution_state_snapshot: Mapping[str, Any] | None = None,
    issues: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble a fresh pending session for one successful mapping submission."""
    correction_candidates = _correction_candidates_from_posture(correction_posture)
    dependency_projection = project_known_dependency_candidates(
        resolution_state_snapshot=resolution_state_snapshot
        if isinstance(resolution_state_snapshot, Mapping)
        else None,
        issues=issues,
    )
    dependency_candidates = list(dependency_projection.get("candidates") or [])
    dependency_diagnostics = list(dependency_projection.get("diagnostics") or [])
    inventory = project_finalization_scope_inventory(
        ir_graph=ir_graph,
        mapping_artifact=mapping_artifact,
        correction_candidates=correction_candidates,
        dependency_candidates=dependency_candidates,
        resolution_state_snapshot=resolution_state_snapshot
        if isinstance(resolution_state_snapshot, Mapping)
        else None,
    )
    diagnostics = [
        *list(inventory.get("diagnostics") or []),
        *dependency_diagnostics,
    ]
    return build_pending_finalization_session(
        mapping_artifact_ref=mapping_artifact_ref,
        source_ir_artifact_ref=source_ir_artifact_ref,
        scope_ids=list(inventory.get("scope_ids") or []),
        correction_candidates=correction_candidates,
        dependency_candidates=dependency_candidates,
        diagnostics=diagnostics,
    )


def write_finalization_session(
    *,
    dossier_id: str,
    transcription_id: str | None,
    workspace_id: str | None,
    run_id: str | None,
    session: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Persist the current finalization session sidecar. Returns None when scope missing."""
    workspace_key = resolve_workspace_key(workspace_id=workspace_id, run_id=run_id)
    tid = str(transcription_id or "").strip()
    if not workspace_key or not tid or not dossier_id:
        return None
    try:
        path = deed_to_ir_finalization_session_path(dossier_id, tid, workspace_key)
    except UnsafeDeedToIrPathSegmentError:
        return None
    payload = dict(session)
    payload.setdefault("schema_version", SCHEMA_VERSION)
    payload["updated_at"] = utc_now_iso()
    atomic_write_json(path, payload)
    return payload


def read_finalization_session(
    *,
    dossier_id: str,
    transcription_id: str | None,
    workspace_id: str | None,
    run_id: str | None,
) -> dict[str, Any] | None:
    workspace_key = resolve_workspace_key(workspace_id=workspace_id, run_id=run_id)
    tid = str(transcription_id or "").strip()
    if not workspace_key or not tid or not dossier_id:
        return None
    try:
        path = deed_to_ir_finalization_session_path(dossier_id, tid, workspace_key)
    except UnsafeDeedToIrPathSegmentError:
        return None
    raw = read_json(path)
    return raw if isinstance(raw, dict) else None


def replace_finalization_session_for_mapping_submission(
    *,
    dossier_id: str,
    transcription_id: str | None,
    workspace_id: str | None,
    run_id: str | None,
    mapping_artifact_ref: str,
    source_ir_artifact_ref: str,
    ir_graph: Mapping[str, Any] | Any | None = None,
    mapping_artifact: Mapping[str, Any] | Any | None = None,
    correction_posture: Mapping[str, Any] | None = None,
    resolution_state_snapshot: Mapping[str, Any] | None = None,
    issues: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Replace any prior session with one bound to this exact mapping/IR lineage."""
    session = build_finalization_session_for_mapping_submission(
        mapping_artifact_ref=mapping_artifact_ref,
        source_ir_artifact_ref=source_ir_artifact_ref,
        ir_graph=ir_graph,
        mapping_artifact=mapping_artifact,
        correction_posture=correction_posture,
        resolution_state_snapshot=resolution_state_snapshot,
        issues=issues,
    )
    return write_finalization_session(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        run_id=run_id,
        session=session,
    )


def mark_finalization_session_stale_for_ir_write(
    *,
    dossier_id: str,
    transcription_id: str | None,
    workspace_id: str | None,
    run_id: str | None,
    new_ir_artifact_ref: str,
) -> dict[str, Any] | None:
    """Mark the pending session stale after a newer IR save/patch."""
    existing = read_finalization_session(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        run_id=run_id,
    )
    if existing is None:
        return None
    new_ir = str(new_ir_artifact_ref or "").strip()
    lineage = existing.get("lineage") if isinstance(existing.get("lineage"), Mapping) else {}
    prior_ir = str(lineage.get("source_ir_artifact_ref") or "").strip()
    if not new_ir or new_ir == prior_ir:
        return existing
    stale = mark_session_stale(existing, new_ir_artifact_ref=new_ir)
    return write_finalization_session(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        run_id=run_id,
        session=stale,
    )


def compact_active_finalization_session_for_prompt(
    *,
    dossier_id: str,
    transcription_id: str | None,
    workspace_id: str | None,
    run_id: str | None,
) -> dict[str, Any] | None:
    """Read + compact pending session for prompt projection (no persistence mutation)."""
    session = read_finalization_session(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        run_id=run_id,
    )
    return compact_finalization_session_for_prompt(session)


def _correction_candidates_from_posture(
    correction_posture: Mapping[str, Any] | None,
) -> list[Mapping[str, Any]]:
    if not isinstance(correction_posture, Mapping):
        return []
    if not correction_posture.get("active"):
        return []
    deltas = correction_posture.get("candidate_deltas")
    if not isinstance(deltas, list):
        return []
    return [row for row in deltas if isinstance(row, Mapping)]
