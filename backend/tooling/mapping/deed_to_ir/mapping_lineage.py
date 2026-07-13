"""Domain-owned current mapping lineage for intent-first deed-to-IR preview.

Promotes submit ``lineage_lock`` into a persisted workspace sidecar. Deterministic
code carries mechanical refs and stale flags only — never semantic readiness.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .persistence_io import atomic_write_json, read_json, refusal, resolve_workspace_key, utc_now_iso
from .paths import UnsafeDeedToIrPathSegmentError, deed_to_ir_current_mapping_lineage_path

SCHEMA_VERSION = "1.0"
STALE_REASON_IR_REVISION_WITHOUT_REMAP = "ir_revision_without_remap"


def build_current_mapping_lineage(
    *,
    mapping_artifact_ref: str,
    source_ir_artifact_ref: str,
    compile_gap_count: int | None = None,
    judge_gap_count: int | None = None,
    correction_posture: Mapping[str, Any] | None = None,
    lineage_current: bool = True,
    use_for_next_preview: bool | None = None,
) -> dict[str, Any]:
    """Build the canonical current-mapping-lineage projection from a successful remap."""
    mapping_ref = str(mapping_artifact_ref or "").strip()
    ir_ref = str(source_ir_artifact_ref or "").strip()
    current = bool(lineage_current) and bool(mapping_ref) and bool(ir_ref)
    use_preview = use_for_next_preview if use_for_next_preview is not None else current
    lineage: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": utc_now_iso(),
        "mapping_artifact_ref": mapping_ref,
        "source_ir_artifact_ref": ir_ref,
        "lineage_current": current,
        "use_for_next_preview": bool(use_preview) and current,
        "stale": not current,
        "stale_reason": None if current else STALE_REASON_IR_REVISION_WITHOUT_REMAP,
    }
    if compile_gap_count is not None:
        lineage["compile_gap_count"] = int(compile_gap_count)
    if judge_gap_count is not None:
        lineage["judge_gap_count"] = int(judge_gap_count)
    if isinstance(correction_posture, Mapping) and correction_posture:
        lineage["correction_posture"] = {
            "active": bool(correction_posture.get("active")),
            "candidate_delta_count": len(correction_posture.get("candidate_deltas") or []),
            "reason_codes": list(correction_posture.get("reason_codes") or []),
        }
    return lineage


def lineage_lock_from_current(lineage: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Compatibility projection matching submit ``lineage_lock`` shape."""
    if not isinstance(lineage, Mapping) or not lineage:
        return None
    mapping_ref = str(lineage.get("mapping_artifact_ref") or "").strip()
    ir_ref = str(lineage.get("source_ir_artifact_ref") or "").strip()
    if not mapping_ref or not ir_ref:
        return None
    return {
        "source_ir_artifact_ref": ir_ref,
        "mapping_artifact_ref": mapping_ref,
        "use_these_refs_for_next_preview": bool(lineage.get("use_for_next_preview")),
    }


def compact_current_mapping_lineage_for_projection(
    lineage: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(lineage, Mapping) or not lineage:
        return None
    compact: dict[str, Any] = {
        "mapping_artifact_ref": lineage.get("mapping_artifact_ref"),
        "source_ir_artifact_ref": lineage.get("source_ir_artifact_ref"),
        "lineage_current": bool(lineage.get("lineage_current")),
        "use_for_next_preview": bool(lineage.get("use_for_next_preview")),
        "stale": bool(lineage.get("stale")),
    }
    if lineage.get("stale_reason"):
        compact["stale_reason"] = lineage.get("stale_reason")
    if lineage.get("compile_gap_count") is not None:
        compact["compile_gap_count"] = lineage.get("compile_gap_count")
    if lineage.get("judge_gap_count") is not None:
        compact["judge_gap_count"] = lineage.get("judge_gap_count")
    posture = lineage.get("correction_posture")
    if isinstance(posture, Mapping) and posture:
        compact["correction_posture"] = dict(posture)
    return compact


def render_current_mapping_lineage_timeline_lines(
    lineage: Mapping[str, Any] | None,
    *,
    indent: str = "  ",
) -> list[str]:
    if not isinstance(lineage, Mapping) or not lineage:
        return []
    lines = [f"{indent}current_mapping_lineage:"]
    mapping_ref = lineage.get("mapping_artifact_ref")
    ir_ref = lineage.get("source_ir_artifact_ref")
    if mapping_ref:
        lines.append(f"{indent}  mapping: {mapping_ref}")
    if ir_ref:
        lines.append(f"{indent}  source_ir: {ir_ref}")
    current = bool(lineage.get("lineage_current")) and not bool(lineage.get("stale"))
    if current:
        lines.append(f"{indent}  status: current")
        if lineage.get("use_for_next_preview") is True:
            lines.append(f"{indent}  use_for_next_preview: true")
    else:
        reason = lineage.get("stale_reason") or "superseded"
        lines.append(f"{indent}  status: superseded ({reason})")
        lines.append(f"{indent}  use_for_next_preview: false")
    if lineage.get("compile_gap_count") is not None or lineage.get("judge_gap_count") is not None:
        lines.append(
            f"{indent}  counts: compile_gaps={lineage.get('compile_gap_count', 0)} "
            f"judge_gaps={lineage.get('judge_gap_count', 0)}"
        )
    return lines


def write_current_mapping_lineage(
    *,
    dossier_id: str,
    transcription_id: str | None,
    workspace_id: str | None,
    run_id: str | None,
    lineage: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Persist current mapping lineage beside preview/output. Returns None when scope missing."""
    workspace_key = resolve_workspace_key(workspace_id=workspace_id, run_id=run_id)
    tid = str(transcription_id or "").strip()
    if not workspace_key or not tid or not dossier_id:
        return None
    try:
        path = deed_to_ir_current_mapping_lineage_path(dossier_id, tid, workspace_key)
    except UnsafeDeedToIrPathSegmentError:
        return None
    payload = dict(lineage)
    payload.setdefault("schema_version", SCHEMA_VERSION)
    payload["updated_at"] = utc_now_iso()
    atomic_write_json(path, payload)
    return payload


def read_current_mapping_lineage(
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
        path = deed_to_ir_current_mapping_lineage_path(dossier_id, tid, workspace_key)
    except UnsafeDeedToIrPathSegmentError:
        return None
    raw = read_json(path)
    return raw if isinstance(raw, dict) else None


def mark_current_mapping_lineage_stale_for_ir_write(
    *,
    dossier_id: str,
    transcription_id: str | None,
    workspace_id: str | None,
    run_id: str | None,
    new_ir_artifact_ref: str,
) -> dict[str, Any] | None:
    """Mark prior mapping lineage stale after a newer IR save/patch (intent-first must remap)."""
    existing = read_current_mapping_lineage(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        run_id=run_id,
    )
    if existing is None:
        return None
    new_ir = str(new_ir_artifact_ref or "").strip()
    prior_ir = str(existing.get("source_ir_artifact_ref") or "").strip()
    if not new_ir or new_ir == prior_ir:
        return existing
    stale = dict(existing)
    stale["lineage_current"] = False
    stale["use_for_next_preview"] = False
    stale["stale"] = True
    stale["stale_reason"] = STALE_REASON_IR_REVISION_WITHOUT_REMAP
    stale["superseded_by_ir_artifact_ref"] = new_ir
    stale["updated_at"] = utc_now_iso()
    return write_current_mapping_lineage(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        run_id=run_id,
        lineage=stale,
    )


def resolve_intent_first_mapping_lineage(
    *,
    dossier_id: str,
    transcription_id: str | None,
    workspace_id: str | None,
    run_id: str | None,
) -> dict[str, Any]:
    """Resolve current lineage for intent-first preview, or a retryable refusal payload."""
    lineage = read_current_mapping_lineage(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        run_id=run_id,
    )
    if lineage is None:
        return refusal(
            "current_mapping_lineage_missing",
            "No current mapping lineage is available. Submit IR for mapping, then retry "
            "intent-first prepare with use_current_mapping_lineage=true.",
        )
    if lineage.get("stale") or not lineage.get("lineage_current") or not lineage.get("use_for_next_preview"):
        return {
            **refusal(
                "current_mapping_lineage_stale",
                "Current mapping lineage is stale for intent-first preview. Remap the latest IR, "
                "then retry prepare with use_current_mapping_lineage=true.",
            ),
            "outputs": {
                "current_mapping_lineage": compact_current_mapping_lineage_for_projection(lineage),
            },
        }
    mapping_ref = str(lineage.get("mapping_artifact_ref") or "").strip()
    ir_ref = str(lineage.get("source_ir_artifact_ref") or "").strip()
    if not mapping_ref or not ir_ref:
        return refusal(
            "current_mapping_lineage_incomplete",
            "Current mapping lineage is incomplete (missing mapping or IR ref).",
        )
    return {
        "executed": True,
        "mapping_artifact_ref": mapping_ref,
        "expected_ir_artifact_ref": ir_ref,
        "current_mapping_lineage": lineage,
    }


def annotate_mapping_lineage_freshness(
    *,
    mapping_artifact_ref: str,
    current_lineage: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Mechanical current/superseded marker for a hydrated mapping ref.

    Does not author semantic readiness — only compares the hydrated ref to the
    persisted current mapping lineage sidecar.
    """
    if not isinstance(current_lineage, Mapping) or not current_lineage:
        return None
    current_ref = str(current_lineage.get("mapping_artifact_ref") or "").strip()
    if not current_ref:
        return None
    requested = str(mapping_artifact_ref or "").strip()
    if not requested:
        return None
    lineage_is_current = bool(current_lineage.get("lineage_current")) and not bool(
        current_lineage.get("stale")
    )
    if requested == current_ref and lineage_is_current:
        return {
            "lineage_status": "current",
            "lineage_current": True,
            "current_mapping_artifact_ref": current_ref,
            "current_source_ir_artifact_ref": current_lineage.get("source_ir_artifact_ref"),
        }
    return {
        "lineage_status": "superseded",
        "lineage_current": False,
        "current_mapping_artifact_ref": current_ref,
        "current_source_ir_artifact_ref": current_lineage.get("source_ir_artifact_ref"),
        "superseded_reason": (
            "ir_revision_without_remap"
            if current_lineage.get("stale")
            else "not_current_mapping_lineage"
        ),
    }


def attach_current_mapping_lineage_to_mapping_review(
    mapping_review: dict[str, Any],
    *,
    lineage: Mapping[str, Any],
) -> None:
    """Attach current lineage + compatibility lineage_lock onto mapping_review."""
    compact = compact_current_mapping_lineage_for_projection(lineage)
    if compact is not None:
        mapping_review["current_mapping_lineage"] = compact
    lock = lineage_lock_from_current(lineage)
    if lock is not None:
        mapping_review["lineage_lock"] = lock
    from .active_handoff_projection import build_active_handoff_context

    active = build_active_handoff_context(lineage)
    if active is not None:
        mapping_review["active_handoff_context"] = active
