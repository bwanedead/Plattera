"""Transcript-edit domain: optional checklist-shaped orient seeds (legacy compatibility).

The generic agent kernel orientation contract does not include checklist ontology; this adapter
maps LLM ``items`` rows into native decision-ledger checklist keys when present.
"""
from __future__ import annotations

from typing import Any

from agent_kernel.orientation.contract import collect_orientation_startup_input
from agent_kernel.orientation.startup_document import (
    coerce_startup_understanding,
    startup_understanding_has_minimum_viable,
)

from agent_kernel.tooling_artifacts import _read_str

_CHECKLIST_KEYS = frozenset(
    {
        "township",
        "range",
        "section",
        "tie_distance",
        "tie_bearing",
        "acreage",
        "closure_or_pob",
    }
)


def _coerce_string_list(raw: Any, *, limit: int) -> list[str]:
    if not isinstance(raw, list):
        return []
    values: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if not text or text in values:
            continue
        values.append(text[:200])
        if len(values) >= limit:
            break
    return values


def coerce_transcript_edit_checklist_seed_items(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Coerce optional ``items`` rows into bounded checklist ledger seed rows (transcript-edit domain)."""
    raw_items = raw.get("items")
    if raw_items is None:
        raw_items = []
    if not isinstance(raw_items, list):
        return []
    state_values = {"unknown", "candidate_found", "verified", "disputed", "accepted_with_risk"}
    confidence_values = {"low", "medium", "high"}
    layer_values = {
        "layer1_canonical_recovery",
        "layer2_canonical_sanity",
        "layer3_dependency",
        "layer4_transcript_quality_optional",
    }
    impact_values = {"mapping_blocking", "transcript_quality_only", "unknown"}
    block_reason_values = {"ambiguity", "contradiction", "dependency"}
    self_retrievable_values = {"yes", "conditional"}
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in raw_items:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key") or "").strip().lower()
        if key not in _CHECKLIST_KEYS or key in seen:
            continue
        seen.add(key)
        state = str(entry.get("state") or "unknown").strip().lower()
        if state not in state_values:
            state = "unknown"
        confidence = str(entry.get("confidence") or "medium").strip().lower()
        if confidence not in confidence_values:
            confidence = "medium"
        layer_tag = str(entry.get("layer_tag") or "layer1_canonical_recovery").strip().lower()
        if layer_tag not in layer_values:
            layer_tag = "layer1_canonical_recovery"
        operational_impact = str(entry.get("operational_impact") or "unknown").strip().lower()
        if operational_impact not in impact_values:
            operational_impact = "unknown"
        block_reason = str(entry.get("block_reason") or "ambiguity").strip().lower()
        if block_reason not in block_reason_values:
            block_reason = "ambiguity"
        self_retrievable = str(entry.get("self_retrievable") or "conditional").strip().lower()
        if self_retrievable not in self_retrievable_values:
            self_retrievable = "conditional"
        alternatives = _coerce_string_list(entry.get("alternatives"), limit=8)
        resolution_options = _coerce_string_list(entry.get("resolution_options"), limit=8)
        evidence_refs = _coerce_string_list(entry.get("evidence_refs"), limit=12)
        selected_value = _read_str(entry.get("selected_value"))
        retrieval_blocker = _read_str(entry.get("retrieval_blocker"))
        span_seed = entry.get("span_seed") if isinstance(entry.get("span_seed"), dict) else None
        items.append(
            {
                "key": key,
                "state": state,
                "selected_value": selected_value,
                "alternatives": alternatives,
                "confidence": confidence,
                "layer_tag": layer_tag,
                "operational_impact": operational_impact,
                "block_reason": block_reason,
                "required_information": str(entry.get("required_information") or "").strip(),
                "minimal_user_action": str(entry.get("minimal_user_action") or "").strip(),
                "resolution_options": resolution_options,
                "self_retrievable": self_retrievable,
                "retrieval_attempted": bool(entry.get("retrieval_attempted")),
                "retrieval_blocker": retrieval_blocker,
                "verification_required": bool(entry.get("verification_required")),
                "attempt_summary": str(entry.get("attempt_summary") or "").strip(),
                "evidence_refs": evidence_refs,
                "provenance": str(entry.get("provenance") or "orient_llm").strip() or "orient_llm",
                "span_seed": span_seed,
            }
        )
    return items


def coerce_transcript_edit_orient_payload(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate generic startup + optional transcript-edit checklist seeds (same success rule as Phase 26)."""
    checklist = coerce_transcript_edit_checklist_seed_items(raw)
    startup_input = collect_orientation_startup_input(raw)
    startup_coerced = coerce_startup_understanding(startup_input)
    if not startup_understanding_has_minimum_viable(startup_coerced) and not checklist:
        raise ValueError("tx_orient_baseline_no_startup_signal")
    return {"startup_understanding": startup_coerced, "checklist_seed_items": checklist}
