from __future__ import annotations

import json

import pytest

from harness.runtime.orchestration.subtasks.contracts import DelegateSubtaskRequest, HydratedSubtaskContext, SubtaskProfile
from harness.runtime.orchestration.subtasks.projection import project_subtask_output
from harness.runtime.orchestration.subtasks.prompting import build_child_prompt
from harness.runtime.orchestration.subtasks.registry import DEFAULT_SUBTASK_REGISTRY, SubtaskProfileRegistry
from harness.runtime.orchestration.subtasks.result_schema import (
    SubtaskProfileSchemaError,
    SubtaskResultSchemaError,
    normalize_result_payload,
    validate_profile_result_schema,
)
from harness.runtime.orchestration.subtasks.runner import normalize_child_output


def _domain_profile() -> SubtaskProfile:
    registry = SubtaskProfileRegistry()
    registry.register(
        SubtaskProfile(
            profile_id="domain.custom_observation",
            owner="domain",
            description="custom result fields",
            allowed_ref_kinds=("artifact",),
            prompt_preamble="observe",
            result_schema={
                "status": ["completed", "ambiguous", "insufficient_input", "failed"],
                "result": {
                    "domain_notes": ["string"],
                    "source_mark": "string|null",
                },
            },
        )
    )
    return registry.require("domain.custom_observation")


def test_generic_observation_profile_unchanged() -> None:
    profile = DEFAULT_SUBTASK_REGISTRY.require("harness.observation")
    result = normalize_result_payload(
        {
            "reading": "A",
            "ambiguity": "unclear edge",
            "observations": ["line one", "line two"],
            "limits": ["crop only"],
        },
        profile=profile,
    )

    assert result == {
        "reading": "A",
        "ambiguity": "unclear edge",
        "observations": ["line one", "line two"],
        "limits": ["crop only"],
    }


def test_custom_profile_preserves_fields() -> None:
    profile = _domain_profile()
    result = normalize_result_payload(
        {
            "domain_notes": ["mark visible", "edge fuzzy"],
            "source_mark": "N. 2° 00' W.",
            "confidence": 0.9,
            "b64": "SHOULD_DROP",
        },
        profile=profile,
    )

    assert result == {
        "domain_notes": ["mark visible", "edge fuzzy"],
        "source_mark": "N. 2° 00' W.",
    }
    assert "confidence" not in result
    assert "b64" not in result


def test_custom_fields_project_into_parent_turn() -> None:
    profile = _domain_profile()
    normalized = normalize_child_output(
        json.dumps(
            {
                "status": "completed",
                "result": {
                    "domain_notes": ["visible mark"],
                    "source_mark": "A",
                },
            }
        ),
        subtask_id="custom_subtask",
        request=DelegateSubtaskRequest(
            profile="domain.custom_observation",
            task="Inspect source mark.",
            context_refs=("artifact:sample",),
        ),
        profile=profile,
    )
    projected = project_subtask_output(normalized)

    assert projected is not None
    assert projected["result"]["domain_notes"] == ["visible mark"]
    assert projected["result"]["source_mark"] == "A"


def test_prompt_schema_matches_normalization_schema() -> None:
    profile = _domain_profile()
    prompt = build_child_prompt(
        profile=profile,
        request=DelegateSubtaskRequest(
            profile=profile.profile_id,
            task="Inspect source mark.",
            context_refs=("artifact:sample",),
        ),
        context=HydratedSubtaskContext(input_refs=("artifact:sample",)),
    )

    assert "domain_notes" in prompt
    assert "source_mark" in prompt

    result = normalize_result_payload(
        {"domain_notes": ["x"], "source_mark": "y"},
        profile=profile,
    )
    assert set(result.keys()) == {"domain_notes", "source_mark"}


def test_unsupported_profile_schema_rejected_at_registration() -> None:
    registry = SubtaskProfileRegistry()
    with pytest.raises(ValueError, match="unsupported type"):
        registry.register(
            SubtaskProfile(
                profile_id="bad.schema",
                owner="test",
                description="bad",
                allowed_ref_kinds=("artifact",),
                prompt_preamble="observe",
                result_schema={
                    "status": ["completed"],
                    "result": {"score": 123},
                },
            )
        )


def test_profile_schema_rejects_confidence_fields() -> None:
    with pytest.raises(SubtaskProfileSchemaError) as excinfo:
        validate_profile_result_schema(
            {
                "status": ["completed"],
                "result": {"confidence": "number"},
            }
        )

    assert excinfo.value.reason_code == "result_schema_confidence_disallowed"


def test_profile_schema_rejects_binary_payload_fields() -> None:
    with pytest.raises(SubtaskProfileSchemaError) as excinfo:
        validate_profile_result_schema(
            {
                "status": ["completed"],
                "result": {"image_b64": "string"},
            }
        )

    assert excinfo.value.reason_code == "result_schema_binary_field_disallowed"


def test_oversized_output_is_repairably_rejected() -> None:
    registry = SubtaskProfileRegistry()
    registry.register(
        SubtaskProfile(
            profile_id="tiny.result",
            owner="test",
            description="tiny",
            allowed_ref_kinds=("artifact",),
            prompt_preamble="observe",
            result_schema={
                "status": ["completed"],
                "result": {"notes": ["string"]},
            },
            max_result_chars=40,
        )
    )
    tiny_profile = registry.require("tiny.result")

    with pytest.raises(SubtaskResultSchemaError) as excinfo:
        normalize_result_payload(
            {"notes": ["x" * 200, "y" * 200, "z" * 200]},
            profile=tiny_profile,
        )

    assert excinfo.value.reason_code == "subtask_result_too_large"


def test_invalid_child_field_type_is_repairably_rejected() -> None:
    profile = _domain_profile()

    output = normalize_child_output(
        json.dumps({"status": "completed", "result": {"domain_notes": "not-a-list"}}),
        subtask_id="custom_subtask",
        request=DelegateSubtaskRequest(
            profile="domain.custom_observation",
            task="Inspect source mark.",
            context_refs=("artifact:sample",),
        ),
        profile=profile,
    )

    assert output["status"] == "failed"
    assert output["errors"][0]["reason_code"] == "subtask_result_field_invalid"


def test_projection_does_not_leak_raw_payloads() -> None:
    profile = _domain_profile()
    projected = project_subtask_output(
        {
            "action_type": "delegate_subtask",
            "subtask_id": "s1",
            "profile": profile.profile_id,
            "status": "completed",
            "input_refs": ["artifact:sample"],
            "result_schema": dict(profile.result_schema),
            "result": {
                "domain_notes": ["ok"],
                "source_mark": "A",
                "image_b64": "SHOULD_NOT_RENDER",
            },
        }
    )

    assert projected is not None
    text = json.dumps(projected)
    assert "SHOULD_NOT_RENDER" not in text
    assert "b64" not in text.lower()
