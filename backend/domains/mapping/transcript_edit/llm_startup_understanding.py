"""LLM-authored startup / orientation understanding (Phase 23).

Structured fields are produced by ``TX_ORIENT_AND_BASELINE`` and merged into native ledger
and blocker registry. Deterministic audit/validator output must not be the author of this surface.

Generic startup document shapes are defined in ``agent_kernel.orientation.startup_document``.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any

from agent_kernel.orientation.startup_document import (
    coerce_startup_understanding,
    fallback_decision_key_for_startup_merge,
    startup_understanding_has_minimum_viable,
)

from .blocker_registry_lifecycle import apply_proposed_emergent_blocker_updates
from .startup_posture import (
    transcript_layer_tag_from_startup_item,
    transcript_mapping_blocking_from_startup_item,
    transcript_operational_impact_from_startup_item,
)
from .transcript_edit_ledger_discovery_prep import (
    DISCOVERY_ITEM_PROVENANCE,
    DISCOVERY_KEY_PREFIX,
    merge_discovered_native_items,
)


def native_rows_from_llm_initial_ledger_items(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Convert LLM ``initial_ledger_items`` into native discovery-shaped rows for merge."""
    out: list[dict[str, Any]] = []
    if not items:
        return out
    now = int(time.time())
    for raw in items:
        title = str(raw.get("title") or raw.get("label") or "").strip()
        summary = str(raw.get("summary") or raw.get("description") or title).strip()
        if len(title) < 4 and len(summary) < 8:
            continue
        title = title[:240]
        summary = summary[:480]
        fp = hashlib.sha256(f"{title}|{summary}".encode("utf-8")).hexdigest()[:12]
        key = f"{DISCOVERY_KEY_PREFIX}llm_startup_item:{fp}"
        sig_fp = _signal_fp(title=title, summary=summary)
        mapping_blocking = transcript_mapping_blocking_from_startup_item(raw)
        suggested = (
            str(raw.get("suggested_decision_key") or raw.get("suggested_key") or raw.get("decision_key") or "")
            .strip()
            .lower()[:64]
            or None
        )
        try:
            pri = int(raw.get("priority"))
        except (TypeError, ValueError):
            pri = 42
        pri = max(1, min(99, pri))
        block_reason = str(raw.get("block_reason") or "").strip().lower()
        if block_reason not in {"ambiguity", "contradiction", "dependency"}:
            block_reason = "contradiction" if mapping_blocking else "ambiguity"
        layer = transcript_layer_tag_from_startup_item(raw)
        impact = transcript_operational_impact_from_startup_item(raw)
        out.append(
            {
                "key": key,
                "label": f"Startup: {title}"[:240],
                "state": str(raw.get("state") or "unknown").strip().lower()[:32] or "unknown",
                "selected_value": raw.get("selected_value"),
                "alternatives": [],
                "confidence": None,
                "blocking": mapping_blocking,
                "evidence_refs": ["llm_startup:orient_baseline"],
                "user_override_state": "none",
                "layer_tag": layer,
                "operational_impact": impact,
                "provenance": DISCOVERY_ITEM_PROVENANCE,
                "verification_required": bool(raw.get("verification_required", True)),
                "scope_id": "target_scope",
                "scope_label": "Target scope",
                "scope_priority": pri,
                "in_target_scope": True,
                "scope_proof": [],
                "closure_requirement": {
                    "mapping_blocking": mapping_blocking,
                    "scope_status": "in_target",
                    "block_reason": block_reason,
                    "required_information": summary or title,
                    "minimal_user_action": "Review startup-authored work item and gather evidence as needed.",
                },
                "discovery_meta": {
                    "kind": "llm_startup_item",
                    "version": 1,
                    "signal_fp": sig_fp,
                    "last_merged_epoch": now,
                    "posture": "fresh",
                    "evidence_touch_count": 0,
                    "lifecycle_hint": "active",
                    "suggested_decision_key": suggested,
                },
            }
        )
    return out


def _signal_fp(*, title: str, summary: str) -> str:
    n = " ".join(f"{title}|{summary}".lower().split())[:500]
    return hashlib.sha256(n.encode("utf-8")).hexdigest()[:12]


def emergent_blocker_updates_from_llm_blockers(
    blockers: list[dict[str, Any]] | None,
    *,
    fallback_decision_key: str | None,
) -> list[dict[str, Any]]:
    """Map LLM ``initial_blockers`` to emergent registry ``add`` operations."""
    out: list[dict[str, Any]] = []
    if not blockers:
        return out
    for idx, raw in enumerate(blockers):
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or raw.get("label") or "").strip()[:240]
        reason = str(raw.get("reason") or raw.get("description") or title).strip()[:800]
        if len(title) < 4 or len(reason) < 8:
            continue
        kind = str(raw.get("blocker_kind") or raw.get("kind") or "").strip().lower()
        if not kind:
            kind = f"custom:startup_{idx + 1}"
        bc = str(raw.get("blocking_class") or "").strip().lower()
        # Registry allows only transcript-edit classes; unknown/invalid → least-assumptive tier (not mapping/closure).
        if bc not in {"mapping_blocking", "closure_blocking", "source_blocking", "quality_only"}:
            bc = "quality_only"
        legacy = str(raw.get("legacy_decision_key") or raw.get("decision_key") or fallback_decision_key or "").strip().lower() or None
        out.append(
            {
                "operation": "add",
                "blocker_kind": kind[:80],
                "title": title,
                "blocking_class": bc,
                "reason": reason,
                "evidence_summary": str(raw.get("evidence_summary") or "").strip()[:500] or None,
                "candidate_values": [str(x).strip() for x in list(raw.get("candidate_values") or []) if str(x).strip()][:8],
                "next_valid_actions": [
                    str(x).strip().lower()
                    for x in list(raw.get("next_valid_actions") or [])
                    if str(x).strip()
                ][:8],
                "scope_status": str(raw.get("scope_status") or "unknown").strip().lower() or "unknown",
                "legacy_decision_key": legacy,
            }
        )
    return out


def select_startup_focus_key(
    *,
    last_focus_key: str | None,
    startup: dict[str, Any] | None,
) -> str | None:
    """Continuity-first startup focus selection for pack/runtime startup paths."""
    continuity_key = str(last_focus_key or "").strip().lower() or None
    if continuity_key:
        return continuity_key
    return fallback_decision_key_for_startup_merge(
        orient_items=[],
        startup=(dict(startup) if isinstance(startup, dict) else None),
    )


def apply_llm_startup_to_ledger_and_registry(
    *,
    ledger: dict[str, Any],
    registry: dict[str, Any],
    startup: dict[str, Any] | None,
    merge_stats: dict[str, Any] | None = None,
    fallback_decision_key: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Merge LLM startup ledger rows + emergent blockers; returns (ledger, registry)."""
    coerced = coerce_startup_understanding(startup if isinstance(startup, dict) else None)
    rows = native_rows_from_llm_initial_ledger_items(
        coerced.get("initial_ledger_items") if isinstance(coerced.get("initial_ledger_items"), list) else []
    )
    led = merge_discovered_native_items(ledger, rows, merge_stats=merge_stats)
    if isinstance(led, dict):
        led["llm_startup_understanding"] = coerced
        has_content = bool(
            (coerced.get("orientation_brief") or "").strip()
            or (coerced.get("startup_rationale") or "").strip()
            or (coerced.get("orientation_notes") or "").strip()
            or coerced.get("artifact_inventory")
            or coerced.get("initial_uncertainties")
            or coerced.get("initial_dependencies")
            or coerced.get("initial_ledger_items")
            or coerced.get("initial_blockers")
            or coerced.get("initial_focus_candidates")
            or rows
        )
        if has_content:
            led["initial_ledger_source"] = "llm_orient_startup"
            led.setdefault("ledger_establishment_mode", "llm_startup_plus_discovery")

    updates = emergent_blocker_updates_from_llm_blockers(
        coerced.get("initial_blockers") if isinstance(coerced.get("initial_blockers"), list) else [],
        fallback_decision_key=fallback_decision_key,
    )
    reg = registry
    if updates:
        result = apply_proposed_emergent_blocker_updates(
            registry=registry,
            blocker_updates=updates,
            fallback_decision_key=fallback_decision_key,
        )
        reg = result.get("registry") if isinstance(result.get("registry"), dict) else registry
    return led, reg


def apply_llm_iteration_updates_to_ledger_and_registry(
    *,
    ledger: dict[str, Any],
    registry: dict[str, Any],
    iteration_payload: dict[str, Any] | None,
    merge_stats: dict[str, Any] | None = None,
    fallback_decision_key: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Phase 24: post-tool / per-iteration LLM interpretation — same shape as startup, different sidecar key."""
    coerced = coerce_startup_understanding(iteration_payload if isinstance(iteration_payload, dict) else None)
    rows = native_rows_from_llm_initial_ledger_items(
        coerced.get("initial_ledger_items") if isinstance(coerced.get("initial_ledger_items"), list) else []
    )
    led = merge_discovered_native_items(ledger, rows, merge_stats=merge_stats)
    if isinstance(led, dict):
        led["llm_iteration_understanding"] = coerced
    updates = emergent_blocker_updates_from_llm_blockers(
        coerced.get("initial_blockers") if isinstance(coerced.get("initial_blockers"), list) else [],
        fallback_decision_key=fallback_decision_key,
    )
    reg = registry
    if updates:
        result = apply_proposed_emergent_blocker_updates(
            registry=registry,
            blocker_updates=updates,
            fallback_decision_key=fallback_decision_key,
        )
        reg = result.get("registry") if isinstance(result.get("registry"), dict) else registry
    return led, reg


__all__ = [
    "apply_llm_iteration_updates_to_ledger_and_registry",
    "apply_llm_startup_to_ledger_and_registry",
    "coerce_startup_understanding",
    "emergent_blocker_updates_from_llm_blockers",
    "fallback_decision_key_for_startup_merge",
    "native_rows_from_llm_initial_ledger_items",
    "select_startup_focus_key",
    "startup_understanding_has_minimum_viable",
]
