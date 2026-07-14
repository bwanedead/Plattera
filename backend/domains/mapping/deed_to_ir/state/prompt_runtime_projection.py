"""Per-turn deed-to-IR prompt runtime projection (domain-owned).

Harness loads this module via ``manifest.prompt_runtime_projection_module_ref``
and calls ``build_prompt_runtime_projection`` with opaque mechanical inputs.
Deterministic code projects lineage-aware handoff context only — it does not
mutate work-item status, relations, or blockers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from tooling.mapping.deed_to_ir.active_handoff_projection import (
    project_lineage_aware_handoff_context,
)
from tooling.mapping.deed_to_ir.mapping_lineage import read_current_mapping_lineage

PROJECTION_SCHEMA = "deed_to_ir.prompt_runtime_projection.v1"


def build_prompt_runtime_projection(
    *,
    launch_context: Mapping[str, Any] | None = None,
    resolution_items: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Build lineage-aware handoff projection for the live choose_action prompt.

    Returns None when there is nothing mechanical to project. When present, the
    payload is opaque to the harness (``run_context.domain_runtime_projection``).
    """
    launch = launch_context if isinstance(launch_context, Mapping) else {}
    dossier_id = str(launch.get("dossier_id") or "").strip()
    if not dossier_id:
        return None

    lineage = read_current_mapping_lineage(
        dossier_id=dossier_id,
        transcription_id=_optional_text(launch.get("transcription_id")),
        workspace_id=_optional_text(launch.get("workspace_id")),
        run_id=_optional_text(launch.get("run_id")),
    )
    items = [dict(item) for item in (resolution_items or ()) if isinstance(item, Mapping)]
    projected = project_lineage_aware_handoff_context(lineage=lineage, work_items=items)
    if not projected:
        return None

    out: dict[str, Any] = {
        "schema": PROJECTION_SCHEMA,
        "domain_id": "deed_to_ir",
        **projected,
    }
    active = projected.get("active_handoff_context")
    if isinstance(active, Mapping):
        hot_refs: list[str] = []
        for key in ("mapping_artifact_ref", "source_ir_artifact_ref"):
            ref = str(active.get(key) or "").strip()
            if ref:
                hot_refs.append(ref)
        if hot_refs:
            # Mechanical hint only: harness may union these into exact-ref windowing.
            out["hot_artifact_refs"] = hot_refs

    cold_refs = _cold_refs_from_historical(projected.get("historical_lineage_context"))
    if cold_refs:
        # Historical mapping/IR refs must be demoted from generic exact-ref windowing.
        out["cold_artifact_refs"] = cold_refs
    return out


def _cold_refs_from_historical(historical: object) -> list[str]:
    if not isinstance(historical, Mapping):
        return []
    items = historical.get("items")
    if not isinstance(items, list):
        return []
    cold: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, Mapping):
            continue
        tied = item.get("tied_artifact_refs")
        if not isinstance(tied, list):
            continue
        for raw in tied:
            ref = str(raw or "").strip()
            if ref and ref not in seen:
                seen.add(ref)
                cold.append(ref)
    return cold


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None
