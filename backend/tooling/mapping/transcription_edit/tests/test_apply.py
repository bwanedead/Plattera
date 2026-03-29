from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from backend.tooling.mapping.transcription_edit.apply import apply_plan, materialize_canonical_input
from backend.tooling.mapping.transcription_edit.contracts import (
    EditLoopStartRequestV0,
    EditPlanV0,
    transcript_text_hash,
)


def _base_plan(*, text: str, ops: list[dict]) -> EditPlanV0:
    return EditPlanV0(
        source_transcript_ref="artifact://transcript/source",
        source_transcript_hash=transcript_text_hash(text),
        plan_id="plan-1",
        summary="test plan",
        ops=ops,
    )


def test_apply_plan_empty_ops_is_valid_noop() -> None:
    text = "no changes requested"
    plan = _base_plan(text=text, ops=[])
    report = apply_plan(plan=plan, transcript_text=text)
    assert report.root_status == "applied"
    assert report.applied_count == 0
    assert report.refused_count == 0


def test_apply_plan_happy_path_offsets_replace_span() -> None:
    text = "Beginning at NW corner. Range seventy-four West."
    plan = _base_plan(
        text=text,
        ops=[
            {
                "op_id": "op-1",
                "op_type": "replace_span",
                "change_class": "semantic",
                "confidence": "high",
                "review_required": True,
                "reason": "fix range",
                "evidence_refs": [],
                "target": {"locator_type": "offsets", "start_char": 0, "end_char": len(text)},
                "expected_old": {"old_excerpt": "seventy-four", "old_hash": transcript_text_hash("seventy-four")},
                "new_text": "seventy-five",
            }
        ],
    )

    report = apply_plan(plan=plan, transcript_text=text)
    assert report.root_status == "applied"
    assert report.applied_count == 1
    assert report.refused_count == 0
    assert "seventy-five" in report.output_transcript_text
    assert report.op_results[0].status == "applied"


def test_apply_plan_root_hash_mismatch_refuses_entire_plan() -> None:
    text = "alpha beta gamma"
    plan = EditPlanV0(
        source_transcript_ref="artifact://transcript/source",
        source_transcript_hash=transcript_text_hash("different source"),
        plan_id="plan-2",
        summary="root mismatch",
        ops=[
            {
                "op_id": "op-1",
                "op_type": "replace_span",
                "change_class": "normalization",
                "confidence": "high",
                "review_required": False,
                "reason": "normalize",
                "evidence_refs": [],
                "target": {"locator_type": "offsets", "start_char": 0, "end_char": len(text)},
                "expected_old": {"old_excerpt": "alpha"},
                "new_text": "ALPHA",
            }
        ],
    )

    report = apply_plan(plan=plan, transcript_text=text)
    assert report.root_status == "refused"
    assert report.root_reason_code == "source_transcript_hash_mismatch"
    assert report.applied_count == 0
    assert report.refused_count == 1
    assert report.op_results[0].reason_code == "root_hash_mismatch"


def test_apply_plan_locator_not_found_refusal() -> None:
    text = "alpha beta gamma"
    plan = _base_plan(
        text=text,
        ops=[
            {
                "op_id": "op-1",
                "op_type": "replace_clause",
                "change_class": "semantic",
                "confidence": "medium",
                "review_required": True,
                "reason": "replace clause",
                "evidence_refs": [],
                "target": {
                    "locator_type": "anchors",
                    "start_anchor": "missing-start",
                    "end_anchor": "missing-end",
                    "occurrence": 1,
                },
                "expected_old": {"old_excerpt": "beta"},
                "new_text": "BETA",
            }
        ],
    )

    report = apply_plan(plan=plan, transcript_text=text)
    assert report.root_status == "refused"
    assert report.root_reason_code == "locator_not_found"
    assert report.applied_count == 0
    assert report.refused_count == 1
    assert report.op_results[0].reason_code == "locator_not_found"


def test_apply_plan_expected_old_mismatch_refusal() -> None:
    text = "alpha beta gamma"
    plan = _base_plan(
        text=text,
        ops=[
            {
                "op_id": "op-1",
                "op_type": "replace_line",
                "change_class": "semantic",
                "confidence": "medium",
                "review_required": True,
                "reason": "replace line",
                "evidence_refs": [],
                "target": {"locator_type": "offsets", "start_char": 0, "end_char": len(text)},
                "expected_old": {"old_excerpt": "delta"},
                "new_text": "DELTA",
            }
        ],
    )

    report = apply_plan(plan=plan, transcript_text=text)
    assert report.root_status == "refused"
    assert report.root_reason_code == "drift_mismatch"
    assert report.applied_count == 0
    assert report.refused_count == 1
    assert report.op_results[0].reason_code == "drift_mismatch"


def test_apply_plan_old_hash_mismatch_refusal() -> None:
    text = "alpha beta gamma"
    plan = _base_plan(
        text=text,
        ops=[
            {
                "op_id": "op-1",
                "op_type": "replace_span",
                "change_class": "semantic",
                "confidence": "high",
                "review_required": True,
                "reason": "hash mismatch",
                "evidence_refs": [],
                "target": {"locator_type": "offsets", "start_char": 0, "end_char": len(text)},
                "expected_old": {"old_excerpt": "alpha", "old_hash": transcript_text_hash("ALPHA")},
                "new_text": "ALPHA",
            }
        ],
    )

    report = apply_plan(plan=plan, transcript_text=text)
    assert report.root_status == "refused"
    assert report.root_reason_code == "old_hash_mismatch"
    assert report.applied_count == 0
    assert report.refused_count == 1
    assert report.op_results[0].reason_code == "old_hash_mismatch"


def test_apply_plan_multiple_ops_anchor_stable_after_offset_shift() -> None:
    text = "START parcel one END\nSTART parcel two END"
    plan = _base_plan(
        text=text,
        ops=[
            {
                "op_id": "op-1",
                "op_type": "replace_span",
                "change_class": "normalization",
                "confidence": "high",
                "review_required": False,
                "reason": "expand parcel one",
                "evidence_refs": [],
                "target": {"locator_type": "offsets", "start_char": 0, "end_char": len(text)},
                "expected_old": {"old_excerpt": "parcel one"},
                "new_text": "parcel one with additional words",
            },
            {
                "op_id": "op-2",
                "op_type": "replace_clause",
                "change_class": "semantic",
                "confidence": "high",
                "review_required": True,
                "reason": "repair parcel two",
                "evidence_refs": [],
                "target": {
                    "locator_type": "anchors",
                    "start_anchor": "START",
                    "end_anchor": "END",
                    "occurrence": 2,
                },
                "expected_old": {"old_excerpt": "parcel two"},
                "new_text": "parcel two fixed",
            },
        ],
    )

    report = apply_plan(plan=plan, transcript_text=text)
    assert report.applied_count == 2
    assert report.refused_count == 0
    assert "parcel one with additional words" in report.output_transcript_text
    assert "parcel two fixed" in report.output_transcript_text


def test_materialize_canonical_input_from_source_text() -> None:
    request = EditLoopStartRequestV0(
        source_text="user supplied transcript",
        source_image_refs=["artifact://img/1"],
        mode="repair_then_promote",
    )
    canonical = materialize_canonical_input(request)
    assert canonical.source_transcript_ref == "inline://source_text"
    assert canonical.transcript_text == "user supplied transcript"
    assert canonical.source_image_refs == ["artifact://img/1"]


def test_materialize_canonical_input_from_ref_sections(tmp_path: Path) -> None:
    payload = {
        "sections": [
            {"body": "Parcel one body"},
            {"text": "Parcel two text"},
        ]
    }
    source = tmp_path / "transcript.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    request = EditLoopStartRequestV0(source_transcript_ref=str(source), mode="repair")
    canonical = materialize_canonical_input(request)
    assert canonical.transcript_text == "Parcel one body\n\nParcel two text"
    assert canonical.source_transcript_hash == transcript_text_hash("Parcel one body\n\nParcel two text")


def test_edit_loop_start_request_requires_exactly_one_source() -> None:
    with pytest.raises(ValueError):
        EditLoopStartRequestV0(source_transcript_ref="artifact://x", source_text="text")
    with pytest.raises(ValueError):
        EditLoopStartRequestV0()


