"""Mechanical known-dependency candidate projection for deed-to-IR intent-first prepare.

Candidates are evidence/context only — not durable dependency rows and not a
deterministic conclusion that a dependency applies. Agent must include or decline.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .mapping_operands_projection import _infer_parcel_id, _is_scope_blocker_item

MAX_DEPENDENCY_CANDIDATES = 16
MAX_DESCRIPTION_CHARS = 512
MAX_AVAILABLE_REFS = 8


def build_known_dependency_candidates(
    *,
    resolution_state_snapshot: Mapping[str, Any] | None,
    issues: Sequence[Mapping[str, Any]] | None = None,
    resolution_state_ref: str | None = None,
) -> list[dict[str, Any]]:
    """Project known inherited dependency candidates from explicit upstream facts.

    Sources (copy-only joins):
    - resolution items that are scope blockers with missing-source / blocks / mapping-blocking issue
    - ``blocks`` relations for affected-scope linkage
    - mapping-blocking issues for description text
    """
    if not isinstance(resolution_state_snapshot, Mapping):
        return []

    items = resolution_state_snapshot.get("items")
    if not isinstance(items, list):
        return []

    blocking_issues = _index_mapping_blocking_issues(issues)
    blocks_targets = _index_blocks_targets(resolution_state_snapshot.get("relations"))

    candidates: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        if not _is_scope_blocker_item(item):
            continue
        item_id = str(item.get("item_id") or "").strip()
        if not item_id:
            continue
        kind = str(item.get("kind") or "").lower()
        has_blocks = item_id in blocks_targets
        has_blocking_issue = item_id in blocking_issues
        if kind != "missing_source_scope" and not has_blocks and not has_blocking_issue:
            continue

        affected_scope = _resolve_affected_scope(
            item_id=item_id,
            block_targets=blocks_targets.get(item_id) or [],
            issue=blocking_issues.get(item_id),
        )
        if not affected_scope:
            continue

        description = _resolve_description(
            item=item,
            issue=blocking_issues.get(item_id),
        )
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
    return candidates


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


def _resolve_affected_scope(
    *,
    item_id: str,
    block_targets: Sequence[str],
    issue: Mapping[str, Any] | None,
) -> str | None:
    for target in block_targets:
        parcel = _infer_parcel_id(unit_id=target, parent_item_id=target)
        if parcel:
            return parcel
    parcel = _infer_parcel_id(unit_id=item_id, parent_item_id=item_id)
    if parcel:
        return parcel
    if isinstance(issue, Mapping):
        scope_text = str(issue.get("scope") or "").strip().lower()
        match = _infer_parcel_id(unit_id=scope_text.replace(" ", "_"), parent_item_id=scope_text)
        if match:
            return match
        # Common prose: "Parcel 2 after ..."
        if "parcel 2" in scope_text or "parcel_2" in scope_text:
            return "parcel_2"
        if "parcel 1" in scope_text or "parcel_1" in scope_text:
            return "parcel_1"
    return None


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
