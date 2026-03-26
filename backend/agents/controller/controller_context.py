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

from .controller_guardrails import (
    _anchor_templates_for_deed,
    _controller_ir_has_local_polygon_geometry,
    _controller_ir_has_required_plss_anchor,
    _controller_ir_parcel_audit,
    _ir_health_from_hint,
    _judge_excerpt_from_hint,
    _map_sanity_excerpt_from_hints,
    _read_str,
    _progress_state_labels,
)
from .controller_transcript import _bound_payload, _bounded_text, _latest_refs_summary

def _build_context_packet(
    *,
    session_id: str,
    tool_menu: list[str],
    bootstrap_context: dict[str, object],
    dashboard: dict[str, object],
    transcript: list[dict[str, object]],
    last_refusal: KernelRefusal | None,
    last_refusal_action_type_raw: str | None,
    last_step_result: KernelStepResult | None,
    run_summary_ref: str | None,
    run_summary_excerpt: str | None,
    phase_hint: str,
    recent_digest_memory: list[dict[str, object]],
) -> dict[str, object]:
    latest_refs = _latest_refs_summary(dashboard)
    recent_trace = _extract_recent_trace(transcript)
    progress = {
        "latest_refs": latest_refs,
        "budgets_remaining": dashboard.get("budgets_remaining", {}),
        "gap_summary": _compact_gap_summary(dashboard.get("gap_summary")),
        "claimability": dashboard.get("claimability", {}),
    }
    packet_inputs = {
        "dossier_id": bootstrap_context.get("dossier_id"),
        "source_entry_ref": bootstrap_context.get("source_entry_ref"),
        "deed_text_excerpt": bootstrap_context.get("deed_text_excerpt"),
        "deed_text_artifact_ref": bootstrap_context.get("deed_text_artifact_ref"),
        "deed_text_full": bootstrap_context.get("deed_text_full"),
        "deed_fingerprint": bootstrap_context.get("deed_fingerprint"),
        "initial_ir_ref": bootstrap_context.get("initial_ir_ref"),
        "latest_ir_ref": latest_refs.get("ir_ref"),
        "deed_span_index_ref": latest_refs.get("deed_span_index_ref"),
    }
    memory_payload = _digest_memory_payload(recent_digest_memory)
    latest_span_memory = _latest_span_memory_from_step(last_step_result)
    if isinstance(latest_span_memory, dict):
        memory_payload.update({k: v for k, v in latest_span_memory.items() if v not in (None, [], "")})
    packet = {
        "session_id": session_id,
        "tool_menu": tool_menu,
        "ir_ops_menu": _ir_ops_menu_payload(),
        "inputs": packet_inputs,
        "progress": progress,
        "working_memory": {
            "phase_hint": phase_hint,
            # Descriptive posture only; do not embed move instructions here.
            "plan_bullets": _phase_plan_bullets(phase_hint),
            "anchor_templates": _anchor_templates_for_deed(bootstrap_context),
            "semantic_sanity_checklist": _semantic_sanity_checklist(),
        },
        "memory": memory_payload,
        "tool_cheatsheet": tool_cheatsheet_entries(tool_menu=tool_menu, context_inputs=packet_inputs),
        "recent_trace": recent_trace,
        "last_refusal": _last_refusal_payload(
            last_refusal,
            last_refusal_action_type_raw=last_refusal_action_type_raw,
            last_step_result=last_step_result,
            bootstrap_context=bootstrap_context,
            context_inputs=packet_inputs,
        ),
        "artifacts_inline": _inline_artifact_hints(latest_refs, bootstrap_context=bootstrap_context),
        "run_summary": {
            "run_summary_ref": run_summary_ref,
            "excerpt": run_summary_excerpt,
        },
    }
    if not isinstance(packet, dict):
        return packet
    artifacts_inline = packet.get("artifacts_inline")
    progress_payload = packet.get("progress")
    if isinstance(artifacts_inline, dict) and isinstance(progress_payload, dict):
        ir_hint = artifacts_inline.get("ir_hint")
        if isinstance(ir_hint, dict):
            progress_payload["ir_health"] = _ir_health_from_hint(ir_hint, latest_refs.get("ir_ref"))
        judge_hint = artifacts_inline.get("judge_hint")
        if isinstance(judge_hint, dict):
            progress_payload["judge_report_excerpt"] = _judge_excerpt_from_hint(judge_hint)
        georef_hint = artifacts_inline.get("georef_hint")
        validate_hint = artifacts_inline.get("validate_hint")
        if isinstance(georef_hint, dict) or isinstance(validate_hint, dict):
            progress_payload["map_sanity_excerpt"] = _map_sanity_excerpt_from_hints(
                georef_hint if isinstance(georef_hint, dict) else None,
                validate_hint if isinstance(validate_hint, dict) else None,
            )
        progress_payload["observed_state_labels"] = _progress_state_labels(progress_payload)
    bounded = _bound_payload(packet, max_items=24)
    if isinstance(bounded, dict):
        deed_text_full = bootstrap_context.get("deed_text_full")
        inputs = bounded.get("inputs")
        if isinstance(inputs, dict) and isinstance(deed_text_full, str):
            inputs["deed_text_full"] = deed_text_full
    return bounded


def _latest_span_memory_from_step(last_step_result: KernelStepResult | None) -> dict[str, object] | None:
    if last_step_result is None or not isinstance(last_step_result.step_record, dict):
        return None
    out: dict[str, object] = {}
    outputs = last_step_result.step_record.get("outputs")
    if isinstance(outputs, dict):
        raw_ref = outputs.get("deed_span_index_ref")
        if isinstance(raw_ref, dict):
            artifact_path = raw_ref.get("artifact_path")
            if isinstance(artifact_path, str):
                out["deed_span_index_ref"] = artifact_path
    outputs_inline = last_step_result.step_record.get("outputs_inline")
    if isinstance(outputs_inline, dict):
        if isinstance(outputs_inline.get("span_catalog_excerpt"), list):
            out["deed_span_catalog_excerpt"] = outputs_inline.get("span_catalog_excerpt")
    return out or None


def _ir_ops_menu_payload() -> dict[str, object]:
    supported = sorted(get_supported_operations())
    unsupported = sorted(get_unsupported_operations())
    tempting = [name for name in unsupported if name in {"Union", "Intersection", "Difference", "Buffer", "Offset"}]
    return {
        "supported_compilable_ops": supported[:24],
        "registered_but_not_compilable_ops": tempting[:12],
        "authoring_rules": [
            "Do not invent op names.",
            "If an op is not compilable, encode deed meaning as direct geometry plus annotation metadata.",
        ],
    }


def _compact_gap_summary(gap_summary: object) -> dict[str, object]:
    if not isinstance(gap_summary, dict):
        return {}
    top_gap_kinds = gap_summary.get("top_gap_kinds")
    top_reason_codes = gap_summary.get("top_reason_codes")
    counts = gap_summary.get("gap_counts_by_kind")
    return {
        "top_gap_kinds": top_gap_kinds[:_MAX_GAP_KINDS] if isinstance(top_gap_kinds, list) else [],
        "top_reason_codes": top_reason_codes[:_MAX_REASON_CODES] if isinstance(top_reason_codes, list) else [],
        "gap_counts_by_kind": counts if isinstance(counts, dict) else {},
    }


def _extract_recent_trace(transcript: list[dict[str, object]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for event in reversed(transcript):
        et = str(event.get("event_type", ""))
        if et not in {"kernel_step_result", "controller_refusal", "controller_parse_failed"}:
            continue
        payload = event.get("payload")
        out.append(
            {
                "event_type": et,
                "detail": str(event.get("detail", ""))[:120],
                "action_type": payload.get("action_type") if isinstance(payload, dict) else None,
                "reason_code": _extract_reason_code_from_payload(payload),
            }
        )
        if len(out) >= _MAX_TRACE_ITEMS:
            break
    out.reverse()
    return out


def _extract_reason_code_from_payload(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None
    refusal = payload.get("refusal")
    if isinstance(refusal, dict):
        reason = refusal.get("reason_code")
        if isinstance(reason, str):
            return reason
    reason = payload.get("reason_code")
    if isinstance(reason, str):
        return reason
    return None


def _phase_plan_bullets(phase_hint: str) -> list[str]:
    """Return descriptive phase posture bullets, not workflow instructions."""

    plans: dict[str, list[str]] = {
        "bootstrap": [
            "Deed evidence hydration is still needed when the deed ref is missing.",
            "IR remains unsettled until a non-stub graph exists.",
            "Compilation and judge outputs are the primary structural checkpoints.",
            "Bundle state tends to lag until the graph stabilizes.",
        ],
        "author_ir": [
            "IR authoring is the active phase posture.",
            "Artifact refs remain the dominant evidence surface.",
            "Compilation is the next structural checkpoint after meaningful IR change.",
        ],
        "verify": [
            "Judge output is the active review surface.",
            "Gap resolution is the current structural concern.",
            "Bundle state reflects convergence rather than completion.",
        ],
        "declare_candidate": [
            "Claimability is the active boundary.",
            "Closure remains evidence-bound rather than status-driven.",
            "Downstream readiness depends on the current domain state.",
        ],
    }
    selected = plans.get(phase_hint, plans["bootstrap"])
    return selected[:_MAX_PLAN_BULLETS]


def _semantic_sanity_checklist() -> list[str]:
    return [
        "Prioritize faithful deed semantics over convenient but inaccurate graph structure; do not invent substitute geometry just to satisfy a gate.",
        "Before declare_done: ask if IR/map is a faithful semantic representation of the deed, not just structurally valid.",
        "If a deed-faithful detail is partially unsupported, preserve it explicitly in IR geometry/annotations/provenance and keep iterating instead of simplifying it away.",
        "Do not accept placeholder/sketch geometry as final mapped output.",
        "If deed ties POB to a corner/line and georef used centroid fallback, treat map as non-final and repair tie encoding.",
        "For partial deeds: map only fully stated parcels; keep incomplete parcels as explicit stubs/annotations, not fabricated geometry.",
        "If plotted shape looks implausible for the deed calls (e.g., wrong topology/triangle vs quadrilateral), reopen deed spans and revise IR.",
    ]


def _last_refusal_payload(
    last_refusal: KernelRefusal | None,
    *,
    last_refusal_action_type_raw: str | None,
    last_step_result: KernelStepResult | None,
    bootstrap_context: dict[str, object] | None,
    context_inputs: dict[str, object],
) -> dict[str, object] | None:
    from .controller_proposals import _build_fix_skeleton

    if last_refusal is None:
        return None
    action_type_raw = (
        last_refusal_action_type_raw
        or ("hydrate_deed" if "deed" in ",".join(last_refusal.missing_inputs).lower() else "open_artifact")
    )
    payload = last_refusal.model_dump(mode="json")
    rejected_meta = _extract_rejected_graph_refusal_meta(last_step_result)
    if rejected_meta:
        payload.update(rejected_meta)
    payload["how_to"] = action_how_to_guide(
        action_type=action_type_raw,
        reason_code=last_refusal.reason_code,
        context_inputs=context_inputs,
    )
    payload["fix"] = _build_fix_skeleton(
        reason_code=last_refusal.reason_code,
        action_type_raw=action_type_raw,
        bootstrap_context=bootstrap_context,
    )
    return payload


def _extract_rejected_graph_refusal_meta(
    last_step_result: KernelStepResult | None,
) -> dict[str, object] | None:
    if last_step_result is None or last_step_result.execution_state != StepExecutionState.REFUSED:
        return None
    step_record = last_step_result.step_record
    if not isinstance(step_record, dict):
        return None
    outputs_inline = step_record.get("outputs_inline")
    if not isinstance(outputs_inline, dict):
        return None
    out: dict[str, object] = {}
    rejected_ref = outputs_inline.get("rejected_graph_artifact_ref")
    if isinstance(rejected_ref, dict):
        artifact_path = rejected_ref.get("artifact_path")
        if isinstance(artifact_path, str):
            out["rejected_graph_artifact_ref"] = {"artifact_path": artifact_path}
    elif isinstance(rejected_ref, str):
        out["rejected_graph_artifact_ref"] = {"artifact_path": rejected_ref}
    rejected_summary = outputs_inline.get("rejected_graph_summary")
    if isinstance(rejected_summary, dict):
        out["rejected_graph_summary"] = _bound_payload(rejected_summary, max_items=12)
    elif isinstance(rejected_summary, str):
        out["rejected_graph_summary"] = {"summary": _bounded_text(rejected_summary, 400)}
    if out:
        return out
    return None


def _digest_memory_payload(recent_digest_memory: list[dict[str, object]]) -> dict[str, object]:
    if not recent_digest_memory:
        return {
            "last_digest_ref": None,
            "last_digest_excerpt": None,
            "recent_digests_excerpts": [],
            "deed_span_index_ref": None,
            "deed_span_catalog_excerpt": None,
            "run_summary_log": [],
        }
    last = recent_digest_memory[-1]
    return {
        "last_digest_ref": last.get("digest_ref"),
        "last_digest_excerpt": last.get("digest_excerpt"),
        "recent_digests_excerpts": [d.get("digest_excerpt") for d in recent_digest_memory[-5:] if d.get("digest_excerpt")],
        "deed_span_index_ref": last.get("deed_span_index_ref"),
        "deed_span_catalog_excerpt": last.get("deed_span_catalog_excerpt"),
        "run_summary_log": [entry.get("run_summary_entry") for entry in recent_digest_memory if isinstance(entry.get("run_summary_entry"), dict)],
    }


def _inline_artifact_hints(
    latest_refs: dict[str, object],
    *,
    bootstrap_context: dict[str, object],
) -> dict[str, object]:
    hints: dict[str, object] = {}
    ir_ref = latest_refs.get("ir_ref")
    if isinstance(ir_ref, str):
        hints["ir_hint"] = _safe_artifact_hint(ir_ref, kind="ir")
    judge_ref = latest_refs.get("judge_ref")
    if isinstance(judge_ref, str):
        hints["judge_hint"] = _safe_artifact_hint(judge_ref, kind="judge")
    deed_ref = latest_refs.get("deed_text_artifact_ref")
    if not isinstance(deed_ref, str):
        deed_ref = bootstrap_context.get("deed_text_artifact_ref")
    if isinstance(deed_ref, str):
        hints["deed_hint"] = _safe_artifact_hint(deed_ref, kind="deed")
    georef_ref = latest_refs.get("georef_ref")
    if isinstance(georef_ref, str):
        hints["georef_hint"] = _safe_artifact_hint(georef_ref, kind="georef")
    validate_ref = latest_refs.get("validate_ref")
    if isinstance(validate_ref, str):
        hints["validate_hint"] = _safe_artifact_hint(validate_ref, kind="validate")
    render_ref = latest_refs.get("render_ref")
    if isinstance(render_ref, str):
        hints["render_hint"] = _safe_artifact_hint(render_ref, kind="render")
    return hints


def _safe_artifact_hint(path_value: str, *, kind: str) -> dict[str, object]:
    try:
        path = Path(path_value).resolve()
        allowed_roots = (
            agent_kernel_artifacts_root().resolve(),
            dossiers_feature_graphs_artifacts_root().resolve(),
        )
        if all(path != root and root not in path.parents for root in allowed_roots):
            return {"kind": kind, "status": "blocked_path"}
    except Exception:
        return {"kind": kind, "status": "blocked_path"}
    if not path.exists():
        return {"kind": kind, "status": "missing"}
    try:
        size = path.stat().st_size
    except Exception:
        return {"kind": kind, "status": "unreadable"}
    if size > _MAX_HINT_FILE_BYTES:
        return {"kind": kind, "status": "too_large"}
    try:
        with path.open("rb") as f:
            raw_bytes = f.read(_MAX_HINT_READ_BYTES + 1)
    except Exception:
        return {"kind": kind, "status": "unreadable"}
    if len(raw_bytes) > _MAX_HINT_READ_BYTES:
        return {"kind": kind, "status": "too_large"}
    try:
        raw = raw_bytes.decode("utf-8")
    except Exception:
        return {"kind": kind, "status": "unreadable"}
    try:
        payload = json.loads(raw)
    except Exception:
        return {"kind": kind, "status": "text", "excerpt": _bounded_text(raw, 256)}
    if kind == "judge" and isinstance(payload, dict):
        report = payload.get("report")
        if isinstance(report, dict):
            gaps = report.get("gaps")
            warnings = report.get("warnings")
            if isinstance(gaps, list):
                top = []
                for gap in gaps[:3]:
                    if isinstance(gap, dict):
                        op_value = gap.get("operation") or gap.get("op_name") or gap.get("operation_name")
                        feature_value = gap.get("feature_id") or gap.get("node_id")
                        top.append(
                            {
                                "kind": gap.get("kind"),
                                "reason_code": gap.get("reason_code"),
                                "node_id": gap.get("node_id"),
                                "feature_id": feature_value,
                                "operation": op_value,
                                "severity": gap.get("severity"),
                                "message": _bounded_text(str(gap.get("message") or ""), 160),
                            }
                        )
                return {
                    "kind": kind,
                    "status": "ok",
                    "top_gaps": top,
                    "warnings": [str(w)[:160] for w in warnings[:3]] if isinstance(warnings, list) else [],
                }
    if kind == "ir" and isinstance(payload, dict):
        graph = payload.get("graph") if isinstance(payload.get("graph"), dict) else payload
        if isinstance(graph, dict):
            nodes = graph.get("nodes")
            node_preview = []
            has_structured_plss_anchor = False
            has_local_polygon_geometry = False
            parcel_audit = {"complete_region_count": 0, "partial_annotation_stub_count": 0}
            graph_meta = graph.get("metadata")
            if isinstance(graph_meta, dict) and _controller_ir_has_required_plss_anchor(graph_meta.get("plss_anchor")):
                has_structured_plss_anchor = True
            if isinstance(nodes, list):
                for node in nodes[:3]:
                    if isinstance(node, dict):
                        node_preview.append(
                            {
                                "id": node.get("id"),
                                "label": node.get("label"),
                                "kind": node.get("kind"),
                            }
                        )
                has_local_polygon_geometry = _controller_ir_has_local_polygon_geometry(nodes)
                parcel_audit = _controller_ir_parcel_audit(nodes)
                if not has_structured_plss_anchor:
                    for node in nodes:
                        if not isinstance(node, dict):
                            continue
                        if str(node.get("kind") or "").strip().lower() != "frame":
                            continue
                        metadata = node.get("metadata")
                        if isinstance(metadata, dict) and _controller_ir_has_required_plss_anchor(metadata.get("plss_anchor")):
                            has_structured_plss_anchor = True
                            break
            return {
                "kind": kind,
                "status": "ok",
                "graph_id": graph.get("graph_id"),
                "node_count": len(nodes) if isinstance(nodes, list) else 0,
                "node_preview": node_preview,
                "has_structured_plss_anchor": has_structured_plss_anchor,
                "has_local_polygon_geometry": has_local_polygon_geometry,
                "parcel_audit": parcel_audit,
            }
    if kind == "deed" and isinstance(payload, dict):
        text = payload.get("text")
        if isinstance(text, str):
            return {"kind": kind, "status": "ok", "excerpt": _bounded_text(" ".join(text.split()), 320)}
    if kind == "georef" and isinstance(payload, dict):
        bounds = payload.get("geographic_polygon", {}).get("bounds") if isinstance(payload.get("geographic_polygon"), dict) else None
        pob = payload.get("anchor_info", {}).get("pob_coordinates") if isinstance(payload.get("anchor_info"), dict) else None
        pob_method = payload.get("anchor_info", {}).get("pob_method") if isinstance(payload.get("anchor_info"), dict) else None
        coords = payload.get("geographic_polygon", {}).get("coordinates") if isinstance(payload.get("geographic_polygon"), dict) else None
        vertex_count = 0
        if isinstance(coords, list) and coords and isinstance(coords[0], list):
            vertex_count = len(coords[0])
        quality = payload.get("agent_kernel_quality") if isinstance(payload.get("agent_kernel_quality"), dict) else {}
        return {
            "kind": kind,
            "status": "ok",
            "success": bool(payload.get("success")),
            "bounds": bounds if isinstance(bounds, dict) else None,
            "pob": pob if isinstance(pob, dict) else None,
            "pob_method": pob_method if isinstance(pob_method, str) else None,
            "vertex_count": vertex_count,
            "plss_state": ((payload.get("plss_anchor") or {}).get("state") if isinstance(payload.get("plss_anchor"), dict) else None),
            "placeholder_geometry_detected": bool(isinstance(quality, dict) and quality.get("placeholder_geometry_detected") is True),
            "explicit_tie_reference_detected": bool(isinstance(quality, dict) and quality.get("explicit_tie_reference_detected") is True),
            "tie_to_corner_provided": bool(isinstance(quality, dict) and quality.get("tie_to_corner_provided") is True),
        }
    if kind == "validate" and isinstance(payload, dict):
        return {
            "kind": kind,
            "status": "ok",
            "passed": bool(payload.get("passed")),
            "reason_code": payload.get("reason_code"),
            "overall_accuracy": payload.get("overall_accuracy"),
            "top_issues": [str(v)[:160] for v in (payload.get("top_issues") or [])[:3]] if isinstance(payload.get("top_issues"), list) else [],
            "bounds": payload.get("bounds") if isinstance(payload.get("bounds"), dict) else None,
        }
    if kind == "render" and isinstance(payload, dict):
        svg_ref = payload.get("svg_artifact_ref")
        svg_path = svg_ref.get("artifact_path") if isinstance(svg_ref, dict) else None
        return {
            "kind": kind,
            "status": "ok",
            "width": payload.get("width"),
            "height": payload.get("height"),
            "vertex_count": payload.get("vertex_count"),
            "svg_artifact_path": svg_path if isinstance(svg_path, str) else None,
            "bounds": payload.get("bounds") if isinstance(payload.get("bounds"), dict) else None,
        }
    return {"kind": kind, "status": "ok"}
