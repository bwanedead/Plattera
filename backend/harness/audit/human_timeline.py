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
ACTION_INPUTS_MAX_CHARS = 1200
OUTPUTS_EXCERPT_MAX_CHARS = 2000
RAW_RESPONSE_EXCERPT_MAX_CHARS = 2000
CONTINUITY_JOURNAL_MAX_CHARS = 3000
HITL_CONTEXT_MAX_CHARS = 1500
USER_MESSAGE_TEXT_MAX_CHARS = 1500
MAX_PAYLOAD_TEXT_FIELDS = 4

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
    sorted_turns = sorted(
        (t for t in turns if isinstance(t, Mapping)),
        key=lambda t: _safe_turn_index(t),
    )
    lines: list[str] = [
        "# Run Timeline (Human View)",
        "",
        "Live projection of the forensic audit records. Facts and model-authored",
        "text only — no host-authored semantic judgment.",
        "",
    ]
    override = _coerce_mapping(run_terminal_override)
    lines.extend(_render_run_projection(sorted_turns, override, summary_heading="Run Summary"))
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
    for turn in sorted_turns:
        lines.extend(_render_turn(turn))
        lines.append("")
    lines.extend(_render_run_projection(sorted_turns, override, summary_heading="Final Run Summary"))
    return "\n".join(lines) + "\n"


def _render_run_projection(
    turns: list[Mapping[str, Any]],
    override: Mapping[str, Any],
    *,
    summary_heading: str,
) -> list[str]:
    if not turns and not override:
        return []
    lines: list[str] = [f"## {summary_heading}", ""]
    total_duration = _run_duration_seconds(turns)
    terminal_class = override.get("terminal_class")
    last_terminal_decision = _last_terminal_decision(turns)
    latest_refs = _latest_refs_snapshot(turns, override)
    lines.append(f"- terminal_class: {terminal_class or 'in_progress'}")
    reason_code = override.get("reason_code")
    if reason_code:
        lines.append(f"- reason_code: {reason_code}")
    if last_terminal_decision:
        lines.append(f"- last_terminal_decision: {last_terminal_decision}")
    override_terminal_decision = override.get("terminal_decision")
    if override_terminal_decision and override_terminal_decision != last_terminal_decision:
        lines.append(f"- terminal_decision: {override_terminal_decision}")
    if total_duration is not None:
        lines.append(f"- total_run_duration: {_format_duration(total_duration)}")
    else:
        lines.append("- total_run_duration: unknown")
    lines.append(f"- llm_turn_count: {len(turns)}")
    if latest_refs:
        lines.append("- latest_artifact_refs:")
        for key, value in list(latest_refs.items())[:16]:
            lines.append(f"  - {key}: {value}")
    else:
        lines.append("- latest_artifact_refs: none")
    final_artifact = _final_artifact_projection(turns, latest_refs)
    if final_artifact:
        lines.extend(["", "## Final Artifact Projection", ""])
        lines.extend(final_artifact)
    lines.extend([""])
    return lines


def _render_turn(turn: Mapping[str, Any]) -> list[str]:
    turn_index = _safe_turn_index(turn)
    dispatch_summary = _pick_dispatch_summary(turn)
    patch_outcome = _nested_get(turn, "state_patch_feedback", "outcome") or "no_patch"
    header = (
        f"TURN {turn_index:04d} | choose_action | {dispatch_summary} | patch:{patch_outcome}"
    )
    duration = _turn_duration_seconds(turn)
    if duration is not None:
        header = f"{header} | duration:{_format_duration(duration)}"
    out: list[str] = [_SECTION_BAR, header, _SECTION_BAR, ""]

    out.extend(_render_operator_progress(turn))
    out.extend(_render_host_hydration_before_turn(turn))
    out.extend(_render_llm_authored_text(turn))
    out.extend(_render_repair(turn))
    out.extend(_render_action(turn))
    out.extend(_render_action_sequence_lane(turn))
    out.extend(_render_pinned_refs(turn))
    out.extend(_render_required_output_gate(turn))
    out.extend(_render_tool_result(turn))
    out.extend(_render_saved_artifact(turn))
    out.extend(_render_state_patch(turn))
    out.extend(_render_hitl(turn))
    out.extend(_render_user_messages(turn))
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
    continuity = _pick_continuity_entry(parsed, tool_request)
    hitl_req = _coerce_mapping(parsed.get("hitl_request")) or _coerce_mapping(
        tool_request.get("hitl_request")
    )

    lines: list[str] = ["LLM Authored Text"]
    lines.extend(_labeled_prose_block("  rationale:", rationale))
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

    raw_needed = not turn.get("parse_ok", True) or not (rationale or continuity or hitl_req)
    if raw_needed:
        reason = turn.get("parse_reason_code")
        parse_detail = turn.get("parse_error_detail")
        orig_count = turn.get("original_action_count_attempted")
        native_actions = turn.get("native_actions_attempted")
        finish_reason = turn.get("provider_finish_reason")
        provider_error = turn.get("provider_error")
        if reason or parse_detail or finish_reason or provider_error:
            lines.append("  action_parse_failure:")
            if reason:
                lines.append(f"    parse_reason_code: {reason}")
            if isinstance(parse_detail, str) and parse_detail.strip():
                lines.extend(_labeled_prose_block("    parse_error_detail:", parse_detail))
            if orig_count is not None:
                lines.append(f"    original_action_count_attempted: {orig_count}")
            if native_actions is not None:
                lines.append(f"    native_actions_attempted: {bool(native_actions)}")
            if finish_reason:
                lines.append(f"    provider_finish_reason: {finish_reason}")
            if provider_error:
                lines.extend(_labeled_prose_block("    provider_error:", str(provider_error)))
            prompt_tokens = turn.get("provider_prompt_tokens")
            completion_tokens = turn.get("provider_completion_tokens")
            if prompt_tokens is not None:
                lines.append(f"    provider_prompt_tokens: {prompt_tokens}")
            if completion_tokens is not None:
                lines.append(f"    provider_completion_tokens: {completion_tokens}")
        raw = turn.get("raw_llm_response_text")
        if isinstance(raw, str) and raw.strip():
            lines.append("  raw_llm_response_excerpt:")
            lines.extend(_indented_prose(_bound_text(raw, RAW_RESPONSE_EXCERPT_MAX_CHARS), indent="    "))

    lines.append("")
    return lines


def _final_artifact_projection(
    turns: list[Mapping[str, Any]],
    latest_refs: Mapping[str, Any],
) -> list[str]:
    materialized_turn: Mapping[str, Any] | None = None
    for turn in turns:
        action_type = _pick_action_type(turn)
        if action_type in ("save_workspace_artifact", "publish_workspace_artifact") and _artifact_write_succeeded(turn):
            materialized_turn = turn
    if materialized_turn is None:
        return []
    posture = (
        "published"
        if _pick_action_type(materialized_turn) == "publish_workspace_artifact"
        else "working"
    )
    result = _coerce_mapping(materialized_turn.get("tool_result_raw"))
    artifact_refs = result.get("artifact_refs") or []
    outputs = _coerce_mapping(result.get("outputs"))
    payload_turn = _published_source_turn(turns, materialized_turn) or materialized_turn
    payload_inputs = _artifact_action_inputs(payload_turn)
    draft_payload = payload_inputs.get("draft_payload")
    transcript_text = payload_inputs.get("transcript_text")
    lines: list[str] = [f"- posture: {posture}"]
    artifact_kind = outputs.get("artifact_kind") or outputs.get("kind")
    if artifact_kind:
        lines.append(f"- artifact_kind: {artifact_kind}")
    if isinstance(artifact_refs, list) and artifact_refs:
        lines.append(f"- latest_artifact_ref: {artifact_refs[0]}")
        lines.append("- artifact_refs:")
        for ref in artifact_refs[:8]:
            lines.append(f"  - {ref}")
    payload_summary = _summarize_artifact_payload(draft_payload, transcript_text)
    if payload_summary:
        lines.append("- payload_summary:")
        lines.extend(f"  - {line}" for line in payload_summary)
    lines.extend(_render_final_text_lanes(draft_payload, transcript_text))
    return lines


def _published_source_turn(
    turns: list[Mapping[str, Any]],
    publish_turn: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    if _pick_action_type(publish_turn) != "publish_workspace_artifact":
        return None
    source_ref = _published_source_revision_ref(publish_turn)
    if source_ref is None:
        return None
    for turn in reversed(turns):
        if turn is publish_turn:
            continue
        if _pick_action_type(turn) not in (
            "save_workspace_artifact",
            "copy_forward_save_workspace_artifact",
        ):
            continue
        if not _artifact_write_succeeded(turn):
            continue
        result = _coerce_mapping(turn.get("tool_result_raw"))
        refs = result.get("artifact_refs") or []
        if isinstance(refs, list) and source_ref in {str(ref) for ref in refs}:
            return turn
    return None


def _published_source_revision_ref(turn: Mapping[str, Any]) -> str | None:
    inputs = _artifact_action_inputs(turn)
    result = _coerce_mapping(turn.get("tool_result_raw"))
    outputs = _coerce_mapping(result.get("outputs"))
    for source in (inputs, outputs):
        value = source.get("source_revision_ref")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


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
            lines.append(f"    repair_parse_reason_code: {reason}")
        repaired_count = rec.get("repaired_action_count")
        if repaired_count is not None:
            lines.append(f"    repaired_action_count: {repaired_count}")
        orig_count = turn.get("original_action_count_attempted")
        if orig_count is not None:
            lines.append(f"    original_action_count_attempted: {orig_count}")
            if repaired_count is not None and int(repaired_count) != int(orig_count):
                if int(repaired_count) < int(orig_count):
                    lines.append("    repair_action_count: reduced_to_cap_or_valid_rows")
                else:
                    lines.append("    repair_action_count: changed_from_original")
        raw = rec.get("repair_raw_response_text")
        if isinstance(raw, str) and raw.strip():
            lines.append("    raw_response_excerpt:")
            lines.extend(_indented_prose(_bound_text(raw, RAW_RESPONSE_EXCERPT_MAX_CHARS), indent="      "))
        parsed_plan = rec.get("repair_parsed_action_plan")
        if parsed_plan:
            lines.extend(_labeled_json_block("    parsed_action_plan:", parsed_plan, PROSE_MAX_CHARS, indent="    "))
    lines.append("")
    return lines


def _render_operator_progress(turn: Mapping[str, Any]) -> list[str]:
    parsed = _coerce_mapping(turn.get("parsed_action_plan"))
    tool_request = _coerce_mapping(turn.get("tool_request"))
    progress = _pick_prose(parsed, tool_request, key="operator_progress_message")
    lines: list[str] = ["Operator Progress"]
    if progress:
        lines.extend(_indented_prose(progress, indent="  "))
    else:
        lines.append("  operator_progress_message: none")
    lines.append("")
    return lines


def _render_action(turn: Mapping[str, Any]) -> list[str]:
    tool_request = _coerce_mapping(turn.get("tool_request"))
    parsed = _coerce_mapping(turn.get("parsed_action_plan"))
    actions = _extract_actions(tool_request, parsed)
    if not actions and not tool_request and not parsed:
        return []
    lines = ["Action"]
    if actions:
        lines.append(f"  actions: {len(actions)}")
        for row in actions:
            lines.extend(_render_action_row(row, turn=turn))
    else:
        action_type = tool_request.get("action_type") or parsed.get("action_type")
        lines.append(f"  action_type: {action_type or 'none'}")
        inputs = tool_request.get("action_inputs") or parsed.get("action_inputs") or {}
        if inputs:
            lines.extend(_labeled_json_block("  action_inputs:", inputs, ACTION_INPUTS_MAX_CHARS))
        else:
            lines.append("  action_inputs: none")
        hydrate_next = tool_request.get("hydrate_next") or parsed.get("hydrate_next") or []
        if isinstance(hydrate_next, list) and hydrate_next:
            lines.append("  hydrate_next:")
            for ref in hydrate_next[:16]:
                lines.append(f"    - {ref}")
        hydrate_next_reason = (
            tool_request.get("hydrate_next_reason") or parsed.get("hydrate_next_reason")
        )
        if hydrate_next_reason:
            lines.append("  hydrate_next_reason:")
            lines.extend(_indented_prose(str(hydrate_next_reason), indent="    "))
    for flag_key in ("skip_execution", "wait_for_human", "complete_run"):
        value = tool_request.get(flag_key)
        if value is None:
            value = parsed.get(flag_key)
        if value:
            lines.append(f"  {flag_key}: true")
    pin_refs = tool_request.get("pin_refs") or parsed.get("pin_refs") or []
    unpin_refs = tool_request.get("unpin_refs") or parsed.get("unpin_refs") or []
    if isinstance(pin_refs, list) and pin_refs:
        lines.append("  pin_refs:")
        for ref in pin_refs[:16]:
            lines.append(f"    - {ref}")
    if isinstance(unpin_refs, list) and unpin_refs:
        lines.append("  unpin_refs:")
        for ref in unpin_refs[:16]:
            lines.append(f"    - {ref}")
    lines.append("")
    return lines


def _render_host_hydration_before_turn(turn: Mapping[str, Any]) -> list[str]:
    host = _coerce_mapping(turn.get("host_hydration_before_turn"))
    if not host:
        return []
    lines = ["Host Hydration (before choose_action)"]
    agent_lane = _coerce_mapping(host.get("agent_requested_hydration"))
    if agent_lane:
        lines.extend(_render_hydration_lane(agent_lane, indent="  ", title="agent_requested_hydration"))
    pinned_lane = _coerce_mapping(host.get("pinned_refs_auto_hydration"))
    if pinned_lane:
        lines.extend(_render_hydration_lane(pinned_lane, indent="  ", title="pinned_refs_auto_hydration"))
    lines.append("")
    return lines


def _render_hydration_lane(
    lane: Mapping[str, Any],
    *,
    indent: str,
    title: str,
) -> list[str]:
    lines = [f"{indent}{title}:"]
    for key in ("requested_refs", "resolved_refs", "refs"):
        refs = lane.get(key)
        if isinstance(refs, list) and refs:
            lines.append(f"{indent}  {key}:")
            for ref in refs[:8]:
                lines.append(f"{indent}    - {ref}")
    for key in ("status", "source_turn_index", "surfaced_iteration"):
        if key in lane and lane.get(key) is not None:
            lines.append(f"{indent}  {key}: {lane.get(key)}")
    reason = lane.get("reason")
    if reason:
        lines.append(f"{indent}  reason:")
        lines.extend(_indented_prose(str(reason), indent=f"{indent}    "))
    errors = lane.get("hydration_errors")
    if isinstance(errors, list) and errors:
        lines.append(f"{indent}  hydration_errors:")
        for row in errors[:5]:
            if isinstance(row, Mapping):
                lines.append(f"{indent}    - {row.get('reason_code') or row}")
            else:
                lines.append(f"{indent}    - {row}")
    hydrated_count = lane.get("hydrated_result_count")
    if hydrated_count is not None:
        lines.append(f"{indent}  hydrated_result_count: {hydrated_count}")
    ref_ids = lane.get("hydrated_ref_ids")
    if isinstance(ref_ids, list) and ref_ids:
        lines.append(f"{indent}  hydrated_ref_ids:")
        for ref in ref_ids[:8]:
            lines.append(f"{indent}    - {ref}")
    return lines


def _render_action_sequence_lane(turn: Mapping[str, Any]) -> list[str]:
    sequence = _coerce_mapping(turn.get("recent_action_sequence_result"))
    if not sequence:
        return []
    items = sequence.get("items")
    if not isinstance(items, list) or not items:
        return []
    lines = ["Action Sequence Results"]
    seq_id = str(sequence.get("sequence_id") or "").strip()
    if seq_id:
        lines.append(f"  sequence_id: {seq_id}")
    if sequence.get("source_turn_index") is not None:
        lines.append(f"  source_turn_index: {sequence.get('source_turn_index')}")
    for row in items[:8]:
        if not isinstance(row, Mapping):
            continue
        alias = str(row.get("alias") or "?")
        action_type = str(row.get("action_type") or "none")
        exec_state = str(row.get("execution_state") or "unknown")
        reason = row.get("reason_code")
        line = f"    - {alias}: {action_type} | {exec_state}"
        if reason:
            line = f"{line} | {reason}"
        lines.append(line)
    lines.append("")
    return lines


def _render_required_output_gate(turn: Mapping[str, Any]) -> list[str]:
    gate = _coerce_mapping(turn.get("required_output_gate"))
    if not gate:
        return []
    lines = ["Required Output Gate"]
    for key in ("reason_code", "strike_count", "max_strikes", "outcome"):
        if key in gate and gate.get(key) is not None:
            lines.append(f"  {key}: {gate.get(key)}")
    lines.append("")
    return lines


def _render_pinned_refs(turn: Mapping[str, Any]) -> list[str]:
    pinned = _coerce_mapping(turn.get("pinned_refs"))
    pin_this_turn = turn.get("pin_refs_this_turn") or []
    unpin_this_turn = turn.get("unpin_refs_this_turn") or []
    if not pinned and not pin_this_turn and not unpin_this_turn:
        return []
    lines = ["Pinned Refs"]
    if isinstance(pin_this_turn, list) and pin_this_turn:
        lines.append("  pinned_this_turn:")
        for ref in pin_this_turn[:16]:
            lines.append(f"    - {ref}")
    if isinstance(unpin_this_turn, list) and unpin_this_turn:
        lines.append("  unpinned_this_turn:")
        for ref in unpin_this_turn[:16]:
            lines.append(f"    - {ref}")
    host = _coerce_mapping(turn.get("host_hydration_before_turn"))
    pinned_auto = _coerce_mapping(host.get("pinned_refs_auto_hydration")) if host else None
    if pinned_auto:
        lines.extend(_render_hydration_lane(pinned_auto, indent="  ", title="auto_hydrated_before_turn"))
    active = pinned.get("active") if pinned else None
    if isinstance(active, list) and active:
        lines.append("  active:")
        for row in active[:8]:
            if isinstance(row, Mapping):
                ref = str(row.get("ref") or "").strip()
                if ref:
                    lines.append(f"    - {ref}")
    expired = pinned.get("expired") if pinned else None
    if isinstance(expired, list) and expired:
        lines.append("  expired:")
        for row in expired[:8]:
            if isinstance(row, Mapping):
                ref = str(row.get("ref") or "").strip()
                if ref:
                    lines.append(f"    - {ref}")
    lines.append("")
    return lines


def _render_action_row(row: Mapping[str, Any], *, turn: Mapping[str, Any]) -> list[str]:
    alias = str(row.get("alias") or "").strip() or "?"
    action_type = str(row.get("action_type") or "").strip() or "none"
    lines = [f"    - {alias}: {action_type}"]
    hydrate_next = row.get("hydrate_next")
    if isinstance(hydrate_next, list) and hydrate_next:
        lines.append("      hydrate_next:")
        for ref in hydrate_next[:16]:
            lines.append(f"        - {ref}")
    else:
        lines.append("      hydrate_next: none")
    hydrate_next_reason = row.get("hydrate_next_reason")
    if hydrate_next_reason:
        lines.append("      hydrate_next_reason:")
        lines.extend(_indented_prose(str(hydrate_next_reason), indent="        "))
    inputs = _coerce_mapping(row.get("action_inputs"))
    if inputs:
        lines.extend(
            _labeled_json_block(
                "      action_inputs:",
                inputs,
                ACTION_INPUTS_MAX_CHARS,
                indent="        ",
            )
        )
    else:
        lines.append("      action_inputs: none")
    sequence = _coerce_mapping(turn.get("recent_action_sequence_result"))
    if sequence:
        items = sequence.get("items")
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, Mapping):
                    continue
                if str(item.get("alias") or "") != alias:
                    continue
                exec_state = str(item.get("execution_state") or "").strip()
                if exec_state:
                    lines.append(f"      execution_state: {exec_state}")
                item_reason = item.get("reason_code")
                if item_reason:
                    lines.append(f"      execution_reason_code: {item_reason}")
                break
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
        lines.extend(_render_rendered_evidence_output(_coerce_mapping(outputs), indent="  "))
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
    if not _artifact_write_succeeded(turn):
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
        payload = _coerce_mapping(draft_payload)
        payload_keys = ", ".join(str(k) for k in payload.keys()) or "none"
        lines.append(f"  draft_payload_keys: {payload_keys}")
        lines.extend(_render_payload_fields(payload, indent="  "))
    elif isinstance(transcript_text, str) and transcript_text.strip():
        lines.append("  transcript_text:")
        lines.extend(
            _indented_prose(_bound_text(transcript_text, PROSE_MAX_CHARS), indent="    ")
        )
    else:
        lines.append("  draft_payload: none")
    lines.append("")
    return lines


def _render_rendered_evidence_output(outputs: Mapping[str, Any], *, indent: str) -> list[str]:
    rows = outputs.get("rendered_evidence_refs")
    if not isinstance(rows, list) or not rows:
        return []
    lines = [f"{indent}rendered_evidence_refs:"]
    for row in rows[:8]:
        row = _coerce_mapping(row)
        source_ref = row.get("source_ref") or "?"
        rendered_ref = row.get("rendered_ref") or "?"
        locator_count = row.get("locator_count", "?")
        summary_only = row.get("summary_only_locator_count", 0)
        unsupported = row.get("unsupported_locator_count", 0)
        lines.append(
            f"{indent}  - source_ref: {source_ref} | rendered_ref: {rendered_ref} | "
            f"locator_count:{locator_count} | summary_only:{summary_only} | unsupported:{unsupported}"
        )
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


def _render_user_messages(turn: Mapping[str, Any]) -> list[str]:
    ledger = turn.get("user_message_ledger") or []
    unknown_count = turn.get("user_message_consumed_unknown_count")
    if not isinstance(ledger, list) and not unknown_count:
        return []
    rows = [row for row in ledger if isinstance(row, Mapping)]
    if not rows and not unknown_count:
        return []
    lines = ["User Messages"]
    if unknown_count:
        lines.append(f"  consumed_unknown_count: {unknown_count}")
    if rows:
        lines.append("  ledger:")
        for raw in rows[:8]:
            row = _coerce_mapping(raw)
            lines.append(f"    - message_id: {row.get('message_id') or 'none'}")
            lines.append(f"      status: {row.get('status') or 'unknown'}")
            source = row.get("source")
            if source:
                lines.append(f"      source: {source}")
            text = row.get("text")
            if text is not None:
                lines.append("      text:")
                lines.extend(
                    _indented_prose(
                        _bound_text(str(text), USER_MESSAGE_TEXT_MAX_CHARS),
                        indent="        ",
                    )
                )
            reason = row.get("defer_reason")
            if reason:
                lines.append("      defer_reason:")
                lines.extend(_indented_prose(_bound_text(str(reason), 400), indent="        "))
            bounds = row.get("_bounds")
            if bounds:
                lines.extend(_labeled_json_block("      bounds:", bounds, 800, indent="        "))
    else:
        lines.append("  ledger: none")
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
    lines.extend(_render_locator_summary(unit.get("evidence_locators"), indent="        "))
    opaque = unit.get("opaque_payload")
    if opaque:
        lines.extend(
            _labeled_json_block("        opaque_payload:", opaque, PROSE_MAX_CHARS, indent="          ")
        )
    return lines


def _render_locator_summary(locators: Any, *, indent: str) -> list[str]:
    if not isinstance(locators, list) or not locators:
        return []
    lines = [f"{indent}evidence_locators:"]
    for locator in locators[:16]:
        locator = _coerce_mapping(locator)
        kind = locator.get("locator_kind") or "?"
        ref_id = locator.get("ref_id") or "?"
        label = locator.get("label")
        parts = [f"kind:{kind}", f"ref:{ref_id}"]
        if label:
            parts.append(f"label:{label}")
        for key in ("box_norm", "line_start", "line_end", "row", "column", "json_path"):
            value = locator.get(key)
            if value is not None and value != "":
                parts.append(f"{key}:{_bound_text(str(value), 120)}")
        lines.append(f"{indent}  - " + " | ".join(parts))
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
        if _has_work_graph_value_fields(item):
            lines.extend(_render_work_graph_value_fields(item, indent="      "))
        covered_units = item.get("covered_units")
        if isinstance(covered_units, list) and covered_units:
            for unit in covered_units:
                unit = _coerce_mapping(unit)
                lines.extend(_render_work_graph_unit(unit))
    lines.append("")
    return lines


def _has_work_graph_value_fields(row: Mapping[str, Any]) -> bool:
    return any(
        row.get(key) not in (None, "", [], {})
        for key in ("label", "value_kind", "candidate_values", "determined_value")
    )


def _render_work_graph_value_fields(row: Mapping[str, Any], *, indent: str) -> list[str]:
    lines: list[str] = []
    label = row.get("label")
    if isinstance(label, str) and label.strip():
        lines.append(f"{indent}label: {label}")
    if row.get("value_kind"):
        lines.append(f"{indent}value_kind: {row['value_kind']}")
    candidates = row.get("candidate_values")
    if isinstance(candidates, list) and candidates:
        joined = "; ".join(str(c) for c in candidates[:16])
        lines.append(f"{indent}candidates: {joined}")
    determined = row.get("determined_value")
    if isinstance(determined, str) and determined.strip():
        lines.append(f"{indent}determined: {_bound_text(determined, 240)}")
    refs = row.get("evidence_refs")
    if isinstance(refs, list) and refs:
        joined_refs = ", ".join(str(r) for r in refs[:8])
        lines.append(f"{indent}evidence: {joined_refs}")
    locators = row.get("evidence_locators")
    if isinstance(locators, list) and locators:
        kinds = ", ".join(
            str(_coerce_mapping(loc).get("locator_kind") or "?") for loc in locators[:8]
        )
        lines.append(f"{indent}evidence_locators: {len(locators)} ({kinds})")
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
    locators = unit.get("evidence_locators")
    if isinstance(locators, list) and locators:
        kinds = ", ".join(str(_coerce_mapping(loc).get("locator_kind") or "?") for loc in locators[:8])
        lines.append(f"        evidence_locators: {len(locators)} ({kinds})")
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


def _extract_actions(
    tool_request: Mapping[str, Any],
    parsed: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    for source in (tool_request, parsed):
        raw = source.get("actions")
        if isinstance(raw, list) and raw:
            return [_coerce_mapping(row) for row in raw if isinstance(row, Mapping)]
    legacy_batch = tool_request.get("action_batch") or parsed.get("action_batch")
    if isinstance(legacy_batch, list) and legacy_batch:
        return [_coerce_mapping(row) for row in legacy_batch if isinstance(row, Mapping)]
    return []


def _pick_dispatch_summary(turn: Mapping[str, Any]) -> str:
    tool_request = _coerce_mapping(turn.get("tool_request"))
    parsed = _coerce_mapping(turn.get("parsed_action_plan"))
    actions = _extract_actions(tool_request, parsed)
    if len(actions) == 1:
        row = actions[0]
        alias = str(row.get("alias") or "").strip()
        action_type = str(row.get("action_type") or "").strip() or "none"
        if alias and alias != "action":
            return f"actions:1 ({alias}:{action_type})"
        return f"actions:1 ({action_type})"
    if len(actions) > 1:
        types = [
            str(row.get("action_type") or "").strip() or "?"
            for row in actions[:4]
        ]
        suffix = ", ..." if len(actions) > 4 else ""
        return f"actions:{len(actions)} ({', '.join(types)}{suffix})"
    return _pick_action_type(turn)


def _pick_action_type(turn: Mapping[str, Any]) -> str:
    tool_request = _coerce_mapping(turn.get("tool_request"))
    parsed = _coerce_mapping(turn.get("parsed_action_plan"))
    actions = _extract_actions(tool_request, parsed)
    if len(actions) == 1:
        return str(actions[0].get("action_type") or "none")
    if len(actions) > 1:
        return "action_sequence"
    if tool_request.get("action_type"):
        return str(tool_request["action_type"])
    if parsed.get("action_type"):
        return str(parsed["action_type"])
    terminal = turn.get("terminal_decision")
    if terminal:
        return str(terminal)
    return "no_dispatch"


def _artifact_action_inputs(turn: Mapping[str, Any]) -> dict[str, Any]:
    tool_request = _coerce_mapping(turn.get("tool_request"))
    parsed = _coerce_mapping(turn.get("parsed_action_plan"))
    return _coerce_mapping(tool_request.get("action_inputs")) or _coerce_mapping(
        parsed.get("action_inputs")
    )


def _extract_text_lane_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    mapping = _coerce_mapping(value)
    text = mapping.get("text")
    return str(text) if isinstance(text, str) else None


def _summarize_lane(label: str, value: Any) -> str:
    text = _extract_text_lane_text(value)
    if text is not None:
        return f"{label}: present ({len(text)} chars)"
    mapping = _coerce_mapping(value)
    if mapping:
        return f"{label}: object ({len(mapping)} keys)"
    return f"{label}: none"


def _summarize_artifact_payload(draft_payload: Any, transcript_text: Any) -> list[str]:
    if isinstance(draft_payload, Mapping):
        payload = _coerce_mapping(draft_payload)
        summary = [f"payload_keys: {', '.join(str(k) for k in payload.keys()) or 'none'}"]
        for key, value in list(payload.items())[:8]:
            summary.append(_summarize_lane(str(key), value))
        return summary
    if isinstance(transcript_text, str) and transcript_text.strip():
        return [f"transcript_text: present ({len(transcript_text)} chars)"]
    return []


def _render_final_text_lanes(draft_payload: Any, transcript_text: Any) -> list[str]:
    lines: list[str] = []
    if isinstance(draft_payload, Mapping):
        payload = _coerce_mapping(draft_payload)
        rendered = 0
        for key, value in payload.items():
            text = _extract_text_lane_text(value)
            if not (isinstance(text, str) and text.strip()):
                continue
            label = f"- {key}.text:" if isinstance(value, Mapping) else f"- {key}:"
            lines.append(label)
            lines.extend(_indented_prose(_bound_text(text, PROSE_MAX_CHARS), indent="    "))
            if len(text) > PROSE_MAX_CHARS:
                lines.append(f"    [truncated to {PROSE_MAX_CHARS} chars]")
            rendered += 1
            if rendered >= MAX_PAYLOAD_TEXT_FIELDS:
                break
        return lines
    if isinstance(transcript_text, str) and transcript_text.strip():
        lines.append("- transcript_text:")
        lines.extend(_indented_prose(_bound_text(transcript_text, PROSE_MAX_CHARS), indent="    "))
        if len(transcript_text) > PROSE_MAX_CHARS:
            lines.append(f"    [truncated to {PROSE_MAX_CHARS} chars]")
    return lines


def _turn_duration_seconds(turn: Mapping[str, Any]) -> float | None:
    started = turn.get("started_at_epoch_seconds")
    finished = turn.get("finished_at_epoch_seconds")
    try:
        if started is None or finished is None:
            return None
        duration = float(finished) - float(started)
        return duration if duration >= 0 else None
    except (TypeError, ValueError):
        return None


def _run_duration_seconds(turns: list[Mapping[str, Any]]) -> float | None:
    starts: list[float] = []
    finishes: list[float] = []
    for turn in turns:
        try:
            started = turn.get("started_at_epoch_seconds")
            finished = turn.get("finished_at_epoch_seconds")
            if started is not None:
                starts.append(float(started))
            if finished is not None:
                finishes.append(float(finished))
        except (TypeError, ValueError):
            continue
    if not starts or not finishes:
        return None
    duration = max(finishes) - min(starts)
    return duration if duration >= 0 else None


def _format_duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds:.3f}s"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remainder = divmod(seconds, 60.0)
    return f"{int(minutes)}m {remainder:.1f}s"


def _terminal_status(turns: list[Mapping[str, Any]]) -> str | None:
    for turn in reversed(turns):
        result = _coerce_mapping(turn.get("tool_result_raw"))
        execution_state = result.get("execution_state")
        if execution_state:
            return str(execution_state)
    return None


def _last_terminal_decision(turns: list[Mapping[str, Any]]) -> str | None:
    for turn in reversed(turns):
        decision = turn.get("terminal_decision")
        if decision:
            return str(decision)
    return None


def _latest_refs_snapshot(
    turns: list[Mapping[str, Any]],
    override: Mapping[str, Any],
) -> dict[str, Any]:
    latest_refs = _coerce_mapping(override.get("latest_refs"))
    if latest_refs:
        return latest_refs
    for turn in reversed(turns):
        refs = _coerce_mapping(turn.get("latest_refs_after")) or _coerce_mapping(
            turn.get("latest_refs_before")
        )
        if refs:
            return refs
    return {}


def _artifact_write_succeeded(turn: Mapping[str, Any]) -> bool:
    result = _coerce_mapping(turn.get("tool_result_raw"))
    execution_state = str(result.get("execution_state") or "")
    artifact_refs = result.get("artifact_refs") or []
    return execution_state == "executed" and isinstance(artifact_refs, list) and bool(artifact_refs)


def _render_payload_fields(payload: Mapping[str, Any], *, indent: str) -> list[str]:
    lines: list[str] = []
    for key, value in list(payload.items())[:8]:
        key_text = str(key)
        text = _extract_text_lane_text(value)
        if isinstance(text, str) and text.strip():
            label = f"{indent}{key_text}.text:" if isinstance(value, Mapping) else f"{indent}{key_text}:"
            lines.append(label)
            lines.extend(_indented_prose(_bound_text(text, PROSE_MAX_CHARS), indent=f"{indent}  "))
            if len(text) > PROSE_MAX_CHARS:
                lines.append(f"{indent}  [truncated to {PROSE_MAX_CHARS} chars]")
            continue
        lines.extend(_labeled_json_block(f"{indent}{key_text}:", value, PROSE_MAX_CHARS, indent=f"{indent}  "))
    return lines


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
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    try:
        os.replace(tmp, path)
    except PermissionError:
        # On Windows, os.replace() may fail with WinError 5 when the destination
        # file is briefly held open by a file watcher or antivirus scan.
        # Fall back to a non-atomic direct write; the timeline is best-effort.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        path.write_text(text, encoding="utf-8")
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
