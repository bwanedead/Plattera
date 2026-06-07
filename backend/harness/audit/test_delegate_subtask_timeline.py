from __future__ import annotations

from pathlib import Path

from harness.audit.delegate_subtask_timeline import render_delegate_subtask_section
from harness.audit.human_timeline import render_timeline
from harness.audit.artifact_ref_links import ArtifactLinkContext
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
                                    "hydration_seconds": 0.12,
                                    "model_call_seconds": 18.42,
                                    "total_seconds": 18.56,
                                    "retry_count": 0,
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

    assert "Delegate subtask `local_subtask`" in body
    assert "profile: `harness.observation`" in body
    assert "- prompt:" in body
    assert "context refs:" in body
    assert "- result:" in body
    assert "status: completed" in body
    assert "reading:" in body
    assert "Only supplied input was used." in body
    assert "prompt_chars=" in body
    assert "model=" in body
    assert "wall=" in body
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

    assert body.count("Delegate subtask `read_a`") == 1
    assert body.count("Delegate subtask `read_b`") == 1
    assert body.count("profile: `transcript_edit.visual_source_observation`") == 2
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

    assert "Delegate subtask `read_crop`" in body
    assert "result_truncated: true" in body
    assert "truncated_fields:" in body
    assert "task_response" in body
    assert "original_result_chars: 1800" in body
    assert "image:derived:crop_a" in body


def test_delegate_context_ref_renders_image_link_when_resolvable(tmp_path: Path) -> None:
    image_path = tmp_path / "crop-a.png"
    image_path.write_bytes(b"png")
    timeline_path = tmp_path / "audit" / "human" / "timeline.md"
    timeline_path.parent.mkdir(parents=True)
    context = ArtifactLinkContext(
        timeline_path=timeline_path,
        ref_path_index={"image:derived:crop_a": str(image_path)},
    )
    lines = render_delegate_subtask_section(
        alias="read_crop",
        inputs={
            "profile": "transcript_edit.visual_source_observation",
            "task": "Read the visible bearing only.",
            "context_refs": ["image:derived:crop_a"],
        },
        item={
            "alias": "read_crop",
            "execution_state": "executed",
            "delegate_subtask": {
                "subtask_id": "read_crop",
                "profile": "transcript_edit.visual_source_observation",
                "status": "completed",
                "result": {"task_response": "N. 37° 00' W."},
            },
        },
        link_context=context,
    )
    rendered = "\n".join(lines)
    assert "[open crop](../../crop-a.png)" in rendered
    assert "task_response: `N. 37° 00' W.`" in rendered
