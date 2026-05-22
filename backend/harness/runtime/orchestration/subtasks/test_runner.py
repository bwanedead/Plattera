from __future__ import annotations

import json

from harness.execution.contracts import ExecutionStepRequest
from harness.runtime.orchestration.subtasks.contracts import (
    DelegateSubtaskRequest,
    HydratedSubtaskContext,
    SubtaskProfile,
)
from harness.runtime.orchestration.subtasks.registry import DEFAULT_SUBTASK_REGISTRY, SubtaskProfileRegistry
from harness.runtime.orchestration.subtasks.prompting import build_child_prompt
from harness.runtime.orchestration.subtasks.runner import (
    normalize_child_output,
    run_delegate_subtask,
)


def _request() -> DelegateSubtaskRequest:
    return DelegateSubtaskRequest(
        profile="harness.observation",
        task="Read only the supplied local evidence.",
        context_refs=("artifact:sample",),
        isolation={"omit_parent_graph": True},
        output_contract={"kind": "observation"},
    )


def _parent_request() -> ExecutionStepRequest:
    return ExecutionStepRequest(
        session_id="s",
        action_id="delegate_subtask",
        inputs={},
        idempotency_key="req:iter:1:dispatch:delegate_subtask",
        run_id="r",
    )


def test_run_delegate_subtask_uses_stubbed_model_and_image_side_channel() -> None:
    profile = DEFAULT_SUBTASK_REGISTRY.require("harness.observation")
    prompts: list[str] = []
    image_counts: list[int] = []

    def hydrate_handler(request: ExecutionStepRequest) -> dict:
        assert request.action_id == "hydrate_artifact_refs"
        return {
            "executed": True,
            "outputs": {
                "results": [
                    {
                        "ref_id": "artifact:sample",
                        "kind": "artifact",
                        "text": "Visible local value is A.",
                        "image_b64": "SHOULD_NOT_APPEAR",
                    }
                ],
                "errors": [],
            },
            "image_evidence": [
                {"ref_id": "artifact:sample", "b64": "raw-pixels", "media_type": "image/png"}
            ],
        }

    def model_caller(prompt: str, model_name: str, *, call_options):
        prompts.append(prompt)
        image_counts.append(len(call_options.image_attachments))
        assert model_name == "model-a"
        assert call_options.output_mode == "json_object"
        return json.dumps(
            {
                "status": "completed",
                "result": {
                    "reading": "A",
                    "ambiguity": "",
                    "observations": ["Only supplied input was used."],
                    "limits": [],
                    "confidence": 0.99,
                },
            }
        )

    output = run_delegate_subtask(
        subtask_id="local_subtask",
        request=_request(),
        profile=profile,
        model_caller=model_caller,
        default_model_name="model-a",
        hydration_handler=hydrate_handler,
        parent_request=_parent_request(),
    )

    assert output["subtask_id"] == "local_subtask"
    assert output["status"] == "completed"
    assert output["result"]["reading"] == "A"
    assert "confidence" not in output["result"]
    assert image_counts == [1]
    assert "SHOULD_NOT_APPEAR" not in prompts[0]
    assert "raw-pixels" not in prompts[0]
    assert "parent resolution graph" not in prompts[0]
    assert "broad doctrine" not in prompts[0]


def test_normalize_child_output_accepts_allowed_statuses() -> None:
    profile = DEFAULT_SUBTASK_REGISTRY.require("harness.observation")
    for status in ("completed", "ambiguous", "insufficient_input", "failed"):
        output = normalize_child_output(
            json.dumps({"status": status, "result": {"observations": ["x"]}}),
            subtask_id="s1",
            request=_request(),
            profile=profile,
        )
        assert output["status"] == status


def test_malformed_child_output_returns_bounded_failed_result() -> None:
    profile = DEFAULT_SUBTASK_REGISTRY.require("harness.observation")

    output = normalize_child_output(
        "not-json",
        subtask_id="s1",
        request=_request(),
        profile=profile,
    )

    assert output["status"] == "failed"
    assert output["errors"][0]["reason_code"] == "subtask_output_malformed"


def test_text_only_profile_does_not_receive_image_side_channel() -> None:
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
    profile = registry.require("test.text_observation")
    seen_image_counts: list[int] = []

    def hydrate_handler(request: ExecutionStepRequest) -> dict:
        del request
        return {
            "executed": True,
            "outputs": {"results": [{"ref_id": "artifact:sample", "text": "hello"}], "errors": []},
            "image_evidence": [
                {"ref_id": "artifact:sample", "b64": "raw-pixels", "media_type": "image/png"}
            ],
        }

    def model_caller(prompt: str, model_name: str, *, call_options):
        del prompt, model_name
        seen_image_counts.append(len(call_options.image_attachments))
        return json.dumps({"status": "completed", "result": {"observations": ["text only"]}})

    output = run_delegate_subtask(
        subtask_id="text_subtask",
        request=DelegateSubtaskRequest(
            profile="test.text_observation",
            task="Inspect text only.",
            context_refs=("artifact:sample",),
        ),
        profile=profile,
        model_caller=model_caller,
        default_model_name="model-a",
        hydration_handler=hydrate_handler,
        parent_request=_parent_request(),
    )

    assert output["status"] == "completed"
    assert seen_image_counts == [0]


def test_child_prompt_uses_profile_result_schema() -> None:
    profile = SubtaskProfile(
        profile_id="domain.observation",
        owner="domain",
        description="custom",
        allowed_ref_kinds=("artifact",),
        prompt_preamble="observe",
        result_schema={"status": ["completed"], "result": {"domain_notes": ["string"]}},
    )

    prompt = build_child_prompt(
        profile=profile,
        request=DelegateSubtaskRequest(
            profile="domain.observation",
            task="Inspect supplied artifact.",
            context_refs=("artifact:sample",),
        ),
        context=HydratedSubtaskContext(input_refs=("artifact:sample",)),
    )

    assert "domain_notes" in prompt


def test_custom_profile_preserves_fields_end_to_end() -> None:
    profile = SubtaskProfile(
        profile_id="domain.observation",
        owner="domain",
        description="custom",
        allowed_ref_kinds=("artifact",),
        prompt_preamble="observe",
        result_schema={
            "status": ["completed", "ambiguous", "insufficient_input", "failed"],
            "result": {"domain_notes": ["string"]},
        },
    )
    SubtaskProfileRegistry().register(profile)

    output = normalize_child_output(
        json.dumps({"status": "completed", "result": {"domain_notes": ["visible mark"]}}),
        subtask_id="s1",
        request=DelegateSubtaskRequest(
            profile="domain.observation",
            task="Inspect supplied artifact.",
            context_refs=("artifact:sample",),
        ),
        profile=profile,
    )

    assert output["result"]["domain_notes"] == ["visible mark"]
    assert "reading" not in output["result"]
