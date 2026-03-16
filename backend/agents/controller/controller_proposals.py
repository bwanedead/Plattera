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

from .controller_guardrails import _build_parse_failure_resync_proposal, _read_str
from .controller_transcript import (
    _append_event,
    _bounded_text,
    _latest_refs_summary,
    _log_controller_event,
    _proposal_failure_payload,
)

def _propose_next_step(
    *,
    llm_client: NextStepLLMClient,
    model: str,
    observation: dict[str, object],
    transcript: list[dict[str, object]],
    run_link_id: str = "",
    mission_objective: str = "",
) -> KernelStepProposal | None:
    tool_menu = observation.get("tool_menu")
    tool_specs = action_tool_specs_for_menu(tool_menu if isinstance(tool_menu, list) else [])
    if not tool_specs:
        tool_specs = []
    first = llm_client.propose_next_step(
        model=model,
        tools=tool_specs,
        tool_choice_name=None,
        developer_message=build_developer_message(run_link_id=run_link_id, model=model, mission_objective=mission_objective),
        user_message=build_user_message(context_packet=observation),
    )
    proposal, parse_error = _coerce_proposal(first)
    if proposal is not None:
        return proposal
    first_failure = _proposal_failure_payload(first, attempt="first", parse_error=parse_error)
    _append_event(
        transcript,
        event_type="controller_parse_failed",
        detail="first_parse_or_validation_failed",
        payload=first_failure,
    )
    _log_controller_event("controller_parse_failed", first_failure)

    second = llm_client.propose_next_step(
        model=model,
        tools=tool_specs,
        tool_choice_name=None,
        developer_message=build_developer_message(run_link_id=run_link_id, model=model, mission_objective=mission_objective),
        user_message=build_repair_user_message(parse_error=parse_error),
    )
    proposal, parse_error = _coerce_proposal(second)
    if proposal is not None:
        return proposal
    second_failure = _proposal_failure_payload(second, attempt="repair", parse_error=parse_error)
    _append_event(
        transcript,
        event_type="controller_parse_failed",
        detail="repair_parse_or_validation_failed",
        payload=second_failure,
    )
    _log_controller_event("controller_parse_failed", second_failure)
    return None


def _propose_refusal_repair_step(
    *,
    llm_client: NextStepLLMClient,
    model: str,
    observation: dict[str, object],
    transcript: list[dict[str, object]],
    repair_request: dict[str, object],
    run_link_id: str = "",
    mission_objective: str = "",
) -> KernelStepProposal | None:
    tool_menu = observation.get("tool_menu")
    available_specs = action_tool_specs_for_menu(tool_menu if isinstance(tool_menu, list) else [])
    action_type_raw = _read_str(repair_request.get("action_type"))
    forced_specs = [spec for spec in available_specs if action_type_raw and spec.name == action_type_raw]
    tools = forced_specs or available_specs
    if not tools:
        return None
    minimal_example = repair_request.get("minimal_working_example")
    first = llm_client.propose_next_step(
        model=model,
        tools=tools,
        tool_choice_name=tools[0].name if len(tools) == 1 else action_type_raw,
        developer_message=build_developer_message(run_link_id=run_link_id, model=model, mission_objective=mission_objective),
        user_message=build_refusal_repair_user_message(
            reason_code=str(repair_request.get("reason_code") or "unknown_refusal"),
            required_fields=[str(v) for v in (repair_request.get("required_fields") or []) if isinstance(v, str)],
            minimal_working_example=minimal_example if isinstance(minimal_example, dict) else None,
        ),
    )
    proposal, parse_error = _coerce_proposal(first)
    if proposal is not None:
        return proposal
    failure = _proposal_failure_payload(first, attempt="refusal_repair", parse_error=parse_error)
    _append_event(
        transcript,
        event_type="controller_parse_failed",
        detail="refusal_repair_parse_or_validation_failed",
        payload=failure,
    )
    _log_controller_event("controller_parse_failed", failure)
    return None


def _refusal_repair_request(
    *,
    action_type_raw: str,
    refusal: KernelRefusal,
    bootstrap_context: dict[str, object],
    context_inputs: dict[str, object],
 ) -> dict[str, object] | None:
    if coerce_action_type(action_type_raw) is None:
        return None
    resolved_action_type_raw = _override_refusal_repair_action_type(
        reason_code=refusal.reason_code,
        action_type_raw=action_type_raw,
        context_inputs=context_inputs,
    )
    how_to = action_how_to_guide(
        action_type=resolved_action_type_raw,
        reason_code=refusal.reason_code,
        context_inputs=context_inputs,
    )
    fix = _build_fix_skeleton(
        reason_code=refusal.reason_code,
        action_type_raw=resolved_action_type_raw,
        bootstrap_context=bootstrap_context,
    )
    kernel_step = fix.get("kernel_step")
    minimal = how_to.get("minimal_working_example")
    if isinstance(kernel_step, dict):
        ks_args = kernel_step.get("args")
        if isinstance(ks_args, dict):
            minimal = ks_args
    return {
        "action_type": resolved_action_type_raw,
        "reason_code": refusal.reason_code,
        "required_fields": how_to.get("required_fields") if isinstance(how_to.get("required_fields"), list) else [],
        "minimal_working_example": minimal if isinstance(minimal, dict) else None,
    }


def _override_refusal_repair_action_type(
    *,
    reason_code: str,
    action_type_raw: str,
    context_inputs: Mapping[str, object],
) -> str:
    normalized = str(reason_code or "").strip().lower()
    if normalized == "semantic_repair_span_loop_no_progress":
        return ActionType.DRAFT_IR.value
    if normalized == "repeated_span_open_no_progress":
        has_span_index = bool(_read_str(context_inputs.get("deed_span_index_ref")))
        return (ActionType.DRAFT_IR.value if has_span_index else ActionType.UPSERT_DEED_SPAN_INDEX.value)
    if normalized == "repeated_inspection_no_progress":
        return ActionType.DRAFT_IR.value
    return action_type_raw


def _coerce_proposal(raw: dict[str, object]) -> tuple[KernelStepProposal | None, str | None]:
    structured = raw.get("structured_data")
    if isinstance(structured, dict):
        try:
            validated = KernelStepProposal.model_validate(_sanitize_raw_proposal_payload(structured))
            return validated, None
        except Exception as exc:
            try:
                legacy = structured.get("proposal")
                if isinstance(legacy, dict):
                    validated = KernelStepProposal.model_validate(_sanitize_raw_proposal_payload(legacy))
                    return validated, None
                return None, f"schema_validation_failed:{type(exc).__name__}"
            except Exception:
                return None, f"schema_validation_failed:{type(exc).__name__}"
    text = raw.get("text")
    if not isinstance(text, str):
        return None, "response_missing_text"
    try:
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            return None, "json_not_object"
        try:
            validated = KernelStepProposal.model_validate(_sanitize_raw_proposal_payload(parsed))
            return validated, None
        except Exception:
            legacy = parsed.get("proposal")
            if isinstance(legacy, dict):
                validated = KernelStepProposal.model_validate(_sanitize_raw_proposal_payload(legacy))
                return validated, None
            return None, "schema_validation_failed:ValidationError"
    except json.JSONDecodeError as exc:
        return None, f"json_parse_failed:{exc.msg}"
    except Exception as exc:
        return None, f"schema_validation_failed:{type(exc).__name__}"


def _sanitize_raw_proposal_payload(raw_payload: dict[str, object]) -> dict[str, object]:
    candidate = dict(raw_payload)
    candidate = _normalize_declare_done_candidate_payload(candidate)
    why_value = candidate.get("why")
    if isinstance(why_value, str) and len(why_value) > 500:
        candidate["why"] = why_value[:500]
    notes_value = candidate.get("notes")
    if isinstance(notes_value, str) and len(notes_value) > 2000:
        candidate["notes"] = notes_value[:2000]
    return candidate


def _normalize_declare_done_candidate_payload(candidate: dict[str, object]) -> dict[str, object]:
    action_type = str(candidate.get("action_type") or "").strip().lower()
    if action_type != ActionType.DECLARE_DONE.value:
        return candidate
    raw = candidate.get("declare_done")
    if not isinstance(raw, dict):
        return candidate
    normalized = dict(raw)

    raw_refs = normalized.get("artifact_refs")
    if isinstance(raw_refs, dict):
        alias_map = {
            "ir_artifact_ref": "ir_ref",
            "compile_artifact_ref": "compile_ref",
            "judge_artifact_ref": "judge_ref",
            "bundle_artifact_ref": "bundle_ref",
            "georeference_artifact_ref": "georef_ref",
            "georef_artifact_ref": "georef_ref",
            "validation_artifact_ref": "validate_ref",
            "validate_artifact_ref": "validate_ref",
            "render_artifact_ref": "render_ref",
        }
        refs_out: dict[str, object] = {}
        for key, value in raw_refs.items():
            k = str(key)
            canonical = alias_map.get(k, k)
            if canonical in {"ir_ref", "compile_ref", "judge_ref", "bundle_ref", "georef_ref", "validate_ref", "render_ref"}:
                refs_out[canonical] = value
        normalized["artifact_refs"] = refs_out

    raw_evidence = normalized.get("evidence_links")
    if isinstance(raw_evidence, list):
        fixed_links: list[dict[str, object]] = []
        for item in raw_evidence[:20]:
            if not isinstance(item, dict):
                continue
            source_raw = str(item.get("source") or "DEED").strip().upper()
            source = source_raw if source_raw in {"DEED", "RAG"} else "DEED"
            ref = item.get("ref")
            if ref is None:
                ref = item.get("artifact_ref")
            if ref is None:
                ref = item.get("reference")
            claim = item.get("claim")
            if claim is None:
                claim = item.get("description")
            if claim is None:
                claim = item.get("reason")
            ref_text = _read_str(ref)
            claim_text = _read_str(claim)
            if not ref_text or not claim_text:
                continue
            fixed_links.append({"source": source, "ref": ref_text, "claim": claim_text[:200]})
        normalized["evidence_links"] = fixed_links

    raw_deviations = normalized.get("accepted_deviations")
    if isinstance(raw_deviations, list):
        fixed_devs: list[dict[str, object]] = []
        for item in raw_deviations[:20]:
            if not isinstance(item, dict):
                continue
            kind = _read_str(item.get("kind")) or _read_str(item.get("type"))
            reason = _read_str(item.get("reason")) or _read_str(item.get("description"))
            if not kind or not reason:
                continue
            fixed_devs.append({"kind": kind[:64], "reason": reason[:200]})
        normalized["accepted_deviations"] = fixed_devs

    candidate["declare_done"] = normalized
    return candidate


def _normalize_controller_notes(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text[:500] if text else None
    try:
        rendered = json.dumps(_bound_payload(value), ensure_ascii=True, sort_keys=True)
    except Exception:
        rendered = str(value)
    rendered = rendered.strip()
    return rendered[:500] if rendered else None


def _validate_controller_inputs(inputs: dict[str, object]) -> KernelRefusal | None:
    payload = json.dumps(inputs, sort_keys=True, separators=(",", ":"))
    if len(payload.encode("utf-8")) > _MAX_CONTROLLER_INPUT_BYTES:
        return KernelRefusal(
            reason_code="controller_inputs_payload_too_large",
            retryable=False,
            blocked_by_invariant=True,
        )
    if _contains_large_geometry(inputs):
        return KernelRefusal(
            reason_code="controller_inputs_include_large_geometry_blob",
            retryable=False,
            blocked_by_invariant=True,
        )
    if _contains_excessive_depth(inputs):
        return KernelRefusal(
            reason_code="controller_inputs_depth_exceeded",
            retryable=False,
            blocked_by_invariant=True,
        )
    return None


def _contains_excessive_depth(value: object, *, depth: int = 0, max_depth: int = 8) -> bool:
    if depth > max_depth:
        return True
    if isinstance(value, dict):
        return any(_contains_excessive_depth(v, depth=depth + 1, max_depth=max_depth) for v in value.values())
    if isinstance(value, list):
        return any(_contains_excessive_depth(v, depth=depth + 1, max_depth=max_depth) for v in value)
    return False


def _contains_large_geometry(value: object, parent_key: str = "") -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_lower = str(key).lower()
            if key_lower in {"geometry", "coordinates", "rings", "vertices", "polygon"}:
                if isinstance(nested, list) and len(nested) > 64:
                    return True
            if _contains_large_geometry(nested, key_lower):
                return True
        return False
    if isinstance(value, list):
        if parent_key in {"geometry", "coordinates", "rings", "vertices", "polygon"} and len(value) > 64:
            return True
        for nested in value:
            if _contains_large_geometry(nested, parent_key):
                return True
    return False


def _build_fix_skeleton(
    *,
    reason_code: str,
    action_type_raw: str,
    bootstrap_context: dict[str, object] | None = None,
) -> dict[str, object]:
    action = action_type_raw.strip().lower()
    args: dict[str, object] = {}
    required_fields: list[str] = []
    deed_ref = None
    if isinstance(bootstrap_context, dict):
        raw_deed_ref = bootstrap_context.get("deed_text_artifact_ref")
        if isinstance(raw_deed_ref, str) and raw_deed_ref.strip():
            deed_ref = raw_deed_ref.strip()
    if action == ActionType.OPEN_ARTIFACT.value:
        required_fields = ["artifact_ref | artifact_path | corpus_entry_ref"]
        args = {"artifact_ref": deed_ref or "<artifact-path-or-ref>"}
    elif action == ActionType.HYDRATE_DEED.value:
        required_fields = ["dossier_id | source_entry_ref"]
        args = {"dossier_id": "<dossier-id>"}
    elif action == ActionType.RETRIEVE_EVIDENCE.value:
        required_fields = ["query"]
        args = {"query": "<what you need to find>"}
    elif action in {ActionType.COMPILE.value, ActionType.JUDGE.value, ActionType.BUNDLE.value}:
        required_fields = ["ir_artifact_ref | updated_ir_artifact_ref | ir_artifact_path"]
        args = {"ir_artifact_ref": "<ir-artifact-ref>"}
    elif action == ActionType.DRAFT_IR.value:
        required_fields = [
            "dossier_id",
            "graph",
            "deed_text_artifact_ref (recommended provenance)",
        ]
        args = {
            "dossier_id": (
                str(bootstrap_context.get("dossier_id"))
                if isinstance(bootstrap_context, dict) and bootstrap_context.get("dossier_id") is not None
                else "<dossier-id>"
            ),
            "deed_text_artifact_ref": deed_ref or "<deed-text-artifact-ref>",
            "graph": {
                "graph_id": "g_min_draft_001",
                "nodes": [{"id": "start_point", "kind": "point", "geometry": {"type": "Point", "coordinates": [0.0, 0.0]}}],
                "edges": [],
                "metadata": {"source": "deed"},
            },
        }
        if reason_code == "georef_missing_plss_anchor":
            required_fields.append("graph.metadata.plss_anchor OR FRAME.metadata.plss_anchor (canonical field name: plss_anchor)")
            args["graph"] = {
                "graph_id": "g_add_plss_anchor_fix_001",
                "nodes": [
                    {
                        "id": "local_frame",
                        "kind": "frame",
                        "metadata": {
                            "plss_anchor": {
                                "state": "Wyoming",
                                "township_number": 14,
                                "township_direction": "N",
                                "range_number": 75,
                                "range_direction": "W",
                                "section_number": 2,
                                "principal_meridian": "Sixth Principal Meridian",
                            }
                        },
                    }
                ],
                "edges": [],
                "metadata": {
                    "source": "deed",
                    "plss_anchor": {
                        "state": "Wyoming",
                        "township_number": 14,
                        "township_direction": "N",
                        "range_number": 75,
                        "range_direction": "W",
                        "section_number": 2,
                    },
                    "authoring_note": "Use canonical field name plss_anchor (NOT plss) for georeference compatibility.",
                },
            }
    elif action == ActionType.DECLARE_DONE.value:
        required_fields = ["declare_done"]
        args = {}
    skeleton = {
        "kernel_step": {
            "action_type": action,
            "args": args,
            "idempotency_key": "<controller-computed>",
            "why": "corrective retry after refusal",
        },
        "required_fields": required_fields,
        "reason_code": reason_code,
    }
    if action == ActionType.DECLARE_DONE.value:
        skeleton["kernel_step"]["declare_done"] = {
            "artifact_refs": {
                "ir_ref": "<latest ir ref>",
                "compile_ref": "<latest compile ref>",
                "judge_ref": "<latest judge ref>",
                "bundle_ref": "<latest bundle ref>",
            },
            "evidence_links": [],
            "accepted_deviations": [],
        }
    return skeleton


def _autofill_known_args(
    *,
    action_type: ActionType,
    args: dict[str, object],
    bootstrap_context: dict[str, object],
    dashboard: dict[str, object],
    context_packet: dict[str, object] | None = None,
) -> tuple[dict[str, object], set[str]]:
    filled: set[str] = set()
    updated = dict(args)
    deed_ref = _read_str(bootstrap_context.get("deed_text_artifact_ref"))
    deed_fingerprint = (
        bootstrap_context.get("deed_fingerprint")
        if isinstance(bootstrap_context.get("deed_fingerprint"), dict)
        else None
    )
    dossier_id = _read_str(bootstrap_context.get("dossier_id"))
    source_entry_ref = _read_str(bootstrap_context.get("source_entry_ref"))
    latest_refs = _latest_refs_summary(dashboard)
    ir_ref = _read_str(latest_refs.get("ir_ref")) or _read_str(bootstrap_context.get("initial_ir_ref"))
    memory = context_packet.get("memory") if isinstance(context_packet, dict) and isinstance(context_packet.get("memory"), dict) else {}
    deed_span_index_ref = _read_str(latest_refs.get("deed_span_index_ref")) or _read_str(memory.get("deed_span_index_ref"))

    if action_type == ActionType.OPEN_ARTIFACT:
        has_any = any(_read_str(updated.get(k)) for k in ("artifact_ref", "artifact_path", "corpus_entry_ref"))
        if not has_any:
            preferred_open_ref = (
                _read_str(latest_refs.get("judge_ref"))
                or _read_str(latest_refs.get("compile_ref"))
                or _read_str(latest_refs.get("ir_ref"))
                or deed_ref
            )
            if preferred_open_ref:
                updated["artifact_ref"] = preferred_open_ref
                filled.add("artifact_ref")
            elif source_entry_ref:
                updated["corpus_entry_ref"] = source_entry_ref
                filled.add("corpus_entry_ref")

    if action_type == ActionType.OPEN_TEXT_SPANS:
        if not _read_str(updated.get("deed_text_artifact_ref")) and deed_ref:
            updated["deed_text_artifact_ref"] = deed_ref
            filled.add("deed_text_artifact_ref")
        if isinstance(updated.get("span_ids"), list) and updated.get("span_ids"):
            if not _read_str(updated.get("deed_span_index_ref")) and deed_span_index_ref:
                updated["deed_span_index_ref"] = deed_span_index_ref
                filled.add("deed_span_index_ref")

    if action_type == ActionType.DRAFT_IR:
        if not _read_str(updated.get("dossier_id")) and dossier_id:
            updated["dossier_id"] = dossier_id
            filled.add("dossier_id")
        has_deed = any(
            _read_str(updated.get(k))
            for k in ("deed_text_artifact_ref", "deed_artifact_ref", "hydrated_deed_artifact_ref")
        )
        if not has_deed and "graph" not in updated and deed_ref:
            updated["deed_text_artifact_ref"] = deed_ref
            filled.add("deed_text_artifact_ref")

    if action_type == ActionType.UPSERT_DEED_SPAN_INDEX:
        if not _read_str(updated.get("deed_text_artifact_ref")) and deed_ref:
            updated["deed_text_artifact_ref"] = deed_ref
            filled.add("deed_text_artifact_ref")
        if "deed_fingerprint" not in updated and isinstance(deed_fingerprint, dict):
            updated["deed_fingerprint"] = deed_fingerprint
            filled.add("deed_fingerprint")

    if action_type in {ActionType.COMPILE, ActionType.JUDGE, ActionType.BUNDLE}:
        has_ir = any(_read_str(updated.get(k)) for k in ("ir_artifact_ref", "updated_ir_artifact_ref", "ir_artifact_path"))
        if not has_ir and ir_ref:
            updated["ir_artifact_ref"] = ir_ref
            filled.add("ir_artifact_ref")

    if action_type == ActionType.GEOREFERENCE:
        if not _read_str(updated.get("bundle_artifact_ref")):
            bundle_ref = _read_str(latest_refs.get("bundle_ref"))
            if bundle_ref:
                updated["bundle_artifact_ref"] = bundle_ref
                filled.add("bundle_artifact_ref")
        has_any = any(_read_str(updated.get(k)) for k in ("bundle_artifact_ref", "ir_artifact_ref"))
        if not has_any and ir_ref:
            updated["ir_artifact_ref"] = ir_ref
            filled.add("ir_artifact_ref")

    if action_type == ActionType.VALIDATE:
        if not _read_str(updated.get("georef_artifact_ref")):
            georef_ref = _read_str(latest_refs.get("georef_ref"))
            if georef_ref:
                updated["georef_artifact_ref"] = georef_ref
                filled.add("georef_artifact_ref")
    if action_type == ActionType.RENDER:
        if not _read_str(updated.get("georef_artifact_ref")):
            georef_ref = _read_str(latest_refs.get("georef_ref"))
            if georef_ref:
                updated["georef_artifact_ref"] = georef_ref
                filled.add("georef_artifact_ref")

    return updated, filled


def _autofill_declare_done_justification(*, dashboard: dict[str, object]) -> DeclareDoneJustification | None:
    latest_refs = _latest_refs_summary(dashboard)
    if not isinstance(latest_refs, dict):
        return None
    if not any(_read_str(latest_refs.get(k)) for k in ("ir_ref", "compile_ref", "judge_ref", "bundle_ref")):
        return None
    payload = {
        "artifact_refs": {
            "ir_ref": _read_str(latest_refs.get("ir_ref")),
            "compile_ref": _read_str(latest_refs.get("compile_ref")),
            "judge_ref": _read_str(latest_refs.get("judge_ref")),
            "bundle_ref": _read_str(latest_refs.get("bundle_ref")),
            "georef_ref": _read_str(latest_refs.get("georef_ref")),
            "validate_ref": _read_str(latest_refs.get("validate_ref")),
            "render_ref": _read_str(latest_refs.get("render_ref")),
        },
        "evidence_links": [],
        "accepted_deviations": [],
    }
    try:
        return DeclareDoneJustification.model_validate(payload)
    except Exception:
        return None
