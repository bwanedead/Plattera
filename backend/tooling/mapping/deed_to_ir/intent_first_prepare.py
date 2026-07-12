"""Intent-first final-package assembly for deed-to-IR (mechanical only).

Assembles strict package rows from current mapping lineage + agent-authored
correction decisions and already agent-authored finalization state. Never
infers scope, dependency, or closure statuses.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from domains.mapping.deed_to_ir.payloads.published_output import ALLOWED_CLOSURE_DIMENSION_IDS

from .correction_contract_card import (
    VALID_UPSTREAM_CORRECTION_POSTURES,
    build_upstream_correction_row_template_from_delta,
)
from .dependency_decisions import render_missing_dependency_decision_lines
from .persistence_io import refusal

VALID_RECOMMENDED_ACTIONS = frozenset(
    {
        "transcript_amendment",
        "ir_only_note",
        "dependency_block",
        "hitl_review",
    }
)


def build_missing_finalization_decisions_shell(
    *,
    scope_ids: Sequence[str] | None = None,
    include_closure_dimensions: bool = True,
) -> dict[str, Any]:
    """Compact retry shell for missing agent-authored scope/closure decisions."""
    scopes = [
        {"scope_id": str(scope_id).strip()}
        for scope_id in (scope_ids or [])
        if str(scope_id or "").strip()
    ]
    shell: dict[str, Any] = {
        "scope_dispositions": scopes,
    }
    if include_closure_dimensions:
        shell["closure_dispositions"] = [
            {"dimension_id": dimension_id}
            for dimension_id in sorted(ALLOWED_CLOSURE_DIMENSION_IDS)
        ]
    return shell


def missing_finalization_decisions_refusal(
    *,
    missing_shell: Mapping[str, Any],
) -> dict[str, Any]:
    payload = refusal(
        "missing_finalization_decisions",
        "Intent-first prepare needs agent-authored scope and closure dispositions. "
        "Supply statuses (and any required rationale) for the listed decision shells; "
        "deterministic code will not invent them.",
    )
    payload["outputs"] = {
        "missing_finalization_decisions": dict(missing_shell),
        "repair_hint": (
            "Author status on each scope_dispositions and closure_dispositions entry "
            "(or pass full scope_results / closure_dimensions), then retry. "
            "reuse_agent_authored_finalization_state=true is optional when a prior "
            "agent-authored preview already exists."
        ),
    }
    return payload


def expand_compact_dispositions(
    *,
    scope_dispositions: Sequence[Mapping[str, Any]] | None,
    closure_dispositions: Sequence[Mapping[str, Any]] | None,
    mapping_artifact_ref: str | None = None,
    ir_artifact_ref: str | None = None,
) -> dict[str, Any]:
    """Expand agent-authored compact dispositions into strict package rows.

    Statuses must be agent-supplied. Deterministic code only copies them into
    strict row shape and may attach mechanical basis refs.
    """
    if not isinstance(scope_dispositions, list) or not scope_dispositions:
        return {
            **refusal(
                "scope_dispositions_required",
                "Intent-first prepare requires scope_dispositions with agent-authored status.",
            ),
        }
    if not isinstance(closure_dispositions, list) or not closure_dispositions:
        return {
            **refusal(
                "closure_dispositions_required",
                "Intent-first prepare requires closure_dispositions with agent-authored status.",
            ),
        }

    basis_refs: list[str] = []
    for ref in (ir_artifact_ref, mapping_artifact_ref):
        text = str(ref or "").strip()
        if text and text not in basis_refs:
            basis_refs.append(text)

    scope_results: list[dict[str, Any]] = []
    for index, row in enumerate(scope_dispositions):
        if not isinstance(row, Mapping):
            return refusal(
                "scope_disposition_invalid",
                f"scope_dispositions[{index}] must be an object.",
            )
        scope_id = str(row.get("scope_id") or "").strip()
        status = str(row.get("status") or "").strip()
        if not scope_id:
            return refusal(
                "scope_disposition_scope_id_required",
                f"scope_dispositions[{index}].scope_id is required.",
            )
        if not status:
            return refusal(
                "scope_disposition_status_required",
                f"scope_dispositions[{index}].status is required (agent-authored).",
            )
        expanded: dict[str, Any] = {
            "scope_id": scope_id,
            "status": status,
        }
        for optional_key in ("title", "summary"):
            value = row.get(optional_key)
            if isinstance(value, str) and value.strip():
                expanded[optional_key] = value.strip()
        for list_key in ("basis_refs", "blocker_refs", "dependency_refs"):
            value = row.get(list_key)
            if isinstance(value, list):
                expanded[list_key] = [str(item).strip() for item in value if str(item).strip()]
        if "basis_refs" not in expanded and basis_refs:
            expanded["basis_refs"] = list(basis_refs)
        scope_results.append(expanded)

    closure_dimensions: list[dict[str, Any]] = []
    present_ids: set[str] = set()
    for index, row in enumerate(closure_dispositions):
        if not isinstance(row, Mapping):
            return refusal(
                "closure_disposition_invalid",
                f"closure_dispositions[{index}] must be an object.",
            )
        dimension_id = str(row.get("dimension_id") or "").strip()
        status = str(row.get("status") or "").strip()
        if not dimension_id:
            return refusal(
                "closure_disposition_dimension_id_required",
                f"closure_dispositions[{index}].dimension_id is required.",
            )
        if dimension_id not in ALLOWED_CLOSURE_DIMENSION_IDS:
            return refusal(
                "closure_disposition_dimension_id_invalid",
                f"closure_dispositions[{index}].dimension_id is not a supported closure layer.",
            )
        if not status:
            return refusal(
                "closure_disposition_status_required",
                f"closure_dispositions[{index}].status is required (agent-authored).",
            )
        expanded_closure: dict[str, Any] = {
            "dimension_id": dimension_id,
            "status": status,
        }
        for optional_key in ("title", "summary"):
            value = row.get(optional_key)
            if isinstance(value, str) and value.strip():
                expanded_closure[optional_key] = value.strip()
        value = row.get("basis_refs")
        if isinstance(value, list):
            expanded_closure["basis_refs"] = [str(item).strip() for item in value if str(item).strip()]
        elif basis_refs:
            expanded_closure["basis_refs"] = list(basis_refs)
        closure_dimensions.append(expanded_closure)
        present_ids.add(dimension_id)

    missing_dims = sorted(ALLOWED_CLOSURE_DIMENSION_IDS - present_ids)
    if missing_dims:
        return {
            **refusal(
                "closure_dispositions_incomplete",
                "All four closure dimensions require agent-authored status.",
            ),
            "outputs": {
                "missing_finalization_decisions": {
                    "closure_dispositions": [{"dimension_id": dim} for dim in missing_dims],
                },
                "repair_hint": "Author status for each missing closure_dispositions entry.",
            },
        }

    return {
        "executed": True,
        "scope_results": scope_results,
        "closure_dimensions": closure_dimensions,
    }


def extract_agent_authored_finalization_state(
    prior_preview: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Reuse only explicitly agent-authored rows from a prior preview artifact."""
    if not isinstance(prior_preview, Mapping):
        return None
    scopes = prior_preview.get("scope_results")
    deps = prior_preview.get("external_dependencies")
    closure = prior_preview.get("closure_dimensions")
    notes = prior_preview.get("notes")
    if not isinstance(scopes, list) or not scopes:
        return None
    if not isinstance(closure, list) or not closure:
        return None
    present_ids = {
        str(row.get("dimension_id") or "").strip()
        for row in closure
        if isinstance(row, Mapping)
    }
    if not ALLOWED_CLOSURE_DIMENSION_IDS.issubset(present_ids):
        return None
    # Require agent-authored statuses (non-blank) on every scope and closure row.
    for row in scopes:
        if not isinstance(row, Mapping) or not str(row.get("status") or "").strip():
            return None
    for row in closure:
        if not isinstance(row, Mapping) or not str(row.get("status") or "").strip():
            return None
    return {
        "scope_results": list(scopes),
        "external_dependencies": list(deps) if isinstance(deps, list) else [],
        "closure_dimensions": list(closure),
        "notes": list(notes) if isinstance(notes, list) else [],
    }


def assemble_upstream_corrections_from_decisions(
    *,
    correction_decisions: Sequence[Mapping[str, Any]] | None,
    correction_posture: Mapping[str, Any] | None,
    mapping_artifact_ref: str,
    ir_artifact_ref: str,
) -> dict[str, Any]:
    """Assemble strict upstream_corrections from agent decisions + typed candidates.

    Returns ``{"executed": True, "rows": [...]}`` or a refusal payload.
    """
    posture = correction_posture if isinstance(correction_posture, Mapping) else {}
    active = bool(posture.get("active"))
    deltas = posture.get("candidate_deltas") if isinstance(posture.get("candidate_deltas"), list) else []
    decisions = list(correction_decisions or [])

    if active and not decisions:
        return {
            **refusal(
                "correction_decisions_required",
                "Correction posture is active. Author correction_decisions for each "
                "candidate target (posture, resolution_used_by_ir, recommended_action, rationale).",
            ),
            "outputs": {
                "correction_posture": {
                    "active": True,
                    "candidate_deltas": deltas,
                    "reason_codes": list(posture.get("reason_codes") or []),
                },
                "repair_hint": (
                    "Provide correction_decisions keyed by target_entity_id; "
                    "do not rebuild full upstream_corrections rows."
                ),
            },
        }

    if not decisions:
        return {"executed": True, "rows": []}

    delta_by_target: dict[str, Mapping[str, Any]] = {}
    for delta in deltas:
        if not isinstance(delta, Mapping):
            continue
        target = str(delta.get("target_entity_id") or "").strip()
        if target:
            delta_by_target[target] = delta

    rows: list[dict[str, Any]] = []
    for index, decision in enumerate(decisions):
        if not isinstance(decision, Mapping):
            return refusal(
                "correction_decision_invalid",
                f"correction_decisions[{index}] must be an object.",
            )
        target = str(decision.get("target_entity_id") or "").strip()
        if not target:
            return refusal(
                "correction_decision_target_required",
                f"correction_decisions[{index}].target_entity_id is required.",
            )
        posture_value = str(decision.get("posture") or "").strip()
        if posture_value not in VALID_UPSTREAM_CORRECTION_POSTURES:
            return refusal(
                "correction_decision_posture_invalid",
                f"correction_decisions[{index}].posture must be one of "
                f"{', '.join(VALID_UPSTREAM_CORRECTION_POSTURES)}.",
            )
        recommended = str(decision.get("recommended_action") or "").strip()
        if recommended not in VALID_RECOMMENDED_ACTIONS:
            return refusal(
                "correction_decision_recommended_action_required",
                f"correction_decisions[{index}].recommended_action is required and must be "
                f"agent-authored ({', '.join(sorted(VALID_RECOMMENDED_ACTIONS))}).",
            )
        rationale = str(decision.get("rationale") or "").strip()
        if not rationale:
            return refusal(
                "correction_decision_rationale_required",
                f"correction_decisions[{index}].rationale is required.",
            )
        if "resolution_used_by_ir" not in decision:
            return refusal(
                "correction_decision_resolution_used_by_ir_required",
                f"correction_decisions[{index}].resolution_used_by_ir is required.",
            )
        resolution_used = bool(decision.get("resolution_used_by_ir"))

        delta = delta_by_target.get(target)
        if delta is None and active:
            return refusal(
                "correction_decision_target_unknown",
                f"No correction candidate for target_entity_id={target}.",
            )
        if delta is None:
            # Agent may still document a correction without an active detector hit,
            # but must supply values explicitly — we do not invent them.
            upstream = str(decision.get("upstream_value") or "").strip()
            corrected = str(decision.get("corrected_value") or "").strip()
            basis = decision.get("basis_refs")
            if not upstream or not corrected or not isinstance(basis, list) or not basis:
                return refusal(
                    "correction_decision_values_required",
                    f"Without an active candidate for {target}, supply upstream_value, "
                    "corrected_value, and basis_refs explicitly.",
                )
            row = {
                "correction_id": str(decision.get("correction_id") or f"correction_{target}").strip(),
                "target_entity_id": target,
                "target_entity_type": str(decision.get("target_entity_type") or "resolution_unit").strip(),
                "upstream_value": upstream,
                "corrected_value": corrected,
                "posture": posture_value,
                "resolution_used_by_ir": resolution_used,
                "recommended_action": recommended,
                "basis_refs": [str(ref).strip() for ref in basis if str(ref).strip()],
                "rationale": rationale,
            }
            if decision.get("title"):
                row["title"] = str(decision.get("title")).strip()
            rows.append(row)
            continue

        template = build_upstream_correction_row_template_from_delta(delta)
        correction_id = str(decision.get("correction_id") or "").strip()
        if not correction_id:
            correction_id = f"correction_{target}"
        basis_refs = list(template.get("basis_refs") or [])
        for ref in (ir_artifact_ref, mapping_artifact_ref):
            text = str(ref or "").strip()
            if text and text not in basis_refs:
                basis_refs.append(text)
        row = {
            "correction_id": correction_id,
            "target_entity_id": target,
            "target_entity_type": str(
                decision.get("target_entity_type") or template.get("target_entity_type") or "resolution_unit"
            ).strip(),
            "upstream_value": template.get("upstream_value"),
            "corrected_value": template.get("corrected_value"),
            "posture": posture_value,
            "resolution_used_by_ir": resolution_used,
            "recommended_action": recommended,
            "basis_refs": basis_refs,
            "rationale": rationale,
        }
        if decision.get("title"):
            row["title"] = str(decision.get("title")).strip()
        elif template.get("title"):
            row["title"] = template.get("title")
        # Typed selected value must never be the inherited raw.
        selected_display = str(delta.get("selected_ir_display_value") or delta.get("ir_value") or "").strip()
        if selected_display:
            row["corrected_value"] = selected_display
        rows.append(row)

    if active:
        decided_targets = {str(row.get("target_entity_id") or "").strip() for row in rows}
        missing = [
            str(delta.get("target_entity_id") or "").strip()
            for delta in deltas
            if isinstance(delta, Mapping)
            and str(delta.get("target_entity_id") or "").strip()
            and str(delta.get("target_entity_id") or "").strip() not in decided_targets
        ]
        if missing:
            return {
                **refusal(
                    "correction_decisions_incomplete",
                    "Correction posture is active but some candidate targets lack decisions.",
                ),
                "outputs": {
                    "missing_correction_targets": missing,
                    "repair_hint": "Author correction_decisions for each missing target_entity_id.",
                },
            }

    return {"executed": True, "rows": rows}


def build_intent_first_correction_summary(
    *,
    rows: Sequence[Mapping[str, Any]],
    correction_posture: Mapping[str, Any] | None,
) -> dict[str, Any]:
    posture = correction_posture if isinstance(correction_posture, Mapping) else {}
    deltas = posture.get("candidate_deltas") if isinstance(posture.get("candidate_deltas"), list) else []
    delta_by_target = {
        str(delta.get("target_entity_id") or "").strip(): delta
        for delta in deltas
        if isinstance(delta, Mapping) and str(delta.get("target_entity_id") or "").strip()
    }
    targets: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        target = str(row.get("target_entity_id") or "").strip()
        delta = delta_by_target.get(target) or {}
        entry: dict[str, Any] = {
            "target_entity_id": target,
            "upstream_value": row.get("upstream_value"),
            "resolution_used_by_ir": row.get("resolution_used_by_ir"),
        }
        selected = delta.get("selected_ir_value")
        if selected is not None:
            entry["selected_ir_value"] = selected
        else:
            # Fall back to corrected display only as string — do not invent typed value.
            entry["selected_ir_display_value"] = row.get("corrected_value")
        targets.append(entry)
    return {
        "active": bool(posture.get("active")),
        "rows_created": len(rows),
        "targets": targets,
    }


def render_missing_finalization_decisions_timeline_lines(
    outputs: Mapping[str, Any] | None,
    *,
    indent: str = "  ",
) -> list[str]:
    if not isinstance(outputs, Mapping):
        return []
    lines: list[str] = []
    shell = outputs.get("missing_finalization_decisions")
    if isinstance(shell, Mapping):
        lines.append(f"{indent}missing_finalization_decisions:")
        scopes = shell.get("scope_dispositions")
        if isinstance(scopes, list) and scopes:
            lines.append(f"{indent}  scope_dispositions:")
            for row in scopes:
                if isinstance(row, Mapping) and row.get("scope_id"):
                    status = row.get("status")
                    suffix = f" status={status}" if status else ""
                    lines.append(f"{indent}    - {row.get('scope_id')}{suffix}")
        closure = shell.get("closure_dispositions") or shell.get("closure_dimensions")
        if isinstance(closure, list) and closure:
            lines.append(f"{indent}  closure_dispositions:")
            for row in closure:
                if isinstance(row, Mapping) and row.get("dimension_id"):
                    status = row.get("status")
                    suffix = f" status={status}" if status else ""
                    lines.append(f"{indent}    - {row.get('dimension_id')}{suffix}")
    lines.extend(render_missing_dependency_decision_lines(outputs, indent=indent))
    return lines


def render_intent_first_prepare_timeline_lines(
    outputs: Mapping[str, Any] | None,
    *,
    indent: str = "  ",
) -> list[str]:
    if not isinstance(outputs, Mapping):
        return []
    lines: list[str] = []
    status = outputs.get("finalization_status")
    if status:
        lines.append(f"{indent}finalization_status: {status}")
    selected = outputs.get("selected_lineage")
    if isinstance(selected, Mapping):
        lines.append(f"{indent}selected_lineage:")
        mapping_ref = selected.get("mapping_artifact_ref")
        ir_ref = selected.get("expected_ir_artifact_ref")
        if mapping_ref:
            lines.append(f"{indent}  mapping: {mapping_ref}")
        if ir_ref:
            lines.append(f"{indent}  expected_ir: {ir_ref}")
    summary = outputs.get("correction_summary")
    if isinstance(summary, Mapping):
        lines.append(
            f"{indent}correction_summary: active={bool(summary.get('active'))} "
            f"rows_created={summary.get('rows_created', 0)}"
        )
        targets = summary.get("targets")
        if isinstance(targets, list):
            for row in targets:
                if not isinstance(row, Mapping):
                    continue
                target = row.get("target_entity_id") or ""
                upstream = row.get("upstream_value") or ""
                selected_val = row.get("selected_ir_value")
                if selected_val is None:
                    selected_val = row.get("selected_ir_display_value") or ""
                lines.append(
                    f"{indent}  - {target}: upstream={upstream} selected_ir={selected_val} "
                    f"resolution_used_by_ir={row.get('resolution_used_by_ir')}"
                )
    lines.extend(render_missing_finalization_decisions_timeline_lines(outputs, indent=indent))
    return lines
