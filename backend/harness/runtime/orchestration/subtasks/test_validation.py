from __future__ import annotations

import pytest

from harness.runtime.orchestration.subtasks.contracts import SubtaskProfile
from harness.runtime.orchestration.subtasks.errors import SubtaskValidationError
from harness.runtime.orchestration.subtasks.registry import (
    DEFAULT_SUBTASK_REGISTRY,
    build_composed_subtask_registry,
    SubtaskProfileRegistry,
)
from harness.runtime.orchestration.subtasks.validation import validate_delegate_subtask_inputs


def _valid_inputs() -> dict:
    return {
        "profile": "harness.observation",
        "task": "Inspect the supplied input and answer the local question.",
        "context_refs": ["artifact:sample"],
        "isolation": {"omit_parent_graph": True, "omit_peer_candidates": "false"},
        "output_contract": {"kind": "observation"},
    }


def test_default_registry_resolves_generic_profiles() -> None:
    assert DEFAULT_SUBTASK_REGISTRY.get("harness.observation") is not None
    assert DEFAULT_SUBTASK_REGISTRY.get("harness.test_observation") is None


def test_validate_delegate_subtask_accepts_valid_inputs() -> None:
    request = validate_delegate_subtask_inputs(_valid_inputs())

    assert request.profile == "harness.observation"
    assert request.context_refs == ("artifact:sample",)
    assert request.isolation == {"omit_parent_graph": True, "omit_peer_candidates": False}


def test_validate_delegate_subtask_rejects_unknown_profile_repairably() -> None:
    payload = _valid_inputs()
    payload["profile"] = "harness.missing"

    with pytest.raises(SubtaskValidationError) as excinfo:
        validate_delegate_subtask_inputs(payload)

    assert excinfo.value.reason_code == "unknown_subtask_profile"


def test_validate_delegate_subtask_enforces_profile_ref_kind_constraints() -> None:
    registry = SubtaskProfileRegistry()
    registry.register(
        SubtaskProfile(
            profile_id="test.text_observation",
            owner="test",
            description="text only",
            allowed_ref_kinds=("artifact", "text"),
            prompt_preamble="observe",
        )
    )
    payload = _valid_inputs()
    payload["profile"] = "test.text_observation"
    payload["context_refs"] = ["image:derived:sample"]

    with pytest.raises(SubtaskValidationError) as excinfo:
        validate_delegate_subtask_inputs(payload, registry=registry)

    assert excinfo.value.reason_code == "context_ref_kind_disallowed"


def test_validate_delegate_subtask_rejects_over_caps() -> None:
    registry = SubtaskProfileRegistry()
    registry.register(
        SubtaskProfile(
            profile_id="harness.tiny",
            owner="harness",
            description="tiny",
            allowed_ref_kinds=("artifact",),
            prompt_preamble="observe",
            max_context_refs=1,
            max_task_chars=8,
        )
    )
    payload = _valid_inputs()
    payload["profile"] = "harness.tiny"
    payload["task"] = "x" * 9

    with pytest.raises(SubtaskValidationError) as excinfo:
        validate_delegate_subtask_inputs(payload, registry=registry)

    assert excinfo.value.reason_code == "task_too_long"


def test_validate_delegate_subtask_rejects_unknown_isolation_flags() -> None:
    payload = _valid_inputs()
    payload["isolation"] = {"omit_parent_graph": True, "decide_truth": True}

    with pytest.raises(SubtaskValidationError) as excinfo:
        validate_delegate_subtask_inputs(payload)

    assert excinfo.value.reason_code == "isolation_unknown_flag"


def test_validate_delegate_subtask_rejects_confidence_output_contract() -> None:
    payload = _valid_inputs()
    payload["output_contract"] = {"kind": "observation", "confidence": "number"}

    with pytest.raises(SubtaskValidationError) as excinfo:
        validate_delegate_subtask_inputs(payload)

    assert excinfo.value.reason_code == "output_contract_confidence_disallowed"


def test_composed_registry_accepts_domain_profile_specs() -> None:
    registry = build_composed_subtask_registry(
        surface_payloads={
            "domain": {
                "subtask_profiles": [
                    {
                        "profile_id": "domain.visual_observation",
                        "owner": "domain",
                        "description": "opaque domain profile",
                        "allowed_ref_kinds": ["image"],
                        "prompt_preamble": "Use only supplied image refs.",
                        "result_schema": {"status": ["completed"], "result": {"observations": ["string"]}},
                    }
                ]
            }
        }
    )

    assert registry.get("harness.observation") is not None
    assert registry.get("domain.visual_observation") is not None
