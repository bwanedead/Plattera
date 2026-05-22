from __future__ import annotations

import json

from harness.execution.contracts import ExecutionStepRequest
from harness.runtime.orchestration.subtasks.contracts import DELEGATE_SUBTASK_ACTION_TYPE
from harness.runtime.orchestration.subtasks.handler import make_delegate_subtask_handler


def test_handler_uses_action_alias_as_subtask_id_without_artifact_or_state_mutation() -> None:
    def model_caller(prompt: str, model_name: str, *, call_options):
        del prompt, model_name, call_options
        return json.dumps({"status": "ambiguous", "result": {"ambiguity": "input was limited"}})

    handler = make_delegate_subtask_handler(
        model_caller=model_caller,
        model_name="model-a",
        hydration_handler=None,
    )
    result = handler(
        ExecutionStepRequest(
            session_id="s",
            action_id=DELEGATE_SUBTASK_ACTION_TYPE,
            inputs={
                "_subtask_alias": "local_subtask",
                "profile": "harness.observation",
                "task": "Inspect the supplied input.",
                "context_refs": ["artifact:sample"],
            },
            idempotency_key="req:iter:1:dispatch:delegate_subtask",
            run_id="r",
        )
    )

    assert result.executed is True
    assert result.outputs["subtask_id"] == "local_subtask"
    assert result.outputs["status"] == "ambiguous"
    assert result.artifact_refs == ()
    assert result.image_evidence == ()


def test_handler_validation_refusal_is_retryable() -> None:
    handler = make_delegate_subtask_handler(
        model_caller=lambda *args, **kwargs: "{}",
        model_name="model-a",
        hydration_handler=None,
    )

    result = handler(
        ExecutionStepRequest(
            session_id="s",
            action_id=DELEGATE_SUBTASK_ACTION_TYPE,
            inputs={"profile": "harness.observation", "task": "missing refs"},
            idempotency_key="ik",
            run_id="r",
        )
    )

    assert result.executed is False
    assert result.refusal is not None
    assert result.refusal.retryable is True
