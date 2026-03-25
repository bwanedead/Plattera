from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.controller.controller_proposals import _propose_next_step
from backend.agents.controller.prompting import build_developer_message


class _FakeLLM:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self._responses = list(responses)

    def propose_next_step(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        content = self._responses.pop(0) if self._responses else {}
        return content


def test_build_developer_message_emits_prompt_event_metadata_and_source_blocks() -> None:
    calls: list[dict[str, object]] = []

    message = build_developer_message(
        run_link_id="run-123",
        model="gpt-5.2",
        mission_objective="map deed",
        identity_trace_cb=calls.append,
    )

    assert message.startswith("[IDENTITY constitution=v2]")
    assert len(calls) == 1
    payload = calls[0]
    assert payload["surface"] == "deed_controller"
    assert payload["domain"] == "deed_to_ir"
    assert payload["prompt_event_metadata"]["surface"] == "deed_controller"
    assert payload["prompt_event_metadata"]["domain"] == "deed_to_ir"
    owners = {row["owner"] for row in payload["source_blocks"]}
    assert "shared_harness" in owners
    assert "deed_to_ir" in owners


def test_controller_proposal_emits_prompt_event_after_llm_call() -> None:
    calls: list[dict[str, object]] = []
    llm = _FakeLLM(
        responses=[
            {
                "text": "{\"action_type\":\"open_artifact\",\"idempotency_key\":\"k1\",\"args\":{\"artifact_ref\":\"ref\"},\"why\":\"inspect\"}",
                "structured_data": {
                    "action_type": "open_artifact",
                    "idempotency_key": "k1",
                    "args": {"artifact_ref": "ref"},
                    "why": "inspect",
                },
            }
        ]
    )

    proposal = _propose_next_step(
        llm_client=llm,  # type: ignore[arg-type]
        model="gpt-5.2",
        observation={"tool_menu": [{"name": "open_artifact", "description": "open", "parameters_schema": {}}]},
        transcript=[],
        run_link_id="run-123",
        mission_objective="map deed",
        identity_trace_cb=calls.append,
    )

    assert proposal is not None
    assert len(calls) == 2
    assert "prompt_event" not in calls[0]
    assert "prompt_event" in calls[1]
    prompt_event = calls[1]["prompt_event"]
    assert isinstance(prompt_event, dict)
    assert prompt_event["outcome_kind"] == "proposal_valid"
    assert prompt_event["model_output_payload"]["structured_data"]["action_type"] == "open_artifact"
