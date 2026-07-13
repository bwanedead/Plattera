"""Unified intent-first finalization decision preflight (mechanical only).

Aggregates absent decision lanes into one retryable card. Does not validate final
rows, persist state, or author semantic decisions.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from domains.mapping.deed_to_ir.payloads.published_output import ALLOWED_CLOSURE_DIMENSION_IDS

from .dependency_candidates_projection import (
    compact_known_dependency_candidates_for_projection,
)
from .dependency_decisions import dependency_ids_covering_candidates
from .persistence_io import retryable_refusal

_PREFLIGHT_REASON = "missing_finalization_decisions"


def evaluate_intent_first_decision_preflight(
    *,
    scope_dispositions: Any = None,
    closure_dispositions: Any = None,
    correction_decisions: Any = None,
    dependency_decisions: Any = None,
    scope_results: Any = None,
    closure_dimensions: Any = None,
    external_dependencies: Any = None,
    upstream_corrections: Any = None,
    correction_posture: Mapping[str, Any] | None = None,
    known_dependency_candidates: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return ``{"complete": True}`` or a retryable unified decision-card refusal."""
    posture = correction_posture if isinstance(correction_posture, Mapping) else {}
    candidates = [
        row for row in (known_dependency_candidates or []) if isinstance(row, Mapping)
    ]
    covered = dependency_ids_covering_candidates(
        external_dependencies=external_dependencies
        if isinstance(external_dependencies, list)
        else None,
        candidates=candidates,
    )
    uncovered = [
        row
        for row in candidates
        if str(row.get("candidate_id") or "").strip()
        and str(row.get("candidate_id") or "").strip() not in covered
    ]

    required_lanes: list[str] = []
    card: dict[str, Any] = {
        "required_lanes": required_lanes,
        "scope_dispositions": [],
        "closure_dispositions": [],
        "correction_decisions": [],
        "dependency_decisions": [],
    }

    scope_present = scope_results is not None or isinstance(scope_dispositions, list)
    if not scope_present:
        required_lanes.append("scope_dispositions")
        # Empty shell only — never invent scope IDs or statuses.
        card["scope_dispositions"] = []

    closure_present = closure_dimensions is not None or isinstance(
        closure_dispositions, list
    )
    if not closure_present:
        required_lanes.append("closure_dispositions")
        card["closure_dispositions"] = [
            {"dimension_id": dimension_id}
            for dimension_id in sorted(ALLOWED_CLOSURE_DIMENSION_IDS)
        ]

    correction_active = bool(posture.get("active"))
    corrections_present = (
        upstream_corrections is not None
        or (isinstance(correction_decisions, list) and bool(correction_decisions))
    )
    if correction_active and not corrections_present:
        required_lanes.append("correction_decisions")
        card["correction_decisions"] = _correction_decision_shell(posture)

    dependency_present = isinstance(dependency_decisions, list) and bool(
        dependency_decisions
    )
    if uncovered and not dependency_present:
        # Covered by reuse/explicit rows already — uncovered empty; skip.
        required_lanes.append("dependency_decisions")
        card["dependency_decisions"] = _dependency_decision_shell(uncovered)

    if not required_lanes:
        return {"complete": True}

    missing_shell = {
        "scope_dispositions": list(card["scope_dispositions"]),
        "closure_dispositions": list(card["closure_dispositions"]),
    }
    if "correction_decisions" in required_lanes:
        missing_shell["correction_decisions"] = list(card["correction_decisions"])
    if "dependency_decisions" in required_lanes:
        missing_shell["dependency_decisions"] = list(card["dependency_decisions"])

    retry_template = build_retry_request_template(
        scope_dispositions=scope_dispositions,
        closure_dispositions=closure_dispositions,
        correction_decisions=correction_decisions,
        dependency_decisions=dependency_decisions,
    )

    payload = retryable_refusal(
        _PREFLIGHT_REASON,
        "Intent-first prepare needs agent-authored finalization decisions. "
        "Author statuses/dispositions for every required lane on the finalization "
        "decision card; deterministic code will not invent them.",
    )
    payload["outputs"] = {
        **payload["outputs"],
        "missing_finalization_decisions": missing_shell,
        "finalization_decision_card": card,
        "retry_request_template": retry_template,
        "repair_hint": (
            "At the first intent-first preview attempt, submit all required decision "
            "lanes together. If a finalization decision card is returned, resubmit "
            "retry_request_template plus the missing agent-authored decisions directly; "
            "do not hydrate artifacts merely to recover facts already present in the card. "
            "Carried-forward rows still require resubmission and normal validation."
        ),
    }
    return payload


def build_retry_request_template(
    *,
    scope_dispositions: Any = None,
    closure_dispositions: Any = None,
    correction_decisions: Any = None,
    dependency_decisions: Any = None,
) -> dict[str, Any]:
    """Inert carry-forward of supplied compact lanes (not acceptance or persistence)."""
    return {
        "use_current_mapping_lineage": True,
        "scope_dispositions": (
            list(scope_dispositions) if isinstance(scope_dispositions, list) else []
        ),
        "closure_dispositions": (
            list(closure_dispositions) if isinstance(closure_dispositions, list) else []
        ),
        "correction_decisions": (
            list(correction_decisions) if isinstance(correction_decisions, list) else []
        ),
        "dependency_decisions": (
            list(dependency_decisions) if isinstance(dependency_decisions, list) else []
        ),
    }


def render_finalization_decision_card_timeline_lines(
    outputs: Mapping[str, Any] | None,
    *,
    indent: str = "  ",
) -> list[str]:
    """Compact timeline for one unified finalization decision card."""
    if not isinstance(outputs, Mapping):
        return []
    card = outputs.get("finalization_decision_card")
    if not isinstance(card, Mapping):
        return []
    lines = [f"{indent}finalization_decision_card:"]
    required = card.get("required_lanes")
    if isinstance(required, list) and required:
        lines.append(
            f"{indent}  required_lanes: {', '.join(str(item) for item in required)}"
        )
    closure = card.get("closure_dispositions")
    if isinstance(closure, list) and closure:
        dims = [
            str(row.get("dimension_id") or "").strip()
            for row in closure
            if isinstance(row, Mapping) and str(row.get("dimension_id") or "").strip()
        ]
        if dims:
            lines.append(f"{indent}  closure_dimensions: {', '.join(dims)}")
    corrections = card.get("correction_decisions")
    if isinstance(corrections, list) and corrections:
        targets = [
            str(row.get("target_entity_id") or "").strip()
            for row in corrections
            if isinstance(row, Mapping) and str(row.get("target_entity_id") or "").strip()
        ]
        if targets:
            lines.append(f"{indent}  correction_targets: {', '.join(targets)}")
    deps = card.get("dependency_decisions")
    if isinstance(deps, list) and deps:
        lines.append(f"{indent}  dependency_candidates:")
        for row in deps:
            if not isinstance(row, Mapping):
                continue
            candidate_id = row.get("candidate_id") or row.get("dependency_id") or ""
            affected = row.get("affected_scope") or ""
            lines.append(f"{indent}    - {candidate_id} affected_scope={affected}")
    template = outputs.get("retry_request_template")
    has_carry = False
    if isinstance(template, Mapping):
        for key in (
            "scope_dispositions",
            "closure_dispositions",
            "correction_decisions",
            "dependency_decisions",
        ):
            value = template.get(key)
            if isinstance(value, list) and value:
                has_carry = True
                break
    lines.append(f"{indent}  retry_carry_forward: {'yes' if has_carry else 'no'}")
    return lines


def _correction_decision_shell(posture: Mapping[str, Any]) -> list[dict[str, Any]]:
    deltas = posture.get("candidate_deltas")
    if not isinstance(deltas, list):
        return []
    shell: list[dict[str, Any]] = []
    for delta in deltas:
        if not isinstance(delta, Mapping):
            continue
        target = str(delta.get("target_entity_id") or "").strip()
        if target:
            shell.append({"target_entity_id": target})
    return shell


def _dependency_decision_shell(
    candidates: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    compact = compact_known_dependency_candidates_for_projection(list(candidates))
    shell: list[dict[str, Any]] = []
    for row in compact:
        candidate_id = str(row.get("candidate_id") or "").strip()
        if not candidate_id:
            continue
        shell.append(
            {
                "candidate_id": candidate_id,
                "dependency_id": row.get("dependency_id") or candidate_id,
                "affected_scope": row.get("affected_scope"),
            }
        )
    return shell
