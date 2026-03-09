from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.evidence_executor import (
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


def test_normalize_image_evidence_locate_request_accepts_mode_and_target() -> None:
    request, reason = normalize_evidence_request(
        evidence_request={
            "kind": "image_evidence",
            "mode": "locate",
            "decision_key": "range",
            "target": {
                "query": "Find range clause.",
                "expected_fields": ["range"],
                "anchor_hint": "Township Fourteen North",
            },
        },
        decision_key="range",
    )
    assert reason == "ok"
    assert isinstance(request, dict)
    assert request.get("kind") == "image_evidence"
    assert request.get("mode") == "locate"
    target = request.get("target") if isinstance(request.get("target"), dict) else {}
    assert str(target.get("query") or "") == "Find range clause."


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


def test_normalize_image_evidence_rejects_expand_context_until_implemented() -> None:
    request, reason = normalize_evidence_request(
        evidence_request={
            "kind": "image_evidence",
            "mode": "expand_context",
            "decision_key": "range",
            "target": {"region_ref": {"artifact_path": "in-memory://region.jpg"}},
        },
        decision_key="range",
    )
    assert request is None
    assert reason == "image_evidence_mode_not_implemented:expand_context"


def test_execute_evidence_request_runs_image_evidence_mode() -> None:
    request, reason = normalize_evidence_request(
        evidence_request={
            "kind": "image_evidence",
            "mode": "verify",
            "decision_key": "range",
            "target": {"query": "Verify Range 75 West."},
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
            "mode": "verify",
            "image_evidence": {"mode": "verify", "status": "match"},
            "image_verification": {"payload": {"results": [{"check_id": "c1", "status": "match"}]}},
        },
    )
    assert result["status"] == "executed"
    assert result["kind"] == "image_evidence"
    assert result["mode"] == "verify"


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
