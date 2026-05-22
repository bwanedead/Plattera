"""Registry discovery tests for nested ``subtask_profiles`` payloads."""

from __future__ import annotations

import pytest

from harness.runtime.orchestration.subtasks.registry import (
    SubtaskProfileRegistry,
    build_composed_subtask_registry,
    profile_from_mapping,
)


def _valid_profile_spec(*, profile_id: str = "domain.sample") -> dict:
    return {
        "profile_id": profile_id,
        "owner": "domain",
        "description": "sample profile",
        "allowed_ref_kinds": ["artifact"],
        "prompt_preamble": "observe",
    }


def test_flat_surface_payload_registers_profile() -> None:
    registry = build_composed_subtask_registry(
        surface_payloads={"domain": {"subtask_profiles": [_valid_profile_spec()]}},
    )
    assert registry.get("domain.sample") is not None


def test_nested_mapping_surface_payload_registers_profile() -> None:
    payload = {"subtask_profiles": [_valid_profile_spec(profile_id="domain.nested")]}
    registry = build_composed_subtask_registry(
        surface_payloads={"domain": {"domain": payload}},
    )
    assert registry.get("domain.nested") is not None


def test_nested_list_surface_payload_registers_profile() -> None:
    payload = {"subtask_profiles": [_valid_profile_spec(profile_id="domain.listed")]}
    registry = build_composed_subtask_registry(
        surface_payloads={"domain": {"payloads": [payload]}},
    )
    assert registry.get("domain.listed") is not None


def test_opaque_run_context_registers_profile() -> None:
    registry = build_composed_subtask_registry(
        opaque_run_context={"subtask_profiles": [_valid_profile_spec(profile_id="ctx.profile")]},
    )
    assert registry.get("ctx.profile") is not None


def test_excessive_nesting_does_not_crash() -> None:
    node: dict = {"subtask_profiles": [_valid_profile_spec(profile_id="deep.profile")]}
    for _ in range(20):
        node = {"nested": node}
    registry = build_composed_subtask_registry(surface_payloads={"domain": node})
    assert registry.get("deep.profile") is None
    assert registry.get("harness.observation") is not None


def test_invalid_profile_schema_still_fails_validation() -> None:
    registry = SubtaskProfileRegistry()
    with pytest.raises(ValueError, match="result_schema"):
        registry.register(
            profile_from_mapping(
                {
                    "profile_id": "bad.schema",
                    "owner": "test",
                    "description": "invalid",
                    "allowed_ref_kinds": ["artifact"],
                    "prompt_preamble": "observe",
                    "result_schema": {"status": ["completed"], "result": {"field": 123}},
                }
            )
        )
