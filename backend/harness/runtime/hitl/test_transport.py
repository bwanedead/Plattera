from __future__ import annotations

from harness.runtime.hitl.transport import (
    HitlTransportPosture,
    hitl_prompt_visible_slice,
    hitl_refresh_derived_state,
)


def test_hitl_refresh_marks_async_when_multiple_pending_prompts_exist() -> None:
    posture = HitlTransportPosture(
        pending_hitl_requests=[
            {"prompt_id": "p-range", "message": "Range?", "choices": [], "context": {}},
            {"prompt_id": "p-cutoff", "message": "Cutoff?", "choices": [], "context": {}},
        ]
    )
    hitl_refresh_derived_state(posture)
    assert posture.hitl_state == "async_prompts_pending"


def test_hitl_prompt_visible_slice_preserves_multiple_pending_requests() -> None:
    posture = HitlTransportPosture(
        pending_hitl_requests=[
            {"prompt_id": "p-range", "message": "Range?", "choices": ["74", "75"], "context": {"primary_evidence_ref": "image:1"}},
            {"prompt_id": "p-cutoff", "message": "More source exists?", "choices": ["Yes", "No"], "context": {"primary_evidence_ref": "image:2"}},
        ]
    )
    pending, answered, state = hitl_prompt_visible_slice(posture)
    assert state == "no_prompt"
    assert answered == []
    assert [row["prompt_id"] for row in pending] == ["p-range", "p-cutoff"]
