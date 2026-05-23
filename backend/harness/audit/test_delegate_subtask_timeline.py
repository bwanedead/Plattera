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


def test_timeline_renders_two_delegate_rows_with_custom_fields_and_no_b64() -> None:
    body = render_timeline(
        [
            {
                "turn_index": 3,
                "parse_ok": True,
                "tool_request": {
                    "actions": [
                        {
                            "alias": "read_a",
                            "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
                            "action_inputs": {
                                "profile": "transcript_edit.visual_source_observation",
                                "task": "Read bearing text in crop A.",
                                "context_refs": ["image:derived:a"],
                            },
                        },
                        {
                            "alias": "read_b",
                            "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
                            "action_inputs": {
                                "profile": "transcript_edit.visual_source_observation",
                                "task": "Read bearing text in crop B.",
                                "context_refs": ["image:derived:b"],
                            },
                        },
                    ],
                    "rationale": "delegate two localized reads",
                },
                "recent_action_sequence_result": {
                    "sequence_id": "seq-3",
                    "source_turn_index": 3,
                    "items": [
                        {
                            "alias": "read_a",
                            "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
                            "execution_state": "executed",
                            "delegate_subtask": {
                                "subtask_id": "read_a",
                                "profile": "transcript_edit.visual_source_observation",
                                "status": "completed",
                                "input_refs": ["image:derived:a"],
                                "result": {
                                    "task_response": "Crop A reads N. 4° 00' W.",
                                    "source_visible_text": "N. 4° 00' W.",
                                    "visual_basis": ["numeral resembles 4"],
                                    "ambiguity": "",
                                    "limits": [],
                                },
                            },
                        },
                        {
                            "alias": "read_b",
                            "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
                            "execution_state": "executed",
                            "delegate_subtask": {
                                "subtask_id": "read_b",
                                "profile": "transcript_edit.visual_source_observation",
                                "status": "failed",
                                "input_refs": ["image:derived:b"],
                                "result": {},
                                "errors": [
                                    {
                                        "reason_code": "subtask_output_malformed",
                                        "message": "Child output was not a JSON object.",
                                    }
                                ],
                            },
                        },
                    ],
                },
                "tool_result_raw": {
                    "execution_state": "executed",
                    "outputs": {"image_b64": "SHOULD_NOT_RENDER"},
                },
            }
        ]
    )

    assert "read_a" in body
    assert "read_b" in body
    assert body.count("subtask_profile: transcript_edit.visual_source_observation") == 2
    assert "source_visible_text:" in body
    assert "N. 4° 00' W." in body
    assert "subtask_output_malformed" in body
    assert "SHOULD_NOT_RENDER" not in body
    assert "b64" not in body.lower()


def test_timeline_renders_delegate_truncation_metadata() -> None:
    body = render_timeline(
        [
            {
                "turn_index": 4,
                "parse_ok": True,
                "tool_request": {
                    "actions": [
                        {
                            "alias": "read_crop",
                            "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
                            "action_inputs": {
                                "profile": "transcript_edit.visual_source_observation",
                                "task": "Read bearing text in localized crop.",
                                "context_refs": ["image:derived:crop_a"],
                            },
                        }
                    ],
                    "rationale": "delegate localized read",
                },
                "recent_action_sequence_result": {
                    "sequence_id": "seq-4",
                    "source_turn_index": 4,
                    "items": [
                        {
                            "alias": "read_crop",
                            "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
                            "execution_state": "executed",
                            "delegate_subtask": {
                                "subtask_id": "read_crop",
                                "profile": "transcript_edit.visual_source_observation",
                                "status": "completed",
                                "input_refs": ["image:derived:crop_a"],
                                "result_truncated": True,
                                "truncated_fields": ["task_response"],
                                "original_result_chars": 1800,
                                "result": {
                                    "task_response": "The visible bearing reads N. 4° 00' W.",
                                    "source_visible_text": "N. 4° 00' W.",
                                    "visual_basis": ["numeral resembles 4"],
                                    "ambiguity": "",
                                    "limits": [],
                                },
                            },
                        }
                    ],
                },
            }
        ]
    )

    assert "subtask_id: read_crop" in body
    assert "result_truncated: true" in body
    assert "truncated_fields:" in body
    assert "task_response" in body
    assert "original_result_chars: 1800" in body
    assert "image:derived:crop_a" in body
