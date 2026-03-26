"""Transcript-edit decision-ledger facade.

Organized-work truth for runtime reasoning is the shared continuity-first model, with the unified
harness decision ledger envelope remaining the compatibility read surface. This package aggregates
native persistence operations and closure helpers beside that envelope.
"""
from __future__ import annotations

from .decision_ledger_closure import (
    closure_state_from_layers,
    derive_layer_statuses,
    has_unresolved_mapping_blocking_closure,
    has_unresolved_target_scope_mapping_blocking_closure,
    is_unresolved_mapping_blocking_decision,
    is_unresolved_target_scope_mapping_blocking_decision,
    unresolved_closure_requirements,
    unresolved_mapping_blocking_requirements,
    unresolved_outside_target_scope_mapping_blocking_requirements,
    unresolved_target_scope_mapping_blocking_requirements,
)
from .decision_ledger_focus import choose_investigation_focus, has_blocking_dispute
from .decision_ledger_scope import scope_summaries_from_ledger
from .decision_ledger_state import (
    clear_resolved_after_reaudit,
    initialize_decision_ledger,
    initialize_decision_ledger_with_domain_template_seed,
    ledger_snapshot_for_payload,
    list_external_context_injections,
    mark_human_resolution_ticket_state,
    reconcile_ledger_derived_fields,
    update_ledger_from_iteration,
    update_ledger_from_orient_baseline,
    upsert_human_resolution_ticket,
    wake_seed_scaffolding_row,
)

__all__ = [
    "clear_resolved_after_reaudit",
    "initialize_decision_ledger",
    "initialize_decision_ledger_with_domain_template_seed",
    "wake_seed_scaffolding_row",
    "reconcile_ledger_derived_fields",
    "update_ledger_from_iteration",
    "update_ledger_from_orient_baseline",
    "ledger_snapshot_for_payload",
    "list_external_context_injections",
    "upsert_human_resolution_ticket",
    "mark_human_resolution_ticket_state",
    "derive_layer_statuses",
    "closure_state_from_layers",
    "unresolved_closure_requirements",
    "unresolved_mapping_blocking_requirements",
    "has_unresolved_mapping_blocking_closure",
    "unresolved_target_scope_mapping_blocking_requirements",
    "unresolved_outside_target_scope_mapping_blocking_requirements",
    "has_unresolved_target_scope_mapping_blocking_closure",
    "is_unresolved_mapping_blocking_decision",
    "is_unresolved_target_scope_mapping_blocking_decision",
    "has_blocking_dispute",
    "scope_summaries_from_ledger",
]
