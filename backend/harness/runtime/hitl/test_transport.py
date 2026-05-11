from __future__ import annotations

from typing import Any
from unittest.mock import patch

from harness.runtime.hitl.transport import (
    HitlTransportPosture,
    hitl_poll_feedback_store,
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


# ---------------------------------------------------------------------------
# Inbound feedback admission goes through the size-bounding normalizer.
# ---------------------------------------------------------------------------


def _stub_list_entries(entries: list[dict[str, Any]]):
    """Build a feedback_store.list_entries replacement that yields the given entries."""
    def _impl(*, loop_kind: str, run_id: str) -> list[dict[str, Any]]:
        return list(entries)
    return _impl


def test_poll_feedback_store_normalizes_admitted_responses() -> None:
    """Pathologically large note from the feedback store is admitted bounded."""
    posture = HitlTransportPosture(
        pending_hitl_requests=[{"prompt_id": "p1", "message": "Q?"}],
    )
    big_note = "n" * 50_000
    raw_entry = {
        "prompt_id": "p1",
        "choice": "yes",
        "note": big_note,
        "submitted_at_epoch_seconds": 1000.0,
        "untracked_field": "should be dropped",
    }
    with patch("services.agent_viewer.feedback_store.list_entries", _stub_list_entries([raw_entry])):
        hitl_poll_feedback_store(posture=posture, loop_kind="any", run_id="r1")

    assert len(posture.answered_hitl_responses) == 1
    feedback = posture.answered_hitl_responses[0]["feedback"]
    # Note clamped to 16384 chars
    assert len(feedback["note"]) == 16_384
    # Truncation marker visible to downstream consumers
    assert feedback.get("_bounds", {}).get("note_truncated") is True
    # Untracked fields stripped at admission
    assert "untracked_field" not in feedback
    # Response carries the prompt_id and unchanged short fields
    assert feedback["choice"] == "yes"
    assert feedback["submitted_at_epoch_seconds"] == 1000.0


def test_poll_feedback_store_callback_receives_normalized_payload() -> None:
    """on_inbound callback (used by ledger + trace) sees the bounded payload."""
    posture = HitlTransportPosture(
        pending_hitl_requests=[{"prompt_id": "p1", "message": "Q?"}],
    )
    raw_entry = {
        "prompt_id": "p1",
        "choice": "yes",
        "note": "n" * 50_000,
        "submitted_at_epoch_seconds": 1.0,
    }
    captured: list[tuple[str, dict[str, Any]]] = []

    def _on_inbound(prompt_id: str, feedback: dict[str, Any]) -> None:
        captured.append((prompt_id, feedback))

    with patch("services.agent_viewer.feedback_store.list_entries", _stub_list_entries([raw_entry])):
        hitl_poll_feedback_store(posture=posture, loop_kind="any", run_id="r1", on_inbound=_on_inbound)

    assert len(captured) == 1
    pid, feedback = captured[0]
    assert pid == "p1"
    assert len(feedback["note"]) == 16_384
    assert feedback["_bounds"]["note_truncated"] is True


def test_poll_feedback_store_pending_feedback_response_also_normalized() -> None:
    """When the inbound matches blocking_prompt_id, pending_feedback_response is also bounded."""
    posture = HitlTransportPosture(
        pending_hitl_requests=[{"prompt_id": "p1", "message": "Q?"}],
        blocking_prompt_id="p1",
    )
    raw_entry = {"prompt_id": "p1", "choice": "yes", "note": "n" * 30_000}
    with patch("services.agent_viewer.feedback_store.list_entries", _stub_list_entries([raw_entry])):
        hitl_poll_feedback_store(posture=posture, loop_kind="any", run_id="r1")

    assert posture.pending_feedback_response is not None
    assert len(posture.pending_feedback_response["note"]) == 16_384
    assert posture.pending_feedback_response["_bounds"]["note_truncated"] is True
