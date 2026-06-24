"""Tests for domain work-graph policy helpers."""

from __future__ import annotations

from domains.work_graph_policy import (
    DomainWorkGraphPolicy,
    claim_inventory_pressure_enabled,
    work_graph_policy_to_json,
)


def test_default_policy_disables_claim_inventory_pressure() -> None:
    assert claim_inventory_pressure_enabled({}) is False
    assert claim_inventory_pressure_enabled({"domain_work_graph_policy": {}}) is False


def test_enabled_policy_surfaces_pressure() -> None:
    ctx = {
        "domain_work_graph_policy": work_graph_policy_to_json(
            DomainWorkGraphPolicy(claim_inventory_pressure_enabled=True)
        )
    }
    assert claim_inventory_pressure_enabled(ctx) is True


def test_deed_to_ir_manifest_disables_claim_inventory_pressure() -> None:
    from domains.mapping.deed_to_ir import build_deed_to_ir_manifest

    assert build_deed_to_ir_manifest().work_graph_policy.claim_inventory_pressure_enabled is False


def test_transcript_edit_manifest_enables_claim_inventory_pressure() -> None:
    from domains.mapping.transcript_edit.manifest import build_transcript_edit_manifest

    assert build_transcript_edit_manifest().work_graph_policy.claim_inventory_pressure_enabled is True
