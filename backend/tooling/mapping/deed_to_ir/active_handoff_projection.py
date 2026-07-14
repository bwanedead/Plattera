"""Lineage-aware active handoff context for deed-to-IR (mechanical projection only).

Builds a compact ``active_handoff_context`` from the persisted current mapping
lineage when that lineage is usable for the next preview. Optionally classifies
work items that carry explicit mapping/IR artifact refs as current vs historical
audit context — without mutating statuses, relations, or blockers.

Deterministic code never declares semantic acceptance, completion, or publish
authorization, and never upgrades a blocked scope into a handoff fact.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

LINEAGE_ARTIFACT_REF_PREFIXES = (
    "feature_graph:mapping:",
    "feature_graph:ir:",
)

HISTORICAL_CONTEXT_NOTE = (
    "Historical lineage context only — does not establish a defect in the current mapping."
)


def lineage_is_usable_for_next_preview(lineage: Mapping[str, Any] | None) -> bool:
    """True when lineage is current, not stale, and selected for next preview."""
    if not isinstance(lineage, Mapping) or not lineage:
        return False
    mapping_ref = str(lineage.get("mapping_artifact_ref") or "").strip()
    ir_ref = str(lineage.get("source_ir_artifact_ref") or "").strip()
    if not mapping_ref or not ir_ref:
        return False
    if lineage.get("stale") is True:
        return False
    if not lineage.get("lineage_current"):
        return False
    if not lineage.get("use_for_next_preview"):
        return False
    return True


def build_active_handoff_context(
    lineage: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Pure projection of usable current lineage as the sole hot mapping candidate.

    Returns None when lineage is absent, stale, incomplete, or not selected for
    next preview. Emits mechanical facts only.
    """
    if not lineage_is_usable_for_next_preview(lineage):
        return None
    assert isinstance(lineage, Mapping)
    context: dict[str, Any] = {
        "mapping_artifact_ref": str(lineage.get("mapping_artifact_ref") or "").strip(),
        "source_ir_artifact_ref": str(lineage.get("source_ir_artifact_ref") or "").strip(),
        "lineage_status": "current",
        "selected_for_next_preview": True,
    }
    if lineage.get("compile_gap_count") is not None:
        context["compile_gap_count"] = int(lineage.get("compile_gap_count"))
    if lineage.get("judge_gap_count") is not None:
        context["judge_gap_count"] = int(lineage.get("judge_gap_count"))
    return context


def current_lineage_artifact_refs(lineage: Mapping[str, Any] | None) -> frozenset[str]:
    if not isinstance(lineage, Mapping) or not lineage:
        return frozenset()
    refs: set[str] = set()
    for key in ("mapping_artifact_ref", "source_ir_artifact_ref"):
        value = str(lineage.get(key) or "").strip()
        if value:
            refs.add(value)
    return frozenset(refs)


def is_lineage_artifact_ref(ref: str) -> bool:
    text = str(ref or "").strip()
    return any(text.startswith(prefix) for prefix in LINEAGE_ARTIFACT_REF_PREFIXES)


def collect_item_lineage_artifact_refs(item: Mapping[str, Any] | None) -> frozenset[str]:
    """Collect explicit structured mapping/IR refs from a work item.

    Uses only ``evidence_refs`` list entries. Does not scrape prose or recurse
    into arbitrary payloads.
    """
    if not isinstance(item, Mapping):
        return frozenset()
    raw = item.get("evidence_refs")
    if not isinstance(raw, list):
        return frozenset()
    refs: set[str] = set()
    for entry in raw:
        text = str(entry or "").strip()
        if text and is_lineage_artifact_ref(text):
            refs.add(text)
    return frozenset(refs)


def classify_work_item_lineage_epoch(
    item: Mapping[str, Any] | None,
    *,
    current_refs: frozenset[str],
) -> str | None:
    """Classify a work item relative to current lineage refs.

    Returns:
      - ``\"current\"`` when the item cites any current lineage ref (including mixed)
      - ``\"historical\"`` when it cites only non-current mapping/IR refs
      - ``None`` when it carries no explicit lineage artifact refs, or when
        ``current_refs`` is empty (no usable current baseline — do not treat
        all lineage evidence as historical)
    """
    if not current_refs:
        return None
    item_refs = collect_item_lineage_artifact_refs(item)
    if not item_refs:
        return None
    if item_refs & current_refs:
        return "current"
    return "historical"


def project_lineage_aware_handoff_context(
    *,
    lineage: Mapping[str, Any] | None,
    work_items: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Project active handoff + historical lineage audit context.

    Does not mutate ``work_items`` or invent semantic handoff readiness from
    blocked scopes. Without a usable current lineage baseline, work items are
    left unclassified (not forced to historical).
    """
    projection: dict[str, Any] = {}
    active = build_active_handoff_context(lineage)
    if active is not None:
        projection["active_handoff_context"] = active

    # Classification requires a usable current baseline. Empty current_refs
    # must not mark every mapping/IR-tied item historical.
    if active is None:
        return projection
    current_refs = current_lineage_artifact_refs(lineage)
    if not current_refs:
        return projection

    historical_rows: list[dict[str, Any]] = []
    current_rows: list[dict[str, Any]] = []

    for raw_item in work_items or ():
        if not isinstance(raw_item, Mapping):
            continue
        # Copy for projection only — never mutate caller objects.
        item = dict(raw_item)
        epoch = classify_work_item_lineage_epoch(item, current_refs=current_refs)
        if epoch is None:
            continue
        row = _compact_work_item_lineage_row(item, lineage_epoch=epoch)
        if epoch == "historical":
            historical_rows.append(row)
        else:
            current_rows.append(row)

    if historical_rows:
        projection["historical_lineage_context"] = {
            "note": HISTORICAL_CONTEXT_NOTE,
            "items": historical_rows,
        }
    if current_rows:
        projection["current_lineage_work_items"] = current_rows
    return projection


def render_lineage_aware_handoff_prompt_lines(
    projection: Mapping[str, Any] | None,
    *,
    indent: str = "",
) -> list[str]:
    """Render prompt lines with active handoff before historical lineage context."""
    if not isinstance(projection, Mapping) or not projection:
        return []
    lines: list[str] = []
    active = projection.get("active_handoff_context")
    if isinstance(active, Mapping) and active:
        lines.append(f"{indent}active_handoff_context:")
        lines.append(f"{indent}  mapping_artifact_ref: {active.get('mapping_artifact_ref')}")
        lines.append(f"{indent}  source_ir_artifact_ref: {active.get('source_ir_artifact_ref')}")
        lines.append(f"{indent}  lineage_status: {active.get('lineage_status')}")
        lines.append(
            f"{indent}  selected_for_next_preview: {bool(active.get('selected_for_next_preview'))}"
        )
        if active.get("compile_gap_count") is not None or active.get("judge_gap_count") is not None:
            lines.append(
                f"{indent}  compile_gap_count: {active.get('compile_gap_count', 0)} "
                f"judge_gap_count: {active.get('judge_gap_count', 0)}"
            )

    historical = projection.get("historical_lineage_context")
    if isinstance(historical, Mapping) and historical:
        lines.append(f"{indent}historical_lineage_context:")
        note = historical.get("note")
        if note:
            lines.append(f"{indent}  note: {note}")
        items = historical.get("items")
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, Mapping):
                    continue
                item_id = item.get("item_id") or "?"
                lines.append(f"{indent}  - item_id={item_id} lineage_epoch=historical")
                tied = item.get("tied_artifact_refs")
                if isinstance(tied, list) and tied:
                    lines.append(f"{indent}    tied_artifact_refs: {', '.join(str(r) for r in tied)}")
    return lines


def _compact_work_item_lineage_row(
    item: Mapping[str, Any],
    *,
    lineage_epoch: str,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "item_id": item.get("item_id"),
        "lineage_epoch": lineage_epoch,
        "tied_artifact_refs": sorted(collect_item_lineage_artifact_refs(item)),
    }
    title = item.get("title")
    if isinstance(title, str) and title.strip():
        row["title"] = title.strip()
    # Preserve status for audit visibility only — do not alter it.
    if item.get("status") is not None:
        row["status"] = item.get("status")
    return row
