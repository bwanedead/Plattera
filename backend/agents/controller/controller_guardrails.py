"""Controller loop split module (Pass 6)."""

from __future__ import annotations

import json
import hashlib
import logging
import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from time import time
from typing import Any, Callable, Mapping, Protocol
from uuid import uuid4

from config.paths import agent_kernel_artifacts_root, dossiers_feature_graphs_artifacts_root
from feature_graph.operations import get_supported_operations, get_unsupported_operations

from agent_kernel.models import (
    ActionType,
    KernelRefusal,
    KernelSessionStartRequest,
    KernelSessionStartResult,
    KernelStepRequest,
    KernelStepResult,
    StepExecutionState,
    StopReason,
    TerminalOutcome,
    TerminalOutcomeKind,
)
from agent_kernel.session import KernelSessionManager

from .contracts import (
    DeclareDoneJustification,
    KernelStepProposal,
    action_tool_specs_for_menu,
    action_how_to_guide,
    coerce_action_type,
    tool_cheatsheet_entries,
    validate_action_args,
)
from .prompting import (
    build_developer_message,
    build_refusal_repair_user_message,
    build_repair_user_message,
    build_user_message,
)
from .retrieval_intents import classify_retrieval_degradation, map_retrieval_intent_to_inputs
from .tool_specs import ToolSpec
from .bootstrap import load_transcript_span_seeds_for_mapping, materialize_seed_spans_from_text

_MAX_CONTROLLER_INPUT_BYTES = 4096
_MAX_EVENTS = 200
_MAX_EVENT_CHARS = 2000
_MAX_TOTAL_BYTES = 262144
_MAX_ERROR_CHARS = 1000
_MAX_TRACE_ITEMS = 8
_MAX_PLAN_BULLETS = 8
_MAX_GAP_KINDS = 8
_MAX_REASON_CODES = 8
_MAX_REFUSAL_STREAK = 3
_RUN_SUMMARY_EVERY_EXECUTED_STEPS = 5
_MAX_HINT_FILE_BYTES = 65536
_MAX_HINT_READ_BYTES = 32768
_RUN_SUMMARY_LOG_MAX_BYTES = 24576
_RUN_SUMMARY_LOG_MAX_ENTRIES = 40
_MAX_DISPLAY_DELTA_CHARS = 220

logger = logging.getLogger(__name__)


def _bounded_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return f"{value[: max_chars - 14]}...[truncated]"


def _bound_payload(value: object, *, max_items: int = 24) -> object:
    if isinstance(value, str):
        return _bounded_text(value, _MAX_EVENT_CHARS)
    if isinstance(value, list):
        trimmed = value[:max_items]
        return [_bound_payload(v, max_items=max_items) for v in trimmed]
    if isinstance(value, dict):
        out: dict[str, object] = {}
        for idx, (key, val) in enumerate(value.items()):
            if idx >= max_items:
                break
            out[str(key)] = _bound_payload(val, max_items=max_items)
        return out
    return value


def _latest_refs_summary(dashboard: dict[str, object]) -> dict[str, object]:
    latest_refs = dashboard.get("latest_refs")
    if not isinstance(latest_refs, dict):
        return {}
    summary: dict[str, object] = {}
    for key, value in latest_refs.items():
        if isinstance(value, dict):
            artifact_path = value.get("artifact_path")
            if isinstance(artifact_path, str) and artifact_path:
                summary[key] = artifact_path
    return summary


def _read_str(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    v = raw.strip()
    return v if v else None


def _compute_controller_idempotency_key(
    *,
    session_id: str,
    iteration: int,
    action_type: str,
    inputs: dict[str, object],
) -> str:
    normalized = json.dumps(inputs, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(
        f"{session_id}|{iteration}|{action_type}|{normalized}".encode("utf-8")
    ).hexdigest()[:24]
    return f"ctl-{digest}"


def _update_refusal_streak(
    *,
    refusal_streak: int,
    previous_signature: str | None,
    reason_code: str,
    action_type: str,
    args: dict[str, object],
) -> tuple[int, str]:
    key_signature = _refusal_signature(reason_code=reason_code, action_type=action_type, args=args)
    if previous_signature == key_signature:
        return refusal_streak + 1, key_signature
    return 1, key_signature


def _refusal_signature(*, reason_code: str, action_type: str, args: dict[str, object]) -> str:
    arg_keys = sorted(args.keys())
    material = _material_change_fingerprint(action_type=action_type, args=args)
    return f"{reason_code}|{action_type}|{','.join(arg_keys)}|{material}"


def _material_change_fingerprint(*, action_type: str, args: dict[str, object]) -> str:
    action = action_type.strip().lower()
    if action == ActionType.RETRIEVE_EVIDENCE.value:
        query = _normalize_for_fingerprint(args.get("query"))
        if query:
            return f"query:{hashlib.sha256(query.encode('utf-8')).hexdigest()[:12]}"
    if action == ActionType.OPEN_ARTIFACT.value:
        ref_value = (
            _normalize_for_fingerprint(args.get("artifact_ref"))
            or _normalize_for_fingerprint(args.get("artifact_path"))
            or _normalize_for_fingerprint(args.get("corpus_entry_ref"))
        )
        if ref_value:
            return f"ref:{hashlib.sha256(ref_value.encode('utf-8')).hexdigest()[:12]}"
    return "static"


def _normalize_for_fingerprint(raw: object) -> str:
    if not isinstance(raw, str):
        return ""
    return " ".join(raw.split()).strip()[:256]


def _infer_phase_hint(dashboard: dict[str, object]) -> str:
    latest_refs = _latest_refs_summary(dashboard)
    claimability = dashboard.get("claimability")
    claimable_ready = False
    if isinstance(claimability, dict):
        claimable_ready = bool(claimability.get("claimable_ready"))
    if claimable_ready:
        return "declare_candidate"
    if not latest_refs.get("ir_ref"):
        return "author_ir"
    if not latest_refs.get("compile_ref") or not latest_refs.get("judge_ref"):
        return "verify"
    return "declare_candidate"


def _ir_health_from_hint(ir_hint: dict[str, object], ir_ref: object) -> dict[str, object]:
    node_count = ir_hint.get("node_count")
    is_stub = bool(isinstance(node_count, int) and node_count == 0)
    has_structured_plss_anchor = bool(ir_hint.get("has_structured_plss_anchor") is True)
    has_local_polygon_geometry = bool(ir_hint.get("has_local_polygon_geometry") is True)
    parcel_audit = ir_hint.get("parcel_audit") if isinstance(ir_hint.get("parcel_audit"), dict) else {}
    return {
        "node_count": node_count if isinstance(node_count, int) else None,
        "edge_count": None,
        "is_stub": is_stub,
        "has_structured_plss_anchor": has_structured_plss_anchor,
        "has_local_polygon_geometry": has_local_polygon_geometry,
        "parcel_audit": parcel_audit,
        "last_ir_artifact_ref": ir_ref if isinstance(ir_ref, str) else None,
    }


def _controller_ir_parcel_audit(nodes: object) -> dict[str, int]:
    if not isinstance(nodes, list):
        return {"complete_region_count": 0, "partial_annotation_stub_count": 0}
    complete_regions = 0
    partial_annotation_stubs = 0
    for node in nodes:
        if not isinstance(node, dict):
            continue
        kind = str(node.get("kind") or "").strip().lower()
        label = str(node.get("label") or "").lower()
        meta = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
        texts: list[str] = [label]
        for value in meta.values():
            if isinstance(value, str):
                texts.append(value.lower())
            elif isinstance(value, list):
                texts.extend(str(item).lower() for item in value if isinstance(item, str))
        joined = " ".join(texts)
        if kind == "region":
            complete_regions += 1
        if kind == "annotation" and any(tok in joined for tok in ("parcel", "stub", "truncated", "partial", "incomplete")):
            partial_annotation_stubs += 1
    return {
        "complete_region_count": complete_regions,
        "partial_annotation_stub_count": partial_annotation_stubs,
    }


def _controller_ir_has_local_polygon_geometry(nodes: object) -> bool:
    if not isinstance(nodes, list):
        return False
    for node in nodes:
        if not isinstance(node, dict):
            continue
        kind = str(node.get("kind") or "").strip().lower()
        geometry = node.get("geometry")
        if not isinstance(geometry, dict):
            continue
        gtype = str(geometry.get("type") or "").strip()
        if kind == "region" and gtype == "Polygon":
            coords = geometry.get("coordinates")
            if isinstance(coords, list) and coords and isinstance(coords[0], list) and len(coords[0]) >= 4:
                return True
        if kind == "curve" and gtype == "LineString":
            coords = geometry.get("coordinates")
            if (
                isinstance(coords, list)
                and len(coords) >= 4
                and isinstance(coords[0], list)
                and isinstance(coords[-1], list)
                and len(coords[0]) >= 2
                and len(coords[-1]) >= 2
                and coords[0][0] == coords[-1][0]
                and coords[0][1] == coords[-1][1]
            ):
                return True
    return False


def _controller_ir_has_required_plss_anchor(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    required = (
        "state",
        "township_number",
        "township_direction",
        "range_number",
        "range_direction",
        "section_number",
    )
    return all(value.get(k) is not None for k in required)


def _judge_excerpt_from_hint(judge_hint: dict[str, object]) -> dict[str, object]:
    out: dict[str, object] = {"top_gaps": [], "warnings": []}
    top_gaps = judge_hint.get("top_gaps")
    if isinstance(top_gaps, list):
        out["top_gaps"] = _bound_payload(top_gaps, max_items=4)
    warnings = judge_hint.get("warnings")
    if isinstance(warnings, list):
        out["warnings"] = [str(w)[:160] for w in warnings[:3]]
    return out


def _recommended_next_moves(progress_payload: dict[str, object]) -> list[str]:
    latest_refs = progress_payload.get("latest_refs")
    if not isinstance(latest_refs, dict):
        return []
    map_sanity = progress_payload.get("map_sanity_excerpt")
    if isinstance(map_sanity, dict):
        validate_top_issues = map_sanity.get("validate_top_issues")
        issues = [str(v).lower() for v in validate_top_issues] if isinstance(validate_top_issues, list) else []
        if any("section_centroid_anchor_fallback" in item for item in issues):
            return [
                "open_text_spans for the deed's POB tie language and encode an explicit tie_to_corner instead of centroid fallback",
                "re-georeference, validate, and render after replacing centroid fallback anchoring",
            ]
        if any("placeholder_geometry" in item for item in issues):
            return [
                "draft_ir update: replace placeholder parcel geometry with deed-faithful traverse/closed boundary before georeference",
                "re-compile, judge, bundle, georeference, validate, render",
            ]
        if any("unresolved_tie_to_corner" in item for item in issues):
            return [
                "open_text_spans for tie-to-corner language and encode tie_to_corner on the mapped parcel/POB metadata",
                "re-georeference, validate, and render after tie is explicit",
            ]
    ir_health = progress_payload.get("ir_health")
    if isinstance(ir_health, dict) and ir_health.get("is_stub") is True:
        return [
            "draft_ir with graph (non-empty FeatureGraph) before compile/judge",
            "use open_text_spans to extract deed calls, then encode nodes/op_expr",
        ]
    if latest_refs.get("ir_ref") and not latest_refs.get("compile_ref"):
        return ["run compile on latest ir_ref before more inspection", "then judge to refresh actionable gaps"]
    if latest_refs.get("compile_ref") and not latest_refs.get("judge_ref"):
        return ["run judge on latest compile/ir state to refresh gaps", "inspect judge repair_view/top gaps after judge"]
    gap_summary = progress_payload.get("gap_summary")
    if latest_refs.get("judge_ref") and isinstance(gap_summary, dict):
        counts = gap_summary.get("gap_counts_by_kind")
        total_gaps = 0
        if isinstance(counts, dict):
            for value in counts.values():
                try:
                    total_gaps += int(value)
                except Exception:
                    continue
        if total_gaps == 0:
            claimability = progress_payload.get("claimability")
            missing_claimability = (
                claimability.get("missing_claimability")
                if isinstance(claimability, dict) and isinstance(claimability.get("missing_claimability"), list)
                else []
            )
            ir_health = progress_payload.get("ir_health")
            has_structured_plss_anchor = bool(
                isinstance(ir_health, dict) and ir_health.get("has_structured_plss_anchor") is True
            )
            local_polygon_missing_known = bool(
                isinstance(ir_health, dict) and ir_health.get("has_local_polygon_geometry") is False
            )
            if latest_refs.get("bundle_ref") and latest_refs.get("georef_ref") and latest_refs.get("validate_ref"):
                if "has_render" in missing_claimability and not latest_refs.get("render_ref"):
                    return ["run render on latest georef_ref to produce a visual map preview", "then declare_done if claimability clears"]
                return ["declare_done with justification if semantics are satisfied"]
            if (
                latest_refs.get("bundle_ref")
                and ("has_georef" in missing_claimability)
                and local_polygon_missing_known
            ):
                return [
                    "draft_ir update: add explicit local parcel polygon geometry (region Polygon or closed LineString ring)",
                    "re-bundle, then georeference and validate",
                ]
            if (
                latest_refs.get("bundle_ref")
                and ("has_georef" in missing_claimability)
                and not has_structured_plss_anchor
            ):
                return [
                    "draft_ir update: add structured plss_anchor to FRAME.metadata.plss_anchor or graph.metadata.plss_anchor",
                    "re-bundle, then georeference and validate",
                ]
            if latest_refs.get("bundle_ref") and ("has_georef" in missing_claimability or "validation_passed" in missing_claimability):
                return ["run georeference on latest bundle, then validate", "declare_done only after georef/validate claimability clears"]
            if latest_refs.get("bundle_ref") and not latest_refs.get("georef_ref"):
                return ["run georeference on latest bundle", "then validate and consider declare_done"]
            if latest_refs.get("georef_ref") and not latest_refs.get("validate_ref"):
                return ["run validate on latest georef_ref", "then consider declare_done if claimability clears"]
            if latest_refs.get("georef_ref") and latest_refs.get("validate_ref") and ("has_render" in missing_claimability):
                return ["run render on latest georef_ref", "then consider declare_done if claimability clears"]
            if latest_refs.get("bundle_ref"):
                return ["declare_done with justification if semantics are satisfied"]
            return ["bundle latest graph artifacts, then georeference/validate if required"]
    if latest_refs.get("judge_ref"):
        return ["inspect judge_report_excerpt/top gaps, then revise IR graph", "compile and judge immediately after each IR change"]
    if latest_refs.get("ir_ref"):
        return ["run compile then judge on latest ir_ref"]
    return ["draft_ir with graph (non-empty FeatureGraph)"]


def _map_sanity_excerpt_from_hints(
    georef_hint: dict[str, object] | None,
    validate_hint: dict[str, object] | None,
) -> dict[str, object]:
    out: dict[str, object] = {}
    if isinstance(georef_hint, dict):
        for key in (
            "success",
            "bounds",
            "pob",
            "pob_method",
            "vertex_count",
            "plss_state",
            "placeholder_geometry_detected",
            "explicit_tie_reference_detected",
            "tie_to_corner_provided",
        ):
            if key in georef_hint:
                out[key] = georef_hint.get(key)
    if isinstance(validate_hint, dict):
        for key in ("passed", "reason_code", "overall_accuracy", "top_issues"):
            if key in validate_hint:
                out[f"validate_{key}" if key not in {"passed", "top_issues"} else ("validate_passed" if key == "passed" else "validate_top_issues")] = validate_hint.get(key)
    return out


def _inspection_thrash_refusal(
    *,
    action_type: ActionType,
    step_inputs: dict[str, object],
    repeated_inspection_ref: str | None,
    repeated_inspection_count: int,
) -> tuple[KernelRefusal, str] | None:
    if action_type != ActionType.OPEN_ARTIFACT:
        return None
    artifact_ref = _read_str(step_inputs.get("artifact_ref")) or _read_str(step_inputs.get("artifact_path"))
    if not artifact_ref:
        return None
    if artifact_ref != repeated_inspection_ref:
        return None
    if repeated_inspection_count < 1:
        return None
    return (
        KernelRefusal(
            reason_code="repeated_inspection_no_progress",
            missing_inputs=[],
            retryable=True,
        ),
        artifact_ref,
    )


def _span_open_thrash_refusal(
    *,
    action_type: ActionType,
    step_inputs: dict[str, object],
    repeated_signature: str | None,
    repeated_count: int,
) -> tuple[KernelRefusal, str] | None:
    if action_type != ActionType.OPEN_TEXT_SPANS:
        return None
    signature = _open_text_spans_signature(step_inputs)
    if not signature:
        return None
    if signature != repeated_signature:
        return None
    if repeated_count < 1:
        return None
    return (
        KernelRefusal(
            reason_code="repeated_span_open_no_progress",
            missing_inputs=[],
            retryable=True,
        ),
        signature,
    )


def _semantic_span_repair_signature_for_context(context_packet: Mapping[str, object]) -> str | None:
    progress = context_packet.get("progress")
    if not isinstance(progress, Mapping):
        return None
    latest_refs = progress.get("latest_refs")
    if not isinstance(latest_refs, Mapping):
        return None
    ir_ref = _read_str(latest_refs.get("ir_ref"))
    validate_ref = _read_str(latest_refs.get("validate_ref"))
    if not ir_ref or not validate_ref:
        return None
    map_sanity = progress.get("map_sanity_excerpt")
    if not isinstance(map_sanity, Mapping):
        return None
    raw_issues = map_sanity.get("validate_top_issues")
    if not isinstance(raw_issues, list):
        return None
    issues = sorted(
        {
            str(item).strip().lower()
            for item in raw_issues
            if isinstance(item, str)
            and (
                "section_centroid_anchor_fallback" in item.lower()
                or "unresolved_tie_to_corner" in item.lower()
            )
        }
    )
    if not issues:
        return None
    deed_span_index_ref = _read_str(latest_refs.get("deed_span_index_ref"))
    payload = {"ir_ref": ir_ref, "validate_ref": validate_ref, "issues": issues, "deed_span_index_ref": deed_span_index_ref}
    try:
        return json.dumps(payload, sort_keys=True, ensure_ascii=True)
    except Exception:
        return str(payload)


def _semantic_span_repair_thrash_refusal(
    *,
    action_type: ActionType,
    context_packet: Mapping[str, object],
    repeated_signature: str | None,
    repeated_count: int,
) -> tuple[KernelRefusal, str] | None:
    if action_type != ActionType.OPEN_TEXT_SPANS:
        return None
    signature = _semantic_span_repair_signature_for_context(context_packet)
    if not signature or signature != repeated_signature:
        return None
    if repeated_count < 2:
        return None
    return (
        KernelRefusal(
            reason_code="semantic_repair_span_loop_no_progress",
            missing_inputs=[],
            retryable=True,
        ),
        signature,
    )


def _open_text_spans_signature(step_inputs: Mapping[str, object]) -> str | None:
    sig_payload: dict[str, object] = {}
    for key in (
        "deed_text_artifact_ref",
        "artifact_ref",
        "deed_span_index_ref",
        "start_char",
        "end_char",
        "max_chars",
        "span_ids",
        "spans",
        "anchors",
    ):
        if key in step_inputs:
            sig_payload[key] = step_inputs.get(key)
    if not sig_payload:
        return None
    try:
        return json.dumps(sig_payload, sort_keys=True, ensure_ascii=True)
    except Exception:
        return str(sig_payload)


def _redundant_deterministic_step_refusal(
    *,
    action_type: ActionType,
    dashboard: dict[str, object],
) -> tuple[KernelRefusal, ActionType | None] | None:
    latest_refs = _latest_refs_summary(dashboard)
    if action_type == ActionType.COMPILE and latest_refs.get("compile_ref"):
        next_action = ActionType.JUDGE if not latest_refs.get("judge_ref") else None
        return (
            KernelRefusal(
                reason_code="compile_already_current",
                missing_inputs=[],
                retryable=True,
            ),
            next_action,
        )
    if action_type == ActionType.JUDGE and latest_refs.get("judge_ref"):
        next_action = ActionType.BUNDLE if not latest_refs.get("bundle_ref") else None
        return (
            KernelRefusal(
                reason_code="judge_already_current",
                missing_inputs=[],
                retryable=True,
            ),
            next_action,
        )
    return None


def _inspection_thrash_suggested_next_action(dashboard: dict[str, object]) -> ActionType | None:
    latest_refs = _latest_refs_summary(dashboard)
    if latest_refs.get("ir_ref") and not latest_refs.get("compile_ref"):
        return ActionType.COMPILE
    if latest_refs.get("compile_ref") and not latest_refs.get("judge_ref"):
        return ActionType.JUDGE
    if latest_refs.get("judge_ref"):
        return ActionType.DRAFT_IR
    return None


def _semantic_span_repair_thrash_suggested_next_action(dashboard: dict[str, object]) -> ActionType | None:
    latest_refs = _latest_refs_summary(dashboard)
    if not latest_refs.get("deed_span_index_ref"):
        return ActionType.UPSERT_DEED_SPAN_INDEX
    return ActionType.DRAFT_IR


def _span_open_thrash_suggested_next_action(dashboard: dict[str, object]) -> ActionType | None:
    latest_refs = _latest_refs_summary(dashboard)
    if not latest_refs.get("deed_span_index_ref"):
        return ActionType.UPSERT_DEED_SPAN_INDEX
    if latest_refs.get("ir_ref"):
        return ActionType.DRAFT_IR
    return ActionType.OPEN_ARTIFACT


def _build_parse_failure_resync_proposal(
    *,
    iteration: int,
    observation: dict[str, object],
) -> KernelStepProposal | None:
    progress = observation.get("progress")
    if not isinstance(progress, dict):
        return None
    latest_refs = progress.get("latest_refs")
    if not isinstance(latest_refs, dict):
        return None
    artifact_ref = None
    for key in ("judge_ref", "compile_ref", "ir_ref"):
        candidate = latest_refs.get(key)
        if isinstance(candidate, str) and candidate.strip():
            artifact_ref = candidate.strip()
            break
    if artifact_ref is None:
        return None
    return KernelStepProposal(
        action_type=ActionType.OPEN_ARTIFACT.value,
        args={"artifact_ref": artifact_ref},
        idempotency_key=f"controller-parse-resync-{iteration}",
        why="controller parse-fail resync: inspect latest artifact for actionable feedback",
        iteration_summary={
            "action": "propose:open_artifact; observed_last:parse_failed",
            "actual_observation": "parse_failed(controller_parse_failed); need deterministic resync",
            "expected_observation": "next iteration will have a bounded artifact repair view or summary",
            "next_move": {"action_type": "open_artifact", "why": "recover context after parse failure"},
            "confidence": "low",
        },
    )


def _anchor_templates_for_deed(bootstrap_context: dict[str, object]) -> list[dict[str, str]]:
    if not isinstance(bootstrap_context.get("deed_text_excerpt"), str):
        return []
    return [
        {"label": "metes_bounds_calls", "start_anchor": "BEGINNING AT", "end_anchor": "POINT OF BEGINNING"},
        {"label": "metes_bounds_calls_alt", "start_anchor": "Beginning at", "end_anchor": "point of beginning"},
        {"label": "exception_clause", "start_anchor": "EXCEPTING", "end_anchor": "TOGETHER WITH"},
    ]


def _quality_gate_refusal_for_step_result(
    *,
    action_type: ActionType,
    step_result: KernelStepResult,
    bootstrap_context: dict[str, object],
) -> dict[str, object] | None:
    from .controller_context import _safe_artifact_hint

    if action_type != ActionType.DRAFT_IR:
        return None
    if step_result.execution_state != StepExecutionState.EXECUTED or step_result.refusal is not None:
        return None
    latest_refs = _latest_refs_summary(step_result.dashboard.model_dump(mode="json"))
    ir_ref = latest_refs.get("ir_ref")
    if not isinstance(ir_ref, str) or not ir_ref:
        return None
    ir_hint = _safe_artifact_hint(ir_ref, kind="ir")
    if not isinstance(ir_hint, dict):
        return None
    node_count = ir_hint.get("node_count")
    if not isinstance(node_count, int) or node_count > 0:
        return None
    refusal = KernelRefusal(
        reason_code="draft_ir_graph_empty",
        missing_inputs=["graph.nodes[0]"],
        retryable=True,
    )
    return {
        "refusal": refusal,
        "quality_gate": {
            "kind": "ir_health",
            "reason_code": "draft_ir_graph_empty",
            "ir_ref": ir_ref,
            "ir_hint": _bound_payload(ir_hint, max_items=8),
            "message": "draft_ir produced an empty graph; next attempt must include graph with at least one node",
        },
    }


def _encoded_size_bytes(events: list[dict[str, object]]) -> int:
    return len(json.dumps({"events": events}, ensure_ascii=True).encode("utf-8"))
