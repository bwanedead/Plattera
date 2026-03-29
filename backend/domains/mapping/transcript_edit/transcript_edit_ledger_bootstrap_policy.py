"""Transcript-edit **domain** ledger bootstrap / template policy seam (Phase 16–17).

**Not** the harness decision-ledger contract. Domains may attach optional template rows
(checklist seed, ordering hints) while the default organized-work posture remains
discovery-first and harness-generic.

**Phase 17:** Default startup is **discovery-native** (no pre-authored checklist items).
Optional full checklist template remains available via ``initialize_decision_ledger_with_domain_template_seed``.

Future domains can mirror this pattern: explicit policy id + optional templates,
without encoding domain ontology into ``backend/harness/decision_ledger``.
"""
from __future__ import annotations

from typing import Any

from .transcript_edit_default_checklist_seed import DEFAULT_DECISION_SLOT_KEYS

# Default runtime posture for transcript-edit organized work (not a harness enum).
DEFAULT_ORGANIZED_WORK_MODE = "discovery_first"

# When True, ``initialize_decision_ledger`` may pre-install the default checklist template (legacy/tests).
# Phase 17 default: False — use ``initialize_decision_ledger_with_domain_template_seed`` explicitly.
DEFAULT_TEMPLATE_BOOTSTRAP_AT_INIT = False

# Whether this domain may supply optional template/seed rows (always True here — capability preserved).
DOMAIN_TEMPLATE_CAPABILITY_OPTIONAL = True

# Identifies the default checklist seed module as *one* domain bootstrap policy, not harness ontology.
TRANSCRIPT_EDIT_SEED_TEMPLATE_POLICY_ID = "transcript_edit.default_checklist_seed.v1"


def effective_ledger_establishment_mode(ledger: dict[str, Any] | None) -> str:
    """``discovery_native`` vs ``template_seed`` — used by native reshape (not harness)."""
    if not isinstance(ledger, dict):
        return "discovery_native"
    raw = str(ledger.get("ledger_establishment_mode") or "").strip().lower()
    if raw in ("discovery_native", "template_seed"):
        return raw
    items = ledger.get("items") if isinstance(ledger.get("items"), list) else []
    keys = {str(i.get("key") or "").strip() for i in items if isinstance(i, dict) and str(i.get("key") or "").strip()}
    seed_keys = set(DEFAULT_DECISION_SLOT_KEYS)
    # Legacy persisted sessions: full default checklist with no explicit mode.
    if keys and keys <= seed_keys and len(keys) == len(seed_keys):
        return "template_seed"
    return "discovery_native"


def transcript_edit_bootstrap_policy_snapshot() -> dict[str, Any]:
    """Compact, inspectable policy record for composition / logs (domain-local)."""
    return {
        "schema_version": "transcript_edit_bootstrap_policy.v2",
        "default_organized_work_mode": DEFAULT_ORGANIZED_WORK_MODE,
        "default_template_bootstrap_at_init": DEFAULT_TEMPLATE_BOOTSTRAP_AT_INIT,
        "domain_template_capability": "optional",
        "domain_template_policy_id": TRANSCRIPT_EDIT_SEED_TEMPLATE_POLICY_ID,
        "harness_ontology": False,
    }
