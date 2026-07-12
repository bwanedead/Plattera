"""Mechanical known-dependency candidate projection for deed-to-IR intent-first prepare.

Candidates are evidence/context only — not durable dependency rows and not a
deterministic conclusion that a dependency applies. Agent must include or decline.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .resolution_scope import (
    SCOPE_SIGNALS_CONFLICT_CODE,
    collect_resolution_scope_signals,
    is_resolution_scope_blocker,
    resolve_unambiguous_scope_id,
)

MAX_DEPENDENCY_CANDIDATES = 16
MAX_DESCRIPTION_CHARS = 512
MAX_AVAILABLE_REFS = 8
MAX_SCOPE_DIAGNOSTICS = 16


def project_known_dependency_candidates(
    *,
    resolution_state_snapshot: Mapping[str, Any] | None,
    issues: Sequence[Mapping[str, Any]] | None = None,
    resolution_state_ref: str | None = None,
) -> dict[str, Any]:
    """Project candidates plus mechanical diagnostics from explicit upstream facts.

    Returns ``{"candidates": [...], "diagnostics": [...]}``.
    Diagnostics are observability only — never dependency rows or blockers.
    """
    if not isinstance(resolution_state_snapshot, Mapping):
        return {"candidates": [], "diagnostics": []}

    items = resolution_state_snapshot.get("items")
    if not isinstance(items, list):
        return {"candidates": [], "diagnostics": []}

    blocking_issues = _index_mapping_blocking_issues(issues)
    blocks_targets = _index_blocks_targets(resolution_state_snapshot.get("relations"))

    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        if not is_resolution_scope_blocker(item):
            continue
        item_id = str(item.get("item_id") or "").strip()
        if not item_id:
            continue
        kind = str(item.get("kind") or "").lower()
        has_blocks = item_id in blocks_targets
        has_blocking_issue = item_id in blocking_issues
        if kind != "missing_source_scope" and not has_blocks and not has_blocking_issue:
            continue

        issue = blocking_issues.get(item_id)
        block_targets = blocks_targets.get(item_id) or []
        signals = collect_resolution_scope_signals(
            item=item,
            issue=issue if isinstance(issue, Mapping) else None,
            block_targets=block_targets,
            identifier_sources=[item_id, *block_targets],
        )
        resolved = resolve_unambiguous_scope_id(signals)
        if resolved.get("conflict") is True:
            if len(diagnostics) < MAX_SCOPE_DIAGNOSTICS:
                diagnostics.append(
                    {
                        "code": SCOPE_SIGNALS_CONFLICT_CODE,
                        "candidate_id": item_id,
                        "observed_scope_ids": list(resolved.get("observed_scope_ids") or []),
                    }
                )
            continue

        affected_scope = resolved.get("scope_id")
        if not affected_scope:
            continue

        description = _resolve_description(item=item, issue=issue if isinstance(issue, Mapping) else None)
        if not description:
            continue

        available_refs = _bound_refs(item.get("evidence_refs"))
        candidate: dict[str, Any] = {
            "candidate_id": item_id,
            "dependency_id": item_id,
            "affected_scope": affected_scope,
            "description": description,
            "available_refs": available_refs,
        }
        if resolution_state_ref:
            candidate["basis_refs"] = [str(resolution_state_ref).strip()]
        candidates.append(candidate)
        if len(candidates) >= MAX_DEPENDENCY_CANDIDATES:
            break

    return {"candidates": candidates, "diagnostics": diagnostics}


def compact_known_dependency_candidates_for_projection(
    candidates: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not isinstance(candidates, list):
        return []
    compact: list[dict[str, Any]] = []
    for row in candidates:
        if not isinstance(row, Mapping):
            continue
        candidate_id = str(row.get("candidate_id") or "").strip()
        if not candidate_id:
            continue
        entry: dict[str, Any] = {
            "candidate_id": candidate_id,
            "dependency_id": row.get("dependency_id") or candidate_id,
            "affected_scope": row.get("affected_scope"),
        }
        if row.get("description"):
            entry["description"] = row.get("description")
        compact.append(entry)
    return compact


def compact_dependency_candidate_diagnostics_for_projection(
    diagnostics: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not isinstance(diagnostics, list):
        return []
    compact: list[dict[str, Any]] = []
    for row in diagnostics:
        if not isinstance(row, Mapping):
            continue
        code = str(row.get("code") or "").strip()
        if not code:
            continue
        entry: dict[str, Any] = {"code": code}
        if row.get("candidate_id"):
            entry["candidate_id"] = row.get("candidate_id")
        observed = row.get("observed_scope_ids")
        if isinstance(observed, list):
            entry["observed_scope_ids"] = [
                str(item).strip() for item in observed if str(item or "").strip()
            ]
        compact.append(entry)
    return compact


def _index_mapping_blocking_issues(
    issues: Sequence[Mapping[str, Any]] | None,
) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    if not isinstance(issues, list):
        return indexed
    for row in issues:
        if not isinstance(row, Mapping):
            continue
        if row.get("mapping_blocking") is not True:
            continue
        issue_id = str(row.get("issue_id") or "").strip()
        if issue_id:
            indexed[issue_id] = row
    return indexed


def _index_blocks_targets(relations: Any) -> dict[str, list[str]]:
    indexed: dict[str, list[str]] = {}
    if not isinstance(relations, list):
        return indexed
    for row in relations:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("relation_type") or "").lower() != "blocks":
            continue
        source = str(row.get("source_item_id") or "").strip()
        target = str(row.get("target_item_id") or "").strip()
        if not source or not target:
            continue
        indexed.setdefault(source, [])
        if target not in indexed[source]:
            indexed[source].append(target)
    return indexed


def _resolve_description(
    *,
    item: Mapping[str, Any],
    issue: Mapping[str, Any] | None,
) -> str | None:
    for source in (
        (issue or {}).get("summary") if isinstance(issue, Mapping) else None,
        item.get("summary"),
        item.get("title"),
        item.get("determined_value"),
        (issue or {}).get("downstream_disposition") if isinstance(issue, Mapping) else None,
    ):
        text = str(source or "").strip()
        if text:
            if len(text) > MAX_DESCRIPTION_CHARS:
                return text[: MAX_DESCRIPTION_CHARS - 1].rstrip() + "…"
            return text
    return None


def _bound_refs(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    refs: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text and text not in refs:
            refs.append(text)
        if len(refs) >= MAX_AVAILABLE_REFS:
            break
    return refs
