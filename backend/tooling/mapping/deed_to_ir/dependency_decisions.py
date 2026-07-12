"""Dependency-decision mechanics for deed-to-IR intent-first finalization.

Agent owns include / decline / status / rationale. Deterministic code expands
accepted candidates into strict external-dependency rows and refuses silent omission.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .dependency_candidates_projection import (
    compact_dependency_candidate_diagnostics_for_projection,
    compact_known_dependency_candidates_for_projection,
)
from .persistence_io import retryable_refusal

VALID_DEPENDENCY_DISPOSITIONS = frozenset({"include", "not_applicable"})


def _build_candidate_lookup(
    candidates: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, str]]:
    """Index known candidates by canonical candidate_id and identifier aliases."""
    by_candidate_id: dict[str, Mapping[str, Any]] = {}
    identifier_to_candidate_id: dict[str, str] = {}
    for row in candidates:
        candidate_id = str(row.get("candidate_id") or "").strip()
        if not candidate_id:
            continue
        by_candidate_id[candidate_id] = row
        identifier_to_candidate_id[candidate_id] = candidate_id
        dependency_id = str(row.get("dependency_id") or candidate_id).strip()
        if dependency_id:
            identifier_to_candidate_id.setdefault(dependency_id, candidate_id)
    return by_candidate_id, identifier_to_candidate_id


def _resolve_identifier_to_candidate_id(
    raw: str,
    *,
    identifier_to_candidate_id: Mapping[str, str],
) -> str | None:
    candidate_id = identifier_to_candidate_id.get(raw)
    return candidate_id if candidate_id else None


def _resolve_decision_candidate_id(
    decision: Mapping[str, Any],
    *,
    identifier_to_candidate_id: Mapping[str, str],
    index: int,
) -> dict[str, Any]:
    """Resolve a decision reference to a known candidate_id or return a refusal."""
    candidate_id_field = str(decision.get("candidate_id") or "").strip()
    dependency_id_field = str(decision.get("dependency_id") or "").strip()

    if candidate_id_field and dependency_id_field:
        resolved_from_candidate = _resolve_identifier_to_candidate_id(
            candidate_id_field,
            identifier_to_candidate_id=identifier_to_candidate_id,
        )
        resolved_from_dependency = _resolve_identifier_to_candidate_id(
            dependency_id_field,
            identifier_to_candidate_id=identifier_to_candidate_id,
        )
        if resolved_from_candidate != resolved_from_dependency:
            return retryable_refusal(
                "dependency_decision_identifier_conflict",
                (
                    f"dependency_decisions[{index}] supplies conflicting identifiers: "
                    f"candidate_id={candidate_id_field}, dependency_id={dependency_id_field}."
                ),
            )
        if not resolved_from_candidate:
            return retryable_refusal(
                "dependency_decision_candidate_unknown",
                (
                    f"No known dependency candidate for candidate_id={candidate_id_field} "
                    f"or dependency_id={dependency_id_field}."
                ),
            )
        return {"candidate_id": resolved_from_candidate}

    identifier = candidate_id_field or dependency_id_field
    if not identifier:
        return retryable_refusal(
            "dependency_decision_candidate_id_required",
            (
                f"dependency_decisions[{index}] requires candidate_id or dependency_id "
                "referencing a known projected candidate."
            ),
        )

    resolved = _resolve_identifier_to_candidate_id(
        identifier,
        identifier_to_candidate_id=identifier_to_candidate_id,
    )
    if not resolved:
        return retryable_refusal(
            "dependency_decision_candidate_unknown",
            f"No known dependency candidate for identifier={identifier}.",
        )
    return {"candidate_id": resolved}


def build_dependency_decision_shell(
    *,
    candidates: Sequence[Mapping[str, Any]],
    uncovered_candidate_ids: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Compact retry shell for undecided known dependency candidates."""
    uncovered = {
        str(item).strip()
        for item in (uncovered_candidate_ids or [])
        if str(item or "").strip()
    }
    shell: list[dict[str, Any]] = []
    for row in candidates:
        if not isinstance(row, Mapping):
            continue
        candidate_id = str(row.get("candidate_id") or "").strip()
        if not candidate_id:
            continue
        if uncovered and candidate_id not in uncovered:
            continue
        shell.append(
            {
                "candidate_id": candidate_id,
                "affected_scope": row.get("affected_scope"),
                "disposition": None,
                "status": None,
                "rationale": None,
            }
        )
    return shell


def dependency_decisions_required_refusal(
    *,
    candidates: Sequence[Mapping[str, Any]],
    uncovered_candidate_ids: Sequence[str] | None = None,
    diagnostics: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    uncovered = {
        str(item).strip()
        for item in (uncovered_candidate_ids or [])
        if str(item or "").strip()
    }
    missing: list[dict[str, Any]] = []
    for row in candidates:
        if not isinstance(row, Mapping):
            continue
        candidate_id = str(row.get("candidate_id") or "").strip()
        if not candidate_id:
            continue
        if uncovered and candidate_id not in uncovered:
            continue
        missing.append(
            {
                "candidate_id": candidate_id,
                "affected_scope": row.get("affected_scope"),
            }
        )
    outputs: dict[str, Any] = {
        "error": {
            "code": "dependency_decisions_required",
            "message": (
                "Known dependency candidates exist. Author dependency_decisions to include or "
                "explicitly decline each candidate before preview."
            ),
        },
        "missing_dependency_decisions": missing,
        "dependency_decision_shell": build_dependency_decision_shell(
            candidates=candidates,
            uncovered_candidate_ids=uncovered_candidate_ids,
        ),
        "known_dependency_candidates": compact_known_dependency_candidates_for_projection(
            list(candidates)
        ),
        "repair_hint": (
            "For each candidate, author dependency_decisions with disposition "
            "include (plus status) or not_applicable (plus rationale)."
        ),
    }
    compact_diagnostics = compact_dependency_candidate_diagnostics_for_projection(diagnostics)
    if compact_diagnostics:
        outputs["dependency_candidate_diagnostics"] = compact_diagnostics
    return {
        "executed": False,
        "reason_codes": ["dependency_decisions_required"],
        "refusal": {
            "reason_code": "dependency_decisions_required",
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": outputs,
    }


def merge_external_dependency_rows(
    *,
    existing_rows: Sequence[Mapping[str, Any]] | None,
    included_rows: Sequence[Mapping[str, Any]] | None,
    declined_candidate_ids: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Merge reused/explicit rows with newly included rows; strip declined ids."""
    declined = {
        str(item).strip()
        for item in (declined_candidate_ids or [])
        if str(item or "").strip()
    }
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in list(existing_rows or []) + list(included_rows or []):
        if not isinstance(row, Mapping):
            continue
        dep_id = str(row.get("dependency_id") or "").strip()
        if not dep_id or dep_id in declined or dep_id in seen:
            continue
        merged.append(dict(row))
        seen.add(dep_id)
    return merged


def dependency_ids_covering_candidates(
    *,
    external_dependencies: Sequence[Mapping[str, Any]] | None,
    candidates: Sequence[Mapping[str, Any]] | None,
) -> set[str]:
    """Return candidate_ids covered by existing agent-authored dependency rows."""
    covered: set[str] = set()
    if not isinstance(external_dependencies, list) or not isinstance(candidates, list):
        return covered
    dep_ids = {
        str(row.get("dependency_id") or "").strip()
        for row in external_dependencies
        if isinstance(row, Mapping) and str(row.get("dependency_id") or "").strip()
    }
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        candidate_id = str(candidate.get("candidate_id") or "").strip()
        dependency_id = str(candidate.get("dependency_id") or candidate_id).strip()
        if candidate_id and (candidate_id in dep_ids or dependency_id in dep_ids):
            covered.add(candidate_id)
    return covered


def assemble_external_dependencies_from_decisions(
    *,
    dependency_decisions: Sequence[Mapping[str, Any]] | None,
    candidates: Sequence[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Assemble strict external_dependencies from agent decisions + known candidates.

    Returns ``{"executed": True, "rows": [...], "declined_candidate_ids": [...]}``
    or a refusal payload.
    """
    candidate_list = [row for row in (candidates or []) if isinstance(row, Mapping)]
    by_id, identifier_to_candidate_id = _build_candidate_lookup(candidate_list)

    decisions = list(dependency_decisions or [])
    if candidate_list and not decisions:
        return dependency_decisions_required_refusal(candidates=candidate_list)

    rows: list[dict[str, Any]] = []
    declined: list[str] = []
    decided: set[str] = set()

    for index, decision in enumerate(decisions):
        if not isinstance(decision, Mapping):
            return retryable_refusal(
                "dependency_decision_invalid",
                f"dependency_decisions[{index}] must be an object.",
            )
        candidate_id_field = str(decision.get("candidate_id") or "").strip()
        dependency_id_field = str(decision.get("dependency_id") or "").strip()
        disposition = str(decision.get("disposition") or "").strip()
        if disposition not in VALID_DEPENDENCY_DISPOSITIONS:
            return retryable_refusal(
                "dependency_decision_disposition_invalid",
                f"dependency_decisions[{index}].disposition must be include or not_applicable.",
            )

        resolved = _resolve_decision_candidate_id(
            decision,
            identifier_to_candidate_id=identifier_to_candidate_id,
            index=index,
        )
        if "candidate_id" in resolved:
            candidate_id = resolved["candidate_id"]
        elif disposition == "not_applicable":
            fallback = candidate_id_field or dependency_id_field
            if not fallback:
                return resolved
            candidate_id = fallback
        else:
            return resolved

        candidate = by_id.get(candidate_id)
        if candidate is None and disposition == "include":
            return retryable_refusal(
                "dependency_decision_candidate_unknown",
                f"No known dependency candidate for candidate_id={candidate_id}.",
            )

        decided.add(candidate_id)
        if disposition == "not_applicable":
            rationale = str(decision.get("rationale") or "").strip()
            if not rationale:
                return retryable_refusal(
                    "dependency_decision_rationale_required",
                    f"dependency_decisions[{index}].rationale is required when disposition=not_applicable.",
                )
            declined.append(candidate_id)
            continue

        status = str(decision.get("status") or "").strip()
        if not status:
            return retryable_refusal(
                "dependency_decision_status_required",
                f"dependency_decisions[{index}].status is required when disposition=include.",
            )
        assert candidate is not None
        dependency_id = str(
            decision.get("dependency_id") or candidate.get("dependency_id") or candidate_id
        ).strip()
        row = {
            "dependency_id": dependency_id,
            "affected_scope": str(candidate.get("affected_scope") or "").strip(),
            "description": str(candidate.get("description") or "").strip(),
            "status": status,
            "available_refs": list(candidate.get("available_refs") or []),
        }
        if not row["affected_scope"] or not row["description"]:
            return retryable_refusal(
                "dependency_candidate_incomplete",
                f"Known candidate {candidate_id} is missing affected_scope or description.",
            )
        rows.append(row)

    uncovered = [
        str(row.get("candidate_id") or "").strip()
        for row in candidate_list
        if str(row.get("candidate_id") or "").strip()
        and str(row.get("candidate_id") or "").strip() not in decided
    ]
    if uncovered:
        return dependency_decisions_required_refusal(
            candidates=candidate_list,
            uncovered_candidate_ids=uncovered,
        )

    return {
        "executed": True,
        "rows": rows,
        "declined_candidate_ids": declined,
    }


def resolve_intent_first_external_dependencies(
    *,
    known_candidates: Sequence[Mapping[str, Any]] | None,
    external_dependencies: Sequence[Mapping[str, Any]] | None,
    dependency_decisions: Sequence[Mapping[str, Any]] | None,
    diagnostics: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve external_dependencies for intent-first prepare (mechanical only).

    Pending known candidates require agent decisions. Reused/explicit rows cover
    matching candidates. Explicit ``not_applicable`` strips matching rows even when
    previously reused. Never invents rows from candidate facts alone.
    """
    candidates = [row for row in (known_candidates or []) if isinstance(row, Mapping)]
    existing = (
        [row for row in external_dependencies if isinstance(row, Mapping)]
        if isinstance(external_dependencies, list)
        else []
    )
    covered = dependency_ids_covering_candidates(
        external_dependencies=existing or None,
        candidates=candidates,
    )
    pending = [
        row
        for row in candidates
        if str(row.get("candidate_id") or "").strip()
        and str(row.get("candidate_id") or "").strip() not in covered
    ]

    decisions_provided = isinstance(dependency_decisions, list)
    if pending and not decisions_provided:
        return dependency_decisions_required_refusal(
            candidates=pending,
            uncovered_candidate_ids=[
                str(row.get("candidate_id") or "").strip() for row in pending
            ],
            diagnostics=diagnostics,
        )

    if not decisions_provided:
        return {
            "executed": True,
            "rows": existing,
            "diagnostics": list(diagnostics or []),
        }

    assembled = assemble_external_dependencies_from_decisions(
        dependency_decisions=dependency_decisions,
        candidates=pending,
    )
    if assembled.get("executed") is not True:
        if diagnostics and isinstance(assembled.get("outputs"), dict):
            compact = compact_dependency_candidate_diagnostics_for_projection(diagnostics)
            if compact and "dependency_candidate_diagnostics" not in assembled["outputs"]:
                assembled["outputs"]["dependency_candidate_diagnostics"] = compact
        return assembled

    return {
        "executed": True,
        "rows": merge_external_dependency_rows(
            existing_rows=existing,
            included_rows=assembled.get("rows") if isinstance(assembled.get("rows"), list) else [],
            declined_candidate_ids=assembled.get("declined_candidate_ids")
            if isinstance(assembled.get("declined_candidate_ids"), list)
            else [],
        ),
        "diagnostics": list(diagnostics or []),
    }


def render_missing_dependency_decision_lines(
    outputs: Mapping[str, Any] | None,
    *,
    indent: str = "  ",
) -> list[str]:
    """Narrow timeline lines for missing dependency decisions / scope diagnostics."""
    if not isinstance(outputs, Mapping):
        return []
    lines: list[str] = []
    missing_deps = outputs.get("missing_dependency_decisions")
    if isinstance(missing_deps, list) and missing_deps:
        lines.append(f"{indent}missing_dependency_decisions:")
        for row in missing_deps:
            if not isinstance(row, Mapping):
                continue
            candidate_id = row.get("candidate_id") or ""
            affected = row.get("affected_scope") or ""
            lines.append(f"{indent}  - {candidate_id} affected_scope={affected}")
    diagnostics = outputs.get("dependency_candidate_diagnostics")
    if isinstance(diagnostics, list) and diagnostics:
        lines.append(f"{indent}dependency_candidate_diagnostics:")
        for row in diagnostics:
            if not isinstance(row, Mapping):
                continue
            code = row.get("code") or ""
            candidate_id = row.get("candidate_id") or ""
            observed = row.get("observed_scope_ids")
            observed_text = ""
            if isinstance(observed, list) and observed:
                observed_text = f" observed=[{', '.join(str(item) for item in observed)}]"
            lines.append(f"{indent}  - {code} candidate_id={candidate_id}{observed_text}")
    return lines
