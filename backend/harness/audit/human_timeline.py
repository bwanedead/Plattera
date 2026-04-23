"""Human-readable per-turn audit projection.

Writes ``audit/human/timeline.md`` by projecting the accumulated turn records
held by ``RunAuditWriter``. The writer is a pure renderer: it copies facts and
model-authored prose already present in the turn records, and does not decide
what the run means.

Hard rules:
- No host-authored semantic conclusions (no "stuck", "spinning", verdicts).
- No domain-aware relevance filtering (all items shown, all prose shown).
- No binary/image bytes embedded in outputs excerpts.
- Long fields get a visible truncation marker.

The renderer is called after every ``observe_llm_io`` and
``observe_turn_completed`` update so the file stays readable mid-run.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import textwrap
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_LOG = logging.getLogger(__name__)

WRAP_COLUMNS = 100
PROSE_MAX_CHARS = 4000
OUTPUTS_EXCERPT_MAX_CHARS = 2000
RAW_RESPONSE_EXCERPT_MAX_CHARS = 2000
CONTINUITY_JOURNAL_MAX_CHARS = 3000
HITL_CONTEXT_MAX_CHARS = 1500

_BINARY_KEYS = frozenset(
    {
        "image_bytes",
        "image_b64",
        "image_base64",
        "image_evidence",
        "binary",
        "binary_payload",
        "pdf_bytes",
        "bytes",
        "raw_bytes",
    }
)

_SECTION_BAR = "=" * 80
_SUBSECTION_BAR = "-" * 80


def write_human_timeline(
    audit_dir: Path,
    turns: list[dict[str, Any]],
    run_terminal_override: Mapping[str, Any] | None = None,
) -> None:
    """Render and atomic-write ``<audit_dir>/human/timeline.md`` from ``turns``.

    Best-effort: exceptions are logged and suppressed so audit never blocks a
    live run.
    """
    try:
        target_dir = audit_dir / "human"
        target_dir.mkdir(parents=True, exist_ok=True)
        body = render_timeline(turns, run_terminal_override=run_terminal_override)
        _atomic_write_text(target_dir / "timeline.md", body)
    except Exception:
        _LOG.warning("human_timeline write failed; timeline may be stale", exc_info=True)


def render_timeline(
    turns: list[dict[str, Any]],
    run_terminal_override: Mapping[str, Any] | None = None,
) -> str:
    """Render the full markdown-ish timeline body from accumulated turn records."""
    lines: list[str] = [
        "# Run Timeline (Human View)",
        "",
        "Live projection of the forensic audit records. Facts and model-authored",
        "text only — no host-authored semantic judgment.",
        "",
    ]
    override = _coerce_mapping(run_terminal_override)
    if override:
        lines.extend(
            [
                "## Run-Level Terminal Override",
                "",
                f"- terminal_class: {override.get('terminal_class') or 'unknown'}",
                f"- reason_code: {override.get('reason_code') or 'unknown'}",
                f"- terminal_decision: {override.get('terminal_decision') or 'unknown'}",
                "",
            ]
        )
    sorted_turns = sorted(
        (t for t in turns if isinstance(t, Mapping)),
        key=lambda t: _safe_turn_index(t),
    )
    for turn in sorted_turns:
        lines.extend(_render_turn(turn))
        lines.append("")
    return "\n".join(lines) + "\n"


def _render_turn(turn: Mapping[str, Any]) -> list[str]:
    turn_index = _safe_turn_index(turn)
    action_type = _pick_action_type(turn)
    patch_outcome = _nested_get(turn, "state_patch_feedback", "outcome") or "no_patch"
    header = (
        f"TURN {turn_index:04d} | choose_action | {action_type} | patch:{patch_outcome}"
    )
    out: list[str] = [_SECTION_BAR, header, _SECTION_BAR, ""]

    out.extend(_render_llm_authored_text(turn))
    out.extend(_render_repair(turn))
    out.extend(_render_action(turn))
    out.extend(_render_tool_result(turn))
    out.extend(_render_saved_artifact(turn))
    out.extend(_render_state_patch(turn))
    out.extend(_render_hitl(turn))
    out.extend(_render_mission_snapshot(turn))
    out.extend(_render_resolution(turn))
    out.extend(_render_work_graph(turn))
    out.extend(_render_closure(turn))
    out.extend(_render_observability(turn))
    return out


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------


def _render_llm_authored_text(turn: Mapping[str, Any]) -> list[str]:
    parsed = _coerce_mapping(turn.get("parsed_action_plan"))
    tool_request = _coerce_mapping(turn.get("tool_request"))

    rationale = _pick_prose(parsed, tool_request, key="rationale")
    progress = _pick_prose(parsed, tool_request, key="operator_progress_message")
    continuity = _pick_continuity_entry(parsed, tool_request)
    hitl_req = _coerce_mapping(parsed.get("hitl_request")) or _coerce_mapping(
        tool_request.get("hitl_request")
    )

    lines: list[str] = ["LLM Authored Text"]
    lines.extend(_labeled_prose_block("  rationale:", rationale))
    lines.extend(_labeled_prose_block("  operator_progress_message:", progress))
    lines.extend(_labeled_json_block("  continuity_journal_entry:", continuity, CONTINUITY_JOURNAL_MAX_CHARS))

    if hitl_req:
        lines.append("  hitl_request.message:")
        lines.extend(_indented_prose(hitl_req.get("message"), indent="    "))
        choices = hitl_req.get("choices")
        if isinstance(choices, list) and choices:
            lines.append("  hitl_request.choices:")
            for choice in choices:
                lines.append(f"    - {choice}")
        context = hitl_req.get("context")
        if context:
            lines.extend(_labeled_json_block("  hitl_request.context:", context, HITL_CONTEXT_MAX_CHARS))

    raw_needed = not turn.get("parse_ok", True) or not (rationale or progress or continuity or hitl_req)
    if raw_needed:
        raw = turn.get("raw_llm_response_text")
        if isinstance(raw, str) and raw.strip():
            lines.append("  raw_llm_response_excerpt:")
            lines.extend(_indented_prose(_bound_text(raw, RAW_RESPONSE_EXCERPT_MAX_CHARS), indent="    "))

    lines.append("")
    return lines


def _render_repair(turn: Mapping[str, Any]) -> list[str]:
    if not turn.get("repair_attempted"):
        return []
    records = turn.get("repair_records") or []
    lines: list[str] = ["Repair"]
    lines.append(f"  attempts: {len(records)}")
    for i, rec in enumerate(records, start=1):
        rec = _coerce_mapping(rec)
        lines.append(f"  attempt_{i}:")
        lines.append(f"    parse_ok: {bool(rec.get('repair_parse_ok'))}")
        reason = rec.get("repair_parse_reason_code")
        if reason:
            lines.append(f"    parse_reason_code: {reason}")
        raw = rec.get("repair_raw_response_text")
        if isinstance(raw, str) and raw.strip():
            lines.append("    raw_response_excerpt:")
            lines.extend(_indented_prose(_bound_text(raw, RAW_RESPONSE_EXCERPT_MAX_CHARS), indent="      "))
        parsed_plan = rec.get("repair_parsed_action_plan")
        if parsed_plan:
            lines.extend(_labeled_json_block("    parsed_action_plan:", parsed_plan, PROSE_MAX_CHARS, indent="    "))
    lines.append("")
    return lines


def _render_action(turn: Mapping[str, Any]) -> list[str]:
    tool_request = _coerce_mapping(turn.get("tool_request"))
    parsed = _coerce_mapping(turn.get("parsed_action_plan"))
    action_type = tool_request.get("action_type") or parsed.get("action_type")
    if not action_type and not tool_request and not parsed:
        return []
    inputs = tool_request.get("action_inputs") or parsed.get("action_inputs") or {}
    lines = ["Action", f"  action_type: {action_type or 'none'}"]
    if inputs:
        lines.extend(_labeled_json_block("  action_inputs:", inputs, PROSE_MAX_CHARS))
    else:
        lines.append("  action_inputs: none")
    for flag_key in ("skip_execution", "wait_for_human", "complete_run"):
        value = tool_request.get(flag_key)
        if value is None:
            value = parsed.get(flag_key)
        if value:
            lines.append(f"  {flag_key}: true")
    lines.append("")
    return lines


def _render_tool_result(turn: Mapping[str, Any]) -> list[str]:
    result = _coerce_mapping(turn.get("tool_result_raw"))
    if not result:
        return []
    lines = ["Tool Result"]
    lines.append(f"  execution_state: {result.get('execution_state') or 'unknown'}")
    refusal = _coerce_mapping(result.get("refusal"))
    if refusal:
        lines.append(f"  execution_reason_code: {refusal.get('reason_code') or 'none'}")
    else:
        lines.append("  execution_reason_code: none")
    artifact_refs = result.get("artifact_refs") or []
    if isinstance(artifact_refs, list) and artifact_refs:
        lines.append("  artifact_refs_out:")
        for ref in artifact_refs[:32]:
            lines.append(f"    - {ref}")
    else:
        lines.append("  artifact_refs_out: none")

    refs_before = _coerce_mapping(turn.get("latest_refs_before"))
    refs_after = _coerce_mapping(turn.get("latest_refs_after"))
    refs_changed = bool(refs_before != refs_after) if refs_before or refs_after else False
    lines.append(f"  latest_refs_changed: {str(refs_changed).lower()}")

    outputs = result.get("outputs")
    if outputs:
        excerpt, truncated = _bounded_outputs(outputs, OUTPUTS_EXCERPT_MAX_CHARS)
        lines.append("  outputs_excerpt:")
        lines.extend(_indented_prose(excerpt, indent="    "))
        if truncated:
            lines.append(f"    [truncated to {OUTPUTS_EXCERPT_MAX_CHARS} chars]")
    else:
        lines.append("  outputs_excerpt: none")

    image_evidence = result.get("image_evidence") or []
    if isinstance(image_evidence, list) and image_evidence:
        lines.append(f"  image_evidence_count: {len(image_evidence)}")
    lines.append("")
    return lines


def _render_saved_artifact(turn: Mapping[str, Any]) -> list[str]:
    tool_request = _coerce_mapping(turn.get("tool_request"))
    parsed = _coerce_mapping(turn.get("parsed_action_plan"))
    action_type = tool_request.get("action_type") or parsed.get("action_type")
    if action_type != "save_workspace_artifact":
        return []
    inputs = _coerce_mapping(tool_request.get("action_inputs")) or _coerce_mapping(
        parsed.get("action_inputs")
    )
    if not inputs:
        return []
    draft_payload = inputs.get("draft_payload")
    transcript_text = inputs.get("transcript_text")
    result = _coerce_mapping(turn.get("tool_result_raw"))
    artifact_refs = result.get("artifact_refs") or []

    lines: list[str] = ["Saved Artifact"]
    if isinstance(artifact_refs, list) and artifact_refs:
        lines.append("  ref_ids:")
        for ref in artifact_refs[:16]:
            lines.append(f"    - {ref}")
    else:
        lines.append("  ref_ids: none")

    outputs = _coerce_mapping(result.get("outputs"))
    artifact_kind = outputs.get("artifact_kind") or outputs.get("kind")
    if artifact_kind:
        lines.append(f"  artifact_kind: {artifact_kind}")

    if isinstance(draft_payload, Mapping):
        verbatim_raw = draft_payload.get("source_transcript_verbatim")
        if isinstance(verbatim_raw, str):
            verbatim_text: str | None = verbatim_raw
        else:
            verbatim = _coerce_mapping(verbatim_raw)
            verbatim_text = verbatim.get("text") if verbatim else None
        if isinstance(verbatim_text, str) and verbatim_text.strip():
            lines.append("  source_transcript_verbatim.text:")
            lines.extend(
                _indented_prose(_bound_text(verbatim_text, PROSE_MAX_CHARS), indent="    ")
            )
        else:
            lines.append("  source_transcript_verbatim.text: none")

        mapping_raw = draft_payload.get("normalized_or_mapping_transcript")
        if isinstance(mapping_raw, str):
            mapping_text: str | None = mapping_raw
        else:
            mapping_view = _coerce_mapping(mapping_raw)
            mapping_text = mapping_view.get("text") if mapping_view else None
        if isinstance(mapping_text, str) and mapping_text.strip():
            lines.append("  normalized_or_mapping_transcript.text:")
            lines.extend(
                _indented_prose(_bound_text(mapping_text, PROSE_MAX_CHARS), indent="    ")
            )
        else:
            lines.append("  normalized_or_mapping_transcript.text: none")

        issues = draft_payload.get("issues")
        lines.extend(_labeled_json_block("  issues:", issues, PROSE_MAX_CHARS))
        parcel_metadata = draft_payload.get("parcel_metadata")
        lines.extend(_labeled_json_block("  parcel_metadata:", parcel_metadata, PROSE_MAX_CHARS))
        hitl_decisions = draft_payload.get("hitl_decisions")
        lines.extend(_labeled_json_block("  hitl_decisions:", hitl_decisions, PROSE_MAX_CHARS))
        payload_evidence_refs = draft_payload.get("evidence_refs")
        if isinstance(payload_evidence_refs, list) and payload_evidence_refs:
            lines.append("  evidence_refs:")
            for ref in payload_evidence_refs[:32]:
                lines.append(f"    - {ref}")
        else:
            lines.append("  evidence_refs: none")
    elif isinstance(transcript_text, str) and transcript_text.strip():
        lines.append("  transcript_text:")
        lines.extend(
            _indented_prose(_bound_text(transcript_text, PROSE_MAX_CHARS), indent="    ")
        )
    else:
        lines.append("  draft_payload: none")
    lines.append("")
    return lines


def _render_state_patch(turn: Mapping[str, Any]) -> list[str]:
    feedback = _coerce_mapping(turn.get("state_patch_feedback"))
    if not feedback:
        return []
    lines = ["State Patch"]
    lines.append(f"  outcome: {feedback.get('outcome') or 'no_patch'}")
    reason = feedback.get("reason_code")
    if reason:
        lines.append(f"  reason_code: {reason}")
    applied_paths = feedback.get("applied_paths") or []
    rejected_paths = feedback.get("rejected_paths") or []
    lines.extend(_bullet_list("  applied_paths:", applied_paths))
    lines.extend(_bullet_list("  rejected_paths:", rejected_paths))
    lines.append("")
    return lines


def _render_hitl(turn: Mapping[str, Any]) -> list[str]:
    pending = turn.get("pending_hitl_requests") or []
    answered = turn.get("answered_hitl_responses") or []
    state = turn.get("hitl_state")
    if not pending and not answered and not state:
        return []
    lines = ["HITL"]
    lines.append(f"  state: {state or 'no_prompt'}")
    if pending:
        lines.append("  pending:")
        for req in pending[:8]:
            req = _coerce_mapping(req)
            lines.append(f"    - prompt_id: {req.get('prompt_id') or 'none'}")
            msg = req.get("message")
            if msg:
                lines.extend(_indented_prose(_bound_text(str(msg), PROSE_MAX_CHARS), indent="      "))
    else:
        lines.append("  pending: none")
    if answered:
        lines.append("  answered:")
        for ans in answered[:8]:
            ans = _coerce_mapping(ans)
            lines.append(f"    - prompt_id: {ans.get('prompt_id') or 'none'}")
            fb = ans.get("feedback")
            if fb is not None:
                lines.extend(_labeled_json_block("      feedback:", fb, PROSE_MAX_CHARS, indent="      "))
    else:
        lines.append("  answered: none")
    lines.append("")
    return lines


def _render_mission_snapshot(turn: Mapping[str, Any]) -> list[str]:
    mission = _coerce_mapping(turn.get("mission_state_after")) or _coerce_mapping(
        turn.get("mission_state_before")
    )
    refs = _coerce_mapping(turn.get("latest_refs_after")) or _coerce_mapping(
        turn.get("latest_refs_before")
    )
    if not mission and not refs:
        return []
    lines = ["Mission Snapshot"]
    if mission:
        work_state = (
            mission.get("active_mode")
            or mission.get("work_state")
            or mission.get("work_universe_posture")
        )
        lines.append(f"  work_state: {work_state or 'unknown'}")
        objective = mission.get("objective")
        if objective:
            lines.append("  objective:")
            lines.extend(_indented_prose(str(objective), indent="    "))
        conditions = mission.get("success_conditions") or []
        if isinstance(conditions, list) and conditions:
            lines.append("  success_conditions:")
            for cond in conditions:
                cond = _coerce_mapping(cond)
                cid = cond.get("condition_id") or "?"
                status = cond.get("status") or "?"
                blocking = cond.get("blocking")
                flag = f" | blocking:{str(bool(blocking)).lower()}" if blocking is not None else ""
                lines.append(f"    - {cid} | {status}{flag}")
    active_item_id = (
        (_coerce_mapping(turn.get("resolution_state_after")).get("active_item_id"))
        or (_coerce_mapping(turn.get("resolution_state_before")).get("active_item_id"))
    )
    if active_item_id:
        lines.append(f"  active_item_id: {active_item_id}")
    if refs:
        lines.append("  latest_refs:")
        for k, v in list(refs.items())[:32]:
            lines.append(f"    {k}: {v}")
    lines.append("")
    return lines


def _render_resolution(turn: Mapping[str, Any]) -> list[str]:
    resolution = _coerce_mapping(turn.get("resolution_state_after")) or _coerce_mapping(
        turn.get("resolution_state_before")
    )
    if not resolution:
        return []
    items = resolution.get("items") or []
    relations = resolution.get("relations") or []
    if not items and not relations:
        return []
    lines = ["Resolution Items"]
    if isinstance(items, list) and items:
        for item in items:
            item = _coerce_mapping(item)
            lines.extend(_render_resolution_item(item))
    else:
        lines.append("  (none)")
    if isinstance(relations, list) and relations:
        lines.append(f"  relations_count: {len(relations)}")
        for rel in relations[:16]:
            rel = _coerce_mapping(rel)
            lines.append(
                f"    - {rel.get('source_item_id')} --{rel.get('relation_type')}--> {rel.get('target_item_id')}"
            )
    lines.append("")
    return lines


def _render_resolution_item(item: Mapping[str, Any]) -> list[str]:
    item_id = item.get("item_id") or "?"
    status = item.get("status") or "?"
    parts = [f"  - {item_id} | {status}"]
    if item.get("structure_kind"):
        parts.append(f"structure_kind:{item['structure_kind']}")
    if item.get("blocking") is not None:
        parts.append(f"blocking:{str(bool(item['blocking'])).lower()}")
    if item.get("requires_hitl") is not None:
        parts.append(f"requires_hitl:{str(bool(item['requires_hitl'])).lower()}")
    if item.get("no_further_progress"):
        parts.append("no_further_progress:true")
    if item.get("sequence_scope"):
        parts.append(f"sequence_scope:{item['sequence_scope']}")
    if item.get("sequence_index") is not None:
        parts.append(f"sequence_index:{item['sequence_index']}")
    lines = [" | ".join(parts)]
    for prose_key in ("summary", "verification_basis", "next_needed_step", "determination"):
        value = item.get(prose_key)
        if isinstance(value, str) and value.strip():
            lines.append(f"    {prose_key}:")
            lines.extend(_indented_prose(_bound_text(value, PROSE_MAX_CHARS), indent="      "))
    covered_units = item.get("covered_units")
    if isinstance(covered_units, list) and covered_units:
        lines.append("    covered_units:")
        for unit in covered_units:
            unit = _coerce_mapping(unit)
            lines.extend(_render_covered_unit(unit))
    return lines


def _render_covered_unit(unit: Mapping[str, Any]) -> list[str]:
    unit_id = unit.get("unit_id") or "?"
    status = unit.get("status") or "?"
    determination = unit.get("determination") or "?"
    header_parts = [f"      - {unit_id} | {status} | {determination}"]
    if unit.get("kind"):
        header_parts.append(f"kind:{unit['kind']}")
    if unit.get("value_kind"):
        header_parts.append(f"value_kind:{unit['value_kind']}")
    if unit.get("materiality"):
        header_parts.append(f"materiality:{unit['materiality']}")
    lines = [" | ".join(header_parts)]
    label = unit.get("label")
    if isinstance(label, str) and label.strip():
        lines.append(f"        label: {label}")
    title = unit.get("title")
    if isinstance(title, str) and title.strip():
        lines.append(f"        title: {title}")
    candidates = unit.get("candidate_values")
    if isinstance(candidates, list) and candidates:
        lines.append("        candidate_values:")
        for cv in candidates[:16]:
            lines.append(f"          - {cv}")
    determined_value = unit.get("determined_value")
    if isinstance(determined_value, str) and determined_value.strip():
        lines.append("        determined_value:")
        lines.extend(
            _indented_prose(_bound_text(determined_value, PROSE_MAX_CHARS), indent="          ")
        )
    for prose_key in ("summary", "verification_basis", "next_needed_step"):
        value = unit.get(prose_key)
        if isinstance(value, str) and value.strip():
            lines.append(f"        {prose_key}:")
            lines.extend(_indented_prose(_bound_text(value, PROSE_MAX_CHARS), indent="          "))
    refs = unit.get("evidence_refs")
    if isinstance(refs, list) and refs:
        lines.append("        evidence_refs:")
        for ref in refs[:16]:
            lines.append(f"          - {ref}")
    opaque = unit.get("opaque_payload")
    if opaque:
        lines.extend(
            _labeled_json_block("        opaque_payload:", opaque, PROSE_MAX_CHARS, indent="          ")
        )
    return lines


def _render_work_graph(turn: Mapping[str, Any]) -> list[str]:
    """Compact work-graph projection from resolution.items + covered_units.

    Pure renderer. No host semantic conclusions. Shows each resolution item as a
    parent row and each covered_unit as an indented compact row with value-bearing
    fields (label/title, status, determination, candidate_values, determined_value,
    evidence_refs, next_needed_step).
    """
    resolution = _coerce_mapping(turn.get("resolution_state_after")) or _coerce_mapping(
        turn.get("resolution_state_before")
    )
    if not resolution:
        return []
    items = resolution.get("items") or []
    if not isinstance(items, list) or not items:
        return []
    lines: list[str] = ["Work Graph"]
    for item in items:
        item = _coerce_mapping(item)
        item_id = item.get("item_id") or "?"
        item_kind = item.get("structure_kind") or item.get("kind") or "?"
        item_status = item.get("status") or "?"
        header_parts = [f"  - {item_id} | {item_kind} | {item_status}"]
        if item.get("determination"):
            header_parts.append(f"determination:{item['determination']}")
        if item.get("blocking"):
            header_parts.append("blocking:true")
        lines.append(" | ".join(header_parts))
        label_or_title = item.get("title") or item.get("item_id")
        if isinstance(label_or_title, str) and label_or_title.strip():
            lines.append(f"      title: {label_or_title}")
        covered_units = item.get("covered_units")
        if isinstance(covered_units, list) and covered_units:
            for unit in covered_units:
                unit = _coerce_mapping(unit)
                lines.extend(_render_work_graph_unit(unit))
    lines.append("")
    return lines


def _render_work_graph_unit(unit: Mapping[str, Any]) -> list[str]:
    unit_id = unit.get("unit_id") or "?"
    label = unit.get("label") or unit.get("title") or unit_id
    status = unit.get("status") or "?"
    header_parts = [f"    * {label} ({unit_id}) | {status}"]
    if unit.get("determination"):
        header_parts.append(f"determination:{unit['determination']}")
    if unit.get("value_kind"):
        header_parts.append(f"value_kind:{unit['value_kind']}")
    lines = [" | ".join(header_parts)]
    candidates = unit.get("candidate_values")
    if isinstance(candidates, list) and candidates:
        joined = "; ".join(str(c) for c in candidates[:16])
        lines.append(f"        candidates: {joined}")
    else:
        lines.append("        candidates: none")
    determined = unit.get("determined_value")
    if isinstance(determined, str) and determined.strip():
        lines.append(f"        determined: {_bound_text(determined, 240)}")
    else:
        lines.append("        determined: none")
    refs = unit.get("evidence_refs")
    if isinstance(refs, list) and refs:
        joined_refs = ", ".join(str(r) for r in refs[:8])
        lines.append(f"        evidence: {joined_refs}")
    else:
        lines.append("        evidence: none")
    next_step = unit.get("next_needed_step")
    if isinstance(next_step, str) and next_step.strip():
        lines.append(f"        next: {_bound_text(next_step, 240)}")
    return lines


def _render_closure(turn: Mapping[str, Any]) -> list[str]:
    mission = _coerce_mapping(turn.get("mission_state_after")) or _coerce_mapping(
        turn.get("mission_state_before")
    )
    closure = _coerce_mapping(mission.get("closure_state"))
    if not closure:
        return []
    lines = ["Closure / Readiness"]
    lines.append(f"  overall_status: {closure.get('overall_status') or 'unknown'}")
    lines.append(f"  ready_to_close: {str(bool(closure.get('ready_to_close'))).lower()}")
    lines.append(f"  ready_to_publish: {str(bool(closure.get('ready_to_publish'))).lower()}")
    dimensions = closure.get("dimensions") or []
    if isinstance(dimensions, list) and dimensions:
        lines.append("  dimensions:")
        for dim in dimensions:
            dim = _coerce_mapping(dim)
            did = dim.get("dimension_id") or "?"
            status = dim.get("status") or "?"
            blocking = dim.get("blocking")
            flag = f" | blocking:{str(bool(blocking)).lower()}" if blocking is not None else ""
            lines.append(f"    - {did} | {status}{flag}")
    lines.append("")
    return lines


def _render_observability(turn: Mapping[str, Any]) -> list[str]:
    summary = _coerce_mapping(turn.get("prompt_observability_summary"))
    if not summary:
        return []
    lines = ["Observability"]
    flags = summary.get("mechanical_flags") or []
    if isinstance(flags, list) and flags:
        lines.append("  flags:")
        for flag in flags:
            lines.append(f"    - {flag}")
    for key in (
        "work_universe_posture",
        "resolution_item_count",
        "success_condition_count",
        "closure_dimension_count",
        "last_state_patch_outcome",
        "last_state_patch_reason_code",
    ):
        if key in summary:
            lines.append(f"  {key}: {summary[key]}")
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _pick_action_type(turn: Mapping[str, Any]) -> str:
    tool_request = _coerce_mapping(turn.get("tool_request"))
    if tool_request.get("action_type"):
        return str(tool_request["action_type"])
    parsed = _coerce_mapping(turn.get("parsed_action_plan"))
    if parsed.get("action_type"):
        return str(parsed["action_type"])
    terminal = turn.get("terminal_decision")
    if terminal:
        return str(terminal)
    return "no_dispatch"


def _pick_prose(*sources: Mapping[str, Any], key: str) -> str | None:
    for src in sources:
        value = src.get(key) if isinstance(src, Mapping) else None
        if isinstance(value, str) and value.strip():
            return value
    return None


def _pick_continuity_entry(*sources: Mapping[str, Any]) -> Any:
    for src in sources:
        if not isinstance(src, Mapping):
            continue
        entry = src.get("continuity_journal_entry")
        if entry:
            return entry
    return None


def _labeled_prose_block(label: str, value: str | None) -> list[str]:
    if not value:
        return [f"{label}", "    none"]
    lines = [label]
    lines.extend(_indented_prose(_bound_text(value, PROSE_MAX_CHARS), indent="    "))
    if len(value) > PROSE_MAX_CHARS:
        lines.append(f"    [truncated to {PROSE_MAX_CHARS} chars]")
    return lines


def _labeled_json_block(
    label: str, value: Any, max_chars: int, *, indent: str = "    "
) -> list[str]:
    if value is None or value == {} or value == []:
        return [label.rstrip(":") + ": none"]
    stripped = _strip_binary(value)
    try:
        blob = json.dumps(stripped, ensure_ascii=False, indent=2, default=str, sort_keys=True)
    except (TypeError, ValueError):
        blob = str(stripped)
    truncated = len(blob) > max_chars
    if truncated:
        blob = blob[:max_chars]
    lines = [label]
    for raw_line in blob.splitlines():
        lines.append(f"{indent}{raw_line}")
    if truncated:
        lines.append(f"{indent}[truncated to {max_chars} chars]")
    return lines


def _bullet_list(label: str, values: list[Any]) -> list[str]:
    if not values:
        return [label.rstrip(":") + ": none"]
    lines = [label]
    for value in values[:32]:
        lines.append(f"    - {value}")
    return lines


def _indented_prose(text: Any, *, indent: str) -> list[str]:
    if text is None:
        return [f"{indent}none"]
    if not isinstance(text, str):
        text = str(text)
    if not text.strip():
        return [f"{indent}none"]
    width = max(WRAP_COLUMNS - len(indent), 20)
    out: list[str] = []
    for raw_line in text.splitlines() or [text]:
        if not raw_line.strip():
            out.append(indent.rstrip())
            continue
        wrapped = textwrap.wrap(raw_line, width=width) or [raw_line]
        for w in wrapped:
            out.append(f"{indent}{w}")
    return out


def _bound_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f" [truncated to {max_chars} chars]"


def _bounded_outputs(value: Any, max_chars: int) -> tuple[str, bool]:
    stripped = _strip_binary(value)
    if isinstance(stripped, str):
        truncated = len(stripped) > max_chars
        return (stripped[:max_chars] if truncated else stripped), truncated
    try:
        blob = json.dumps(stripped, ensure_ascii=False, indent=2, default=str, sort_keys=True)
    except (TypeError, ValueError):
        blob = str(stripped)
    truncated = len(blob) > max_chars
    return (blob[:max_chars] if truncated else blob), truncated


def _strip_binary(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _strip_binary(inner)
            for key, inner in value.items()
            if str(key) not in _BINARY_KEYS
        }
    if isinstance(value, list):
        return [_strip_binary(item) for item in value]
    return value


def _coerce_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _nested_get(source: Mapping[str, Any], *keys: str) -> Any:
    current: Any = source
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _safe_turn_index(turn: Mapping[str, Any]) -> int:
    try:
        return int(turn.get("turn_index") or 0)
    except (TypeError, ValueError):
        return 0


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
