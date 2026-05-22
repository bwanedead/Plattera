from __future__ import annotations

from harness.audit.human_timeline import render_timeline
from harness.runtime.orchestration.subtasks.contracts import DELEGATE_SUBTASK_ACTION_TYPE


def test_timeline_renders_delegate_subtask_mechanics_without_raw_media() -> None:
    body = render_timeline(
        [
            {
                "turn_index": 2,
                "parse_ok": True,
                "tool_request": {
                    "actions": [
                        {
                            "alias": "local_subtask",
                            "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
                            "action_inputs": {
                                "profile": "harness.observation",
                                "task": "Inspect the supplied input and answer the local question.",
                                "context_refs": ["artifact:sample"],
                                "isolation": {"omit_parent_graph": True},
                            },
                        }
                    ],
                    "rationale": "run isolated observation",
                },
                "recent_action_sequence_result": {
                    "sequence_id": "seq-2",
                    "source_turn_index": 2,
                    "items": [
                        {
                            "alias": "local_subtask",
                            "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
                            "execution_state": "executed",
                            "delegate_subtask": {
                                "subtask_id": "local_subtask",
                                "profile": "harness.observation",
                                "status": "completed",
                                "input_refs": ["artifact:sample"],
                                "result": {
                                    "reading": "A",
                                    "ambiguity": "",
                                    "observations": ["Only supplied input was used."],
                                    "limits": [],
                                },
                                "subtask_trace": {
                                    "model": "model-a",
                                    "prompt_char_count": 512,
                                    "image_attachment_count": 1,
                                },
                            },
                        }
                    ],
                },
                "tool_result_raw": {
                    "execution_state": "executed",
                    "outputs": {"image_b64": "SHOULD_NOT_RENDER"},
                },
            }
        ]
    )

    assert "subtask_profile: harness.observation" in body
    assert "subtask_task_excerpt:" in body
    assert "subtask_input_refs:" in body
    assert "subtask_result:" in body
    assert "status: completed" in body
    assert "reading:" in body
    assert "Only supplied input was used." in body
    assert "prompt_char_count" in body
    assert "SHOULD_NOT_RENDER" not in body
    assert "b64" not in body.lower()
