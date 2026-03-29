"""Compact organized-work composition for transcript-edit runtime observability (Phase 13–18).

Counts and hints are derived from **native** + unified context for operator/model surfaces; they do not
define harness ledger semantics. Authoritative organized-work structure remains the unified envelope.

Domain-local only — not part of the generic harness decision-ledger contract.
"""
from __future__ import annotations

from typing import Any

from .transcript_edit_ledger_bootstrap_policy import transcript_edit_bootstrap_policy_snapshot
from .transcript_edit_ledger_discovery_prep import DISCOVERY_ITEM_PROVENANCE, DISCOVERY_KEY_PREFIX
from .work_board_projection import HARNESS_EMERGENT_ITEM_PREFIX

_UNRESOLVED_STATES = frozenset({"unknown", "candidate_found", "disputed", "accepted_with_risk"})


def compute_organized_work_composition(
    *,
    native_decision_ledger: dict[str, Any] | None,
    unified_work_board: dict[str, Any] | None,
) -> dict[str, Any]:
    """Bounded counts + drive hint for operator/model-facing surfaces (not full analytics)."""
    native = native_decision_ledger if isinstance(native_decision_ledger, dict) else {}
    items = native.get("items") if isinstance(native.get("items"), list) else []
    ledger_mode = str(native.get("ledger_establishment_mode") or "").strip().lower() or "discovery_native"
    initial_src = str(native.get("initial_ledger_source") or "").strip() or None
    seed_awake = 0
    seed_dormant = 0
    discovery_active = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        st = str(it.get("state") or "").strip().lower()
        if st not in _UNRESOLVED_STATES:
            continue
        prov = str(it.get("provenance") or "").strip()
        key = str(it.get("key") or "")
        if prov == DISCOVERY_ITEM_PROVENANCE or key.startswith(DISCOVERY_KEY_PREFIX):
            discovery_active += 1
        elif it.get("seed_scaffolding_dormant") is True:
            seed_dormant += 1
        else:
            seed_awake += 1

    seed_total = seed_awake + seed_dormant
    discovery_cooling = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        st = str(it.get("state") or "").strip().lower()
        if st not in _UNRESOLVED_STATES:
            continue
        prov = str(it.get("provenance") or "").strip()
        key = str(it.get("key") or "")
        if prov != DISCOVERY_ITEM_PROVENANCE and not key.startswith(DISCOVERY_KEY_PREFIX):
            continue
        dm = it.get("discovery_meta") if isinstance(it.get("discovery_meta"), dict) else {}
        if str(dm.get("lifecycle_hint") or "").strip().lower() == "cooling":
            discovery_cooling += 1

    emergent = 0
    if isinstance(unified_work_board, dict):
        for row in list(unified_work_board.get("items") or []):
            if not isinstance(row, dict):
                continue
            iid = str(row.get("item_id") or "").strip()
            if not iid.startswith(HARNESS_EMERGENT_ITEM_PREFIX):
                continue
            bst = str(row.get("state") or "").strip().lower()
            if bst in {"resolved", "superseded"}:
                continue
            emergent += 1

    total_native = seed_total + discovery_active
    if total_native == 0 and emergent == 0:
        drive = "idle"
    elif total_native == 0:
        drive = "emergent_led"
    elif discovery_active > 0 and seed_awake == 0:
        drive = "discovery_led"
    elif seed_awake > 0 and discovery_active == 0:
        drive = "seed_scaffolding_led"
    elif discovery_active > seed_awake:
        drive = "discovery_led"
    elif seed_awake > discovery_active:
        drive = "seed_scaffolding_led"
    else:
        drive = "mixed"

    if discovery_active > 0 and seed_dormant > 0 and seed_awake == 0:
        formation = "discovery_primary_lazy_seed_background"
    elif discovery_active > 0 and seed_awake > 0:
        formation = "discovery_and_awake_seed"
    elif discovery_active > 0:
        formation = "discovery_primary"
    elif seed_awake > 0 and seed_dormant > 0:
        formation = "awake_seed_with_dormant_scaffolding"
    elif seed_dormant > 0 and seed_awake == 0:
        formation = "dormant_seed_only_unresolved"
    elif seed_awake > 0:
        formation = "seed_scaffolding_primary"
    else:
        formation = "neutral"

    discovery_led_startup_surface = bool(discovery_active > 0 and seed_awake == 0)
    if discovery_led_startup_surface:
        startup_posture = "discovery_first_surface"
    elif seed_awake > 0 and discovery_active == 0:
        startup_posture = "awake_seed_surface"
    elif seed_dormant > 0 and seed_awake == 0 and discovery_active == 0:
        startup_posture = "dormant_seed_only_unresolved"
    else:
        startup_posture = "mixed"

    bp = transcript_edit_bootstrap_policy_snapshot()
    domain_template_rows_awake = bool(seed_awake > 0)
    return {
        "schema_version": "organized_work_composition.v5",
        "seed_materialization_mode": "on_demand",
        "ledger_establishment_mode": ledger_mode,
        "initial_ledger_source": initial_src,
        "bootstrap_policy": bp,
        "domain_template_rows_awake": domain_template_rows_awake,
        "unresolved_seed_active_count": int(seed_total),
        "unresolved_seed_scaffolding_awake_count": int(seed_awake),
        "unresolved_seed_scaffolding_dormant_count": int(seed_dormant),
        "unresolved_discovery_active_count": int(discovery_active),
        "unresolved_discovery_cooling_count": int(discovery_cooling),
        "unresolved_emergent_harness_count": int(emergent),
        "work_drive_hint": drive,
        "work_formation_hint": formation,
        "discovery_led_startup_surface": discovery_led_startup_surface,
        "startup_active_work_posture": startup_posture,
    }
