"""Prompt-safe projection for the derived atom evidence worklist."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .atom_evidence_worklist import KIND, build_atom_evidence_worklist

_UTIL_OPEN_PACKET_READY = "open_packet_ready_unused"
_UTIL_OPEN_PACKET_USED = "open_packet_used_not_determined"
_UTIL_OPEN_EVIDENCE_REF = "open_evidence_referenced_not_determined"

MAX_PROMPT_PRIORITY_ROWS = 12
MAX_PROMPT_PACKET_REFS_PER_ROW = 2
MAX_PROMPT_DELEGATE_REFS_PER_ROW = 2
MAX_PROMPT_UNMATCHED_REFS = 8

_PRIORITY_UTILIZATION_ORDER: tuple[str, ...] = (
    _UTIL_OPEN_PACKET_READY,
    _UTIL_OPEN_PACKET_USED,
    _UTIL_OPEN_EVIDENCE_REF,
)

_PRIORITY_RANK = {status: index for index, status in enumerate(_PRIORITY_UTILIZATION_ORDER)}


def build_atom_evidence_worklist_for_prompt(
    *,
    resolution_state: Mapping[str, Any] | None,
    recent_result_records: Sequence[Mapping[str, Any]] | None = None,
    delegate_result_records: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Build a bounded prompt observability block from loop memory inputs."""
    full = build_atom_evidence_worklist(
        resolution_state=resolution_state,
        recent_result_records=recent_result_records,
        delegate_result_records=delegate_result_records,
    )
    return project_atom_evidence_worklist_for_prompt(full)


def project_atom_evidence_worklist_for_prompt(
    full_worklist: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Drop-only projection: counts, prioritized open rows, unmatched packet refs."""
    if not isinstance(full_worklist, Mapping):
        return None

    atoms = full_worklist.get("atoms")
    if not isinstance(atoms, list):
        atoms = []

    priority_candidates = [
        row for row in atoms if isinstance(row, Mapping) and _is_priority_atom(row)
    ]
    priority_candidates.sort(
        key=lambda row: (
            _PRIORITY_RANK.get(str(row.get("utilization_status") or ""), 99),
            str(row.get("atom_id") or ""),
        )
    )

    priority_rows = [
        _compact_priority_row(row)
        for row in priority_candidates[:MAX_PROMPT_PRIORITY_ROWS]
    ]

    unmatched_raw = full_worklist.get("unmatched_packet_refs")
    unmatched_rows = [
        _compact_unmatched_row(row)
        for row in (unmatched_raw if isinstance(unmatched_raw, list) else [])
        if isinstance(row, Mapping)
    ][:MAX_PROMPT_UNMATCHED_REFS]

    counts = full_worklist.get("counts")
    if not isinstance(counts, Mapping):
        counts = {}

    if not priority_rows and not unmatched_rows:
        if not _has_interesting_counts(counts):
            return None

    out: dict[str, Any] = {
        "kind": str(full_worklist.get("kind") or KIND),
        "counts": dict(counts),
    }
    if priority_rows:
        out["priority_rows"] = priority_rows
    if unmatched_rows:
        out["unmatched_packet_refs"] = unmatched_rows
    return out


def compact_atom_evidence_worklist_for_prompt(
    block: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Compaction transport: preserve counts, priority rows, unmatched refs only."""
    if not isinstance(block, Mapping):
        return None

    counts = block.get("counts")
    priority_rows = block.get("priority_rows")
    unmatched_rows = block.get("unmatched_packet_refs")

    has_priority = isinstance(priority_rows, list) and bool(priority_rows)
    has_unmatched = isinstance(unmatched_rows, list) and bool(unmatched_rows)
    has_counts = isinstance(counts, Mapping) and _has_interesting_counts(counts)

    if not has_priority and not has_unmatched and not has_counts:
        return None

    out: dict[str, Any] = {"kind": str(block.get("kind") or KIND)}
    if isinstance(counts, Mapping):
        out["counts"] = dict(counts)
    if has_priority:
        out["priority_rows"] = [
            dict(row) for row in priority_rows[:MAX_PROMPT_PRIORITY_ROWS] if isinstance(row, Mapping)
        ]
    if has_unmatched:
        out["unmatched_packet_refs"] = [
            dict(row)
            for row in unmatched_rows[:MAX_PROMPT_UNMATCHED_REFS]
            if isinstance(row, Mapping)
        ]
    return out


def resolution_state_as_mapping(state: Any) -> Mapping[str, Any] | None:
    """Mechanical coercion of continuity resolution state for the worklist builder."""
    if state is None:
        return None
    if hasattr(state, "model_dump"):
        return state.model_dump(mode="json")
    if isinstance(state, Mapping):
        return state
    return None


def _counts_only_block(block: Mapping[str, Any]) -> dict[str, Any] | None:
    counts = block.get("counts")
    if not isinstance(counts, Mapping) or not _has_interesting_counts(counts):
        return None
    return {"kind": str(block.get("kind") or KIND), "counts": dict(counts)}


def _has_interesting_counts(counts: Mapping[str, Any]) -> bool:
    for key in (
        "packet_ready_unused",
        "packet_used_not_determined",
        "unmatched_packet_refs",
    ):
        try:
            if int(counts.get(key) or 0) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _is_priority_atom(row: Mapping[str, Any]) -> bool:
    return str(row.get("utilization_status") or "") in _PRIORITY_UTILIZATION_ORDER


def _compact_priority_row(atom: Mapping[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {
        "atom_id": atom.get("atom_id"),
        "status": atom.get("status"),
        "utilization_status": atom.get("utilization_status"),
    }
    packet_refs = atom.get("packet_refs")
    if isinstance(packet_refs, list) and packet_refs:
        row["packet_refs"] = [
            _compact_packet_ref(pref)
            for pref in packet_refs[:MAX_PROMPT_PACKET_REFS_PER_ROW]
            if isinstance(pref, Mapping)
        ]
    delegate_refs = atom.get("delegate_refs")
    if isinstance(delegate_refs, list) and delegate_refs:
        row["delegate_refs"] = [
            _compact_delegate_ref(pref)
            for pref in delegate_refs[:MAX_PROMPT_DELEGATE_REFS_PER_ROW]
            if isinstance(pref, Mapping)
        ]
    return row


def _compact_unmatched_row(row: Mapping[str, Any]) -> dict[str, Any]:
    out = _compact_packet_ref(row, include_match_kind=False)
    delegate_refs = row.get("delegate_refs")
    if isinstance(delegate_refs, list) and delegate_refs:
        out["delegate_refs"] = [
            _compact_delegate_ref(pref)
            for pref in delegate_refs[:MAX_PROMPT_DELEGATE_REFS_PER_ROW]
            if isinstance(pref, Mapping)
        ]
    return out


def _compact_packet_ref(
    pref: Mapping[str, Any],
    *,
    include_match_kind: bool = True,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "crop_ref": pref.get("crop_ref"),
        "overlay_ref": pref.get("overlay_ref"),
        "source_alias": pref.get("source_alias"),
        "letter": pref.get("letter"),
        "created_turn": pref.get("created_turn"),
    }
    target_atom_id = pref.get("target_atom_id")
    if target_atom_id:
        row["target_atom_id"] = target_atom_id
    target_hint = pref.get("target_hint")
    if target_hint:
        row["target_hint"] = target_hint
    if include_match_kind:
        match_kind = pref.get("match_kind")
        if match_kind:
            row["match_kind"] = match_kind
    nested = pref.get("delegate_refs")
    if isinstance(nested, list) and nested:
        row["delegate_refs"] = [
            _compact_delegate_ref(item)
            for item in nested[:MAX_PROMPT_DELEGATE_REFS_PER_ROW]
            if isinstance(item, Mapping)
        ]
    return {k: v for k, v in row.items() if v not in (None, "", [], {})}


def _compact_delegate_ref(pref: Mapping[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {
        "delegate_ref": pref.get("delegate_ref"),
        "delegate_alias": pref.get("delegate_alias"),
        "delegate_status": pref.get("delegate_status"),
    }
    context_refs = pref.get("context_refs")
    if isinstance(context_refs, list) and context_refs:
        row["context_refs"] = list(context_refs)[:MAX_PROMPT_DELEGATE_REFS_PER_ROW]
    if pref.get("created_turn") is not None:
        row["created_turn"] = pref.get("created_turn")
    return {k: v for k, v in row.items() if v not in (None, "", [], {})}
