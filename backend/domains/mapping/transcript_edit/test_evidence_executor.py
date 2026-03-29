from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.domains.mapping.transcript_edit.evidence_executor import (
    execute_evidence_request,
    normalize_evidence_request,
)


def test_normalize_evidence_request_rejects_decision_key_mismatch() -> None:
    request, reason = normalize_evidence_request(
        evidence_request={
            "kind": "image_verify",
            "decision_key": "section",
            "target": {"span_ids": ["s1"]},
        },
        decision_key="range",
    )
    assert request is None
    assert reason == "evidence_request_decision_key_mismatch"


def test_execute_evidence_request_runs_image_verify() -> None:
    request, reason = normalize_evidence_request(
        evidence_request={
            "kind": "image_verify",
            "decision_key": "range",
            "target": {"span_ids": ["s1"], "expected_fields": ["range"]},
        },
        decision_key="range",
    )
    assert reason == "ok"
    assert isinstance(request, dict)
    repeat_guard: dict[str, dict[str, object]] = {}
    result = execute_evidence_request(
        normalized_request=request,
        source_transcript_hash="sha256:test",
        repeat_guard=repeat_guard,
        evidence_signal_counter=0,
        max_repeats_per_signature=2,
        open_spans_runner=lambda _req: [],
        image_verify_runner=lambda _req: {"payload": {"results": [{"check_id": "c1", "status": "match"}]}},
    )
    assert result["status"] == "executed"
    assert result["kind"] == "image_verify"


def test_normalize_image_evidence_select_region_request_accepts_mode_and_target() -> None:
    request, reason = normalize_evidence_request(
        evidence_request={
            "kind": "image_evidence",
            "mode": "select_region",
            "decision_key": "range",
            "target": {
                "crop_box_normalized": {"x": 0.25, "y": 0.2, "width": 0.3, "height": 0.2},
                "zoom_factor": 2.4,
                "expected_fields": ["range"],
            },
        },
        decision_key="range",
    )
    assert reason == "ok"
    assert isinstance(request, dict)
    assert request.get("kind") == "image_evidence"
    assert request.get("mode") == "select_region"
    target = request.get("target") if isinstance(request.get("target"), dict) else {}
    assert isinstance(target.get("crop_box_normalized"), dict)


def test_normalize_image_evidence_accepts_target_mode_form() -> None:
    request, reason = normalize_evidence_request(
        evidence_request={
            "kind": "image_evidence",
            "decision_key": "range",
            "target": {
                "mode": "select_region",
                "crop_box_normalized": {"x": 0.25, "y": 0.2, "width": 0.3, "height": 0.2},
            },
        },
        decision_key="range",
    )
    assert reason == "ok"
    assert isinstance(request, dict)
    assert str(request.get("mode") or "") == "select_region"
    target = request.get("target") if isinstance(request.get("target"), dict) else {}
    assert target.get("mode") is None
    assert isinstance(target.get("crop_box_normalized"), dict)


def test_normalize_image_evidence_accepts_operation_key_form() -> None:
    request, reason = normalize_evidence_request(
        evidence_request={
            "kind": "image_evidence",
            "decision_key": "range",
            "target": {
                "verify_region": {
                    "region_ref": {"artifact_path": "in-memory://region.jpg"},
                    "query": "Verify Range 75 West.",
                }
            },
        },
        decision_key="range",
    )
    assert reason == "ok"
    assert isinstance(request, dict)
    assert str(request.get("mode") or "") == "verify_region"
    target = request.get("target") if isinstance(request.get("target"), dict) else {}
    assert isinstance(target.get("region_ref"), dict)
    assert str(target.get("query") or "") == "Verify Range 75 West."


def test_normalize_image_evidence_rejects_invalid_mode() -> None:
    request, reason = normalize_evidence_request(
        evidence_request={
            "kind": "image_evidence",
            "mode": "bad_mode",
            "decision_key": "range",
        },
        decision_key="range",
    )
    assert request is None
    assert reason == "image_evidence_mode_invalid"


def test_normalize_image_evidence_infers_select_region_when_mode_absent_and_crop_box_present() -> None:
    """A1 compatibility: agent omits mode, provides crop_box_normalized — should infer select_region."""
    request, reason = normalize_evidence_request(
        evidence_request={
            "kind": "image_evidence",
            "decision_key": "range",
            "reason": "Inspect range clause region.",
            "target": {
                "crop_box_normalized": {"x": 0.35, "y": 0.20, "width": 0.35, "height": 0.15},
                "zoom_factor": 2.4,
                "expected_fields": ["range"],
            },
        },
        decision_key="range",
    )
    assert reason == "ok", f"Expected ok, got {reason}"
    assert isinstance(request, dict)
    assert request.get("mode") == "select_region"
    target = request.get("target") or {}
    assert isinstance(target.get("crop_box_normalized"), dict)


def test_execute_evidence_request_dispatches_image_evidence_runner() -> None:
    """B: execute_evidence_request must route image_evidence to the image_evidence_runner."""
    evidence_request = {
        "kind": "image_evidence",
        "decision_key": "range",
        "reason": "Inspect range clause.",
        "target": {
            "crop_box_normalized": {"x": 0.35, "y": 0.20, "width": 0.35, "height": 0.15},
            "zoom_factor": 2.0,
        },
    }
    request, reason = normalize_evidence_request(evidence_request=evidence_request, decision_key="range")
    assert reason == "ok"
    assert request is not None

    runner_called: list[dict] = []

    def _image_evidence_runner(req: dict) -> dict:
        runner_called.append(req)
        return {
            "image_evidence": {
                "mode": "select_region",
                "status": "executed",
                "tx_image_evidence_region_ref": {"artifact_path": "in-memory://region.jpg"},
                "tx_image_evidence_context_ref": {"artifact_path": "in-memory://context.jpg"},
                "crop_box": {"x": 0.35, "y": 0.20, "width": 0.35, "height": 0.15},
                "zoom_factor": 2.0,
            }
        }

    result = execute_evidence_request(
        normalized_request=request,
        source_transcript_hash="sha256:test",
        repeat_guard={},
        evidence_signal_counter=0,
        max_repeats_per_signature=2,
        open_spans_runner=lambda _: [],
        image_verify_runner=lambda _: {},
        image_evidence_runner=_image_evidence_runner,
    )
    assert result["status"] == "executed"
    assert result["kind"] == "image_evidence"
    assert len(runner_called) == 1
    # Resulting image_evidence payload must include region/context refs
    img_ev = result.get("image_evidence") or {}
    assert isinstance(img_ev.get("tx_image_evidence_region_ref"), dict)


def test_normalize_image_evidence_rejects_conflicting_mode_sources() -> None:
    request, reason = normalize_evidence_request(
        evidence_request={
            "kind": "image_evidence",
            "mode": "verify_region",
            "decision_key": "range",
            "target": {
                "mode": "select_region",
                "crop_box_normalized": {"x": 0.25, "y": 0.2, "width": 0.3, "height": 0.2},
            },
        },
        decision_key="range",
    )
    assert request is None
    assert reason == "image_evidence_mode_conflict"


def test_normalize_image_evidence_rejects_multiple_operation_keys() -> None:
    request, reason = normalize_evidence_request(
        evidence_request={
            "kind": "image_evidence",
            "decision_key": "range",
            "target": {
                "select_region": {"crop_box_normalized": {"x": 0.25, "y": 0.2, "width": 0.3, "height": 0.2}},
                "verify_region": {
                    "region_ref": {"artifact_path": "in-memory://region.jpg"},
                    "query": "Verify Range 75 West.",
                },
            },
        },
        decision_key="range",
    )
    assert request is None
    assert reason == "image_evidence_target_mode_ambiguous"


def test_normalize_image_evidence_rejects_invalid_nested_operation_name() -> None:
    request, reason = normalize_evidence_request(
        evidence_request={
            "kind": "image_evidence",
            "decision_key": "range",
            "target": {
                "pick_region": {"crop_box_normalized": {"x": 0.25, "y": 0.2, "width": 0.3, "height": 0.2}},
            },
        },
        decision_key="range",
    )
    assert request is None
    assert reason == "image_evidence_nested_operation_invalid"


def test_normalize_image_evidence_refine_region_accepts_transform_fields() -> None:
    request, reason = normalize_evidence_request(
        evidence_request={
            "kind": "image_evidence",
            "mode": "refine_region",
            "decision_key": "range",
            "target": {
                "region_ref": {"artifact_path": "in-memory://region.jpg"},
                "transform": "expand",
                "amount": 0.2,
            },
        },
        decision_key="range",
    )
    assert reason == "ok"
    assert isinstance(request, dict)
    target = request.get("target") if isinstance(request.get("target"), dict) else {}
    assert str(target.get("transform") or "") == "expand"


def test_normalize_image_evidence_refine_region_crop_shorthand_normalizes_to_select_region() -> None:
    request, reason = normalize_evidence_request(
        evidence_request={
            "kind": "image_evidence",
            "mode": "refine_region",
            "decision_key": "range",
            "target": {
                "crop_box_normalized": {"x": 0.4, "y": 0.18, "width": 0.32, "height": 0.14},
                "zoom_factor": 3.0,
                "expected_fields": ["range"],
            },
        },
        decision_key="range",
    )
    assert reason == "ok"
    assert isinstance(request, dict)
    assert str(request.get("mode") or "") == "select_region"
    target = request.get("target") if isinstance(request.get("target"), dict) else {}
    assert isinstance(target.get("crop_box_normalized"), dict)
    assert target.get("zoom_factor") == 3.0


def test_normalize_image_evidence_select_region_rejects_missing_selector() -> None:
    request, reason = normalize_evidence_request(
        evidence_request={
            "kind": "image_evidence",
            "mode": "select_region",
            "decision_key": "range",
            "target": {
                "zoom_factor": 2.0,
            },
        },
        decision_key="range",
    )
    assert request is None
    assert reason == "image_evidence_select_region_target_missing"


def test_normalize_image_evidence_refine_region_rejects_missing_region_ref() -> None:
    request, reason = normalize_evidence_request(
        evidence_request={
            "kind": "image_evidence",
            "mode": "refine_region",
            "decision_key": "range",
            "target": {
                "transform": "expand",
                "amount": 0.15,
            },
        },
        decision_key="range",
    )
    assert request is None
    assert reason == "image_evidence_refine_region_region_ref_missing"


def test_normalize_image_evidence_verify_region_rejects_missing_query() -> None:
    request, reason = normalize_evidence_request(
        evidence_request={
            "kind": "image_evidence",
            "mode": "verify_region",
            "decision_key": "range",
            "target": {
                "region_ref": {"artifact_path": "in-memory://region.jpg"},
            },
        },
        decision_key="range",
    )
    assert request is None
    assert reason == "image_evidence_verify_region_query_missing"


def test_execute_evidence_request_runs_image_evidence_mode() -> None:
    request, reason = normalize_evidence_request(
        evidence_request={
            "kind": "image_evidence",
            "mode": "verify_region",
            "decision_key": "range",
            "target": {"region_ref": {"artifact_path": "in-memory://region.jpg"}, "query": "Verify Range 75 West."},
        },
        decision_key="range",
    )
    assert reason == "ok"
    assert isinstance(request, dict)
    result = execute_evidence_request(
        normalized_request=request,
        source_transcript_hash="sha256:test",
        repeat_guard={},
        evidence_signal_counter=0,
        max_repeats_per_signature=2,
        open_spans_runner=lambda _req: [],
        image_verify_runner=lambda _req: {},
        image_evidence_runner=lambda _req: {
            "mode": "verify_region",
            "image_evidence": {"mode": "verify_region", "status": "match"},
            "image_verification": {"payload": {"results": [{"check_id": "c1", "status": "match"}]}},
        },
    )
    assert result["status"] == "executed"
    assert result["kind"] == "image_evidence"
    assert result["mode"] == "verify_region"


def test_execute_evidence_request_blocks_repeats_without_new_signal() -> None:
    request, reason = normalize_evidence_request(
        evidence_request={"kind": "open_spans", "decision_key": "section"},
        decision_key="section",
    )
    assert reason == "ok"
    assert isinstance(request, dict)
    repeat_guard: dict[str, dict[str, object]] = {}
    first = execute_evidence_request(
        normalized_request=request,
        source_transcript_hash="sha256:test",
        repeat_guard=repeat_guard,
        evidence_signal_counter=3,
        max_repeats_per_signature=1,
        open_spans_runner=lambda _req: [{"span_id": "s1"}],
        image_verify_runner=lambda _req: {},
    )
    second = execute_evidence_request(
        normalized_request=request,
        source_transcript_hash="sha256:test",
        repeat_guard=repeat_guard,
        evidence_signal_counter=3,
        max_repeats_per_signature=1,
        open_spans_runner=lambda _req: [{"span_id": "s1"}],
        image_verify_runner=lambda _req: {},
    )
    assert first["status"] == "executed"
    assert second["status"] == "repeat_blocked"


def test_execute_evidence_request_repeat_budget_resets_on_new_signal() -> None:
    request, reason = normalize_evidence_request(
        evidence_request={"kind": "open_spans", "decision_key": "section"},
        decision_key="section",
    )
    assert reason == "ok"
    assert isinstance(request, dict)
    repeat_guard: dict[str, dict[str, object]] = {}
    _ = execute_evidence_request(
        normalized_request=request,
        source_transcript_hash="sha256:test",
        repeat_guard=repeat_guard,
        evidence_signal_counter=1,
        max_repeats_per_signature=1,
        open_spans_runner=lambda _req: [{"span_id": "s1"}],
        image_verify_runner=lambda _req: {},
    )
    blocked = execute_evidence_request(
        normalized_request=request,
        source_transcript_hash="sha256:test",
        repeat_guard=repeat_guard,
        evidence_signal_counter=1,
        max_repeats_per_signature=1,
        open_spans_runner=lambda _req: [{"span_id": "s1"}],
        image_verify_runner=lambda _req: {},
    )
    resumed = execute_evidence_request(
        normalized_request=request,
        source_transcript_hash="sha256:test",
        repeat_guard=repeat_guard,
        evidence_signal_counter=2,
        max_repeats_per_signature=1,
        open_spans_runner=lambda _req: [{"span_id": "s1"}],
        image_verify_runner=lambda _req: {},
    )
    assert blocked["status"] == "repeat_blocked"
    assert resumed["status"] == "executed"


def test_execute_evidence_request_dependency_unsupported_is_safe() -> None:
    request, reason = normalize_evidence_request(
        evidence_request={"kind": "retrieve_dependency_evidence", "decision_key": "range"},
        decision_key="range",
    )
    assert reason == "ok"
    assert isinstance(request, dict)
    result = execute_evidence_request(
        normalized_request=request,
        source_transcript_hash="sha256:test",
        repeat_guard={},
        evidence_signal_counter=0,
        max_repeats_per_signature=2,
        open_spans_runner=lambda _req: [],
        image_verify_runner=lambda _req: {},
        retrieve_dependency_runner=None,
    )
    assert result["status"] == "unsupported"

