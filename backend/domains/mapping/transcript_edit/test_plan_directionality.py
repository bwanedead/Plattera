"""Phase 22 — edit plan directionality and HITL locator vs corrected-value checks."""

from __future__ import annotations

from tooling.mapping.transcription_edit.contracts import EditPlanV0, transcript_text_hash

from domains.mapping.transcript_edit.plan_interpretation import validate_edit_plan_directionality


def _plan(
    *,
    old_excerpt: str,
    new_text: str,
    source_hash: str,
) -> EditPlanV0:
    return EditPlanV0.model_validate(
        {
            "plan_version": "edit_plan_v0",
            "source_transcript_ref": "artifact://t.json",
            "source_transcript_hash": source_hash,
            "plan_id": "p1",
            "summary": "test",
            "ops": [
                {
                    "op_id": "op-1",
                    "op_type": "replace_span",
                    "change_class": "semantic",
                    "confidence": "high",
                    "review_required": True,
                    "reason": "fix range",
                    "evidence_refs": [],
                    "target": {
                        "locator_type": "offsets",
                        "start_char": 0,
                        "end_char": 40,
                    },
                    "expected_old": {"old_excerpt": old_excerpt},
                    "new_text": new_text,
                }
            ],
        }
    )


def test_directionality_accepts_wrong_to_correct_range() -> None:
    text = 'Thence Range 74 West to a point. Should be Range 75 West.'
    h = transcript_text_hash(text)
    plan = _plan(old_excerpt="Range 74 West", new_text="Range 75 West", source_hash=h)
    ok, reason = validate_edit_plan_directionality(
        plan=plan,
        transcript_text=text,
        feedback={"selected_value": "Range 75 West"},
        injection_context=None,
    )
    assert ok is True
    assert reason is None


def test_directionality_rejects_removing_authoritative_correct_value() -> None:
    text = "Range 75 West is the recorded call."
    h = transcript_text_hash(text)
    plan = _plan(old_excerpt="Range 75 West", new_text="Range 74 West", source_hash=h)
    ok, reason = validate_edit_plan_directionality(
        plan=plan,
        transcript_text=text,
        feedback={"selected_value": "Range 75 West"},
        injection_context=None,
    )
    assert ok is False
    assert reason == "plan_removes_authoritative_range_value"


def test_directionality_expected_old_must_be_in_working_transcript() -> None:
    text = "No range token here."
    h = transcript_text_hash(text)
    plan = _plan(old_excerpt="Range 74 West", new_text="Range 75 West", source_hash=h)
    ok, reason = validate_edit_plan_directionality(
        plan=plan,
        transcript_text=text,
        feedback={"selected_value": "Range 75 West"},
        injection_context=None,
    )
    assert ok is False
    assert reason == "expected_old_not_in_working_transcript"



