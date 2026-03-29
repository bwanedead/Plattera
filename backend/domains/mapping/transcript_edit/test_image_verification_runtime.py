from __future__ import annotations

import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from agent_kernel.models import StepExecutionState

import backend.domains.mapping.transcript_edit.image_verification as image_verification
from backend.domains.mapping.transcript_edit.image_verification import (
    _next_wait_heartbeat_threshold,
    _run_step_with_heartbeat,
    verify_mapping_critical_with_image,
)


class _Dash:
    def __init__(self, latest_refs: dict) -> None:
        self._latest_refs = latest_refs

    @property
    def latest_refs(self):  # type: ignore[no-untyped-def]
        return SimpleNamespace(model_dump=lambda mode="json": self._latest_refs)


def _executed_step() -> object:
    return SimpleNamespace(
        execution_state=StepExecutionState.EXECUTED,
        dashboard=_Dash({"tx_image_verify_ref": {"artifact_path": "in-memory://none"}}),
        refusal=None,
        step_record={"outputs_inline": {"tx_image_verify_results": [{"check_id": "c1", "status": "match"}]}},
    )


def _refused_step() -> object:
    return SimpleNamespace(
        execution_state=StepExecutionState.REFUSED,
        dashboard=_Dash({"tx_image_verify_ref": {"artifact_path": "in-memory://none"}}),
        refusal=SimpleNamespace(reason_code="openai_500"),
        step_record={"outputs_inline": {}},
    )


def test_wait_thresholds_are_throttled() -> None:
    seen: set[int] = set()
    assert _next_wait_heartbeat_threshold(elapsed_seconds=3, emitted_thresholds=seen) is None
    assert _next_wait_heartbeat_threshold(elapsed_seconds=15, emitted_thresholds=seen) == 15
    seen.add(15)
    assert _next_wait_heartbeat_threshold(elapsed_seconds=20, emitted_thresholds=seen) is None
    assert _next_wait_heartbeat_threshold(elapsed_seconds=30, emitted_thresholds=seen) == 30
    seen.add(30)
    assert _next_wait_heartbeat_threshold(elapsed_seconds=60, emitted_thresholds=seen) == 60
    seen.add(60)
    assert _next_wait_heartbeat_threshold(elapsed_seconds=89, emitted_thresholds=seen) is None
    assert _next_wait_heartbeat_threshold(elapsed_seconds=121, emitted_thresholds=seen) == 120


def test_verify_mapping_critical_with_image_reports_failure_after_bounded_retries() -> None:
    calls = {"n": 0}

    def _step_fn(**kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        return _refused_step()

    out = verify_mapping_critical_with_image(
        session_manager=object(),
        session_id="s1",
        iteration=1,
        dossier_id="D1",
        source_transcript_ref="in-memory://source.json",
        top_findings=[{"finding_id": "plss_range_conflict_001", "finding_type": "plss_consistency", "message": "Range conflict"}],
        disagreement_hints={},
        source_image_refs=["in-memory://img.png"],
        model="gpt-5.2",
        step_fn=_step_fn,
        read_step_outputs_inline_fn=lambda record: (record.get("outputs_inline") if isinstance(record, dict) else {}),
        read_str_fn=lambda value: str(value) if isinstance(value, str) else None,
        progress_cb=None,
        focus_decision_key="range",
        llm_call_seq_start=0,
    )
    summary = (out.get("payload") or {}).get("summary") if isinstance(out.get("payload"), dict) else {}
    diagnostics = (out.get("payload") or {}).get("diagnostics") if isinstance(out.get("payload"), dict) else []
    assert calls["n"] == 2
    assert int(summary.get("failed_count") or 0) >= 1
    assert isinstance(diagnostics, list) and len(diagnostics) >= 1
    assert int(out.get("llm_call_seq_end") or 0) == 2


def test_verify_mapping_critical_with_image_surfaces_focus_mismatch_context() -> None:
    def _step_fn(**kwargs):  # type: ignore[no-untyped-def]
        return _executed_step()

    out = verify_mapping_critical_with_image(
        session_manager=object(),
        session_id="s1",
        iteration=1,
        dossier_id="D1",
        source_transcript_ref="in-memory://source.json",
        top_findings=[{"finding_id": "plss_range_conflict_001", "finding_type": "plss_consistency", "message": "Range token conflict"}],
        disagreement_hints={},
        source_image_refs=["in-memory://img.png"],
        model="gpt-5.2",
        step_fn=_step_fn,
        read_step_outputs_inline_fn=lambda record: (record.get("outputs_inline") if isinstance(record, dict) else {}),
        read_str_fn=lambda value: str(value) if isinstance(value, str) else None,
        progress_cb=None,
        focus_decision_key="acreage",
        llm_call_seq_start=10,
    )
    results = (out.get("payload") or {}).get("results") if isinstance(out.get("payload"), dict) else []
    assert isinstance(results, list) and len(results) >= 1
    row = results[0]
    assert str(row.get("decision_key") or "") == "range"
    assert str(row.get("focus_decision_key") or "") == "acreage"
    assert isinstance(row.get("query"), str) and len(str(row.get("query"))) > 0


def test_verify_mapping_critical_with_image_anchors_generic_plss_to_focus_when_key_missing() -> None:
    def _step_fn(**kwargs):  # type: ignore[no-untyped-def]
        return _executed_step()

    out = verify_mapping_critical_with_image(
        session_manager=object(),
        session_id="s1",
        iteration=1,
        dossier_id="D1",
        source_transcript_ref="in-memory://source.json",
        top_findings=[
            {
                "finding_id": "plss_conflict_001",
                "finding_type": "plss_consistency",
                "message": "PLSS token contradiction near location clause.",
            }
        ],
        disagreement_hints={},
        source_image_refs=["in-memory://img.png"],
        model="gpt-5.2",
        step_fn=_step_fn,
        read_step_outputs_inline_fn=lambda record: (record.get("outputs_inline") if isinstance(record, dict) else {}),
        read_str_fn=lambda value: str(value) if isinstance(value, str) else None,
        progress_cb=None,
        focus_decision_key="range",
        llm_call_seq_start=20,
    )
    results = (out.get("payload") or {}).get("results") if isinstance(out.get("payload"), dict) else []
    assert isinstance(results, list) and len(results) >= 1
    row = results[0]
    assert str(row.get("decision_key") or "") == "range"
    assert str(row.get("focus_decision_key") or "") == "range"


def test_run_step_with_heartbeat_emits_no_events_before_first_threshold(monkeypatch) -> None:
    monkeypatch.setattr(image_verification, "_IMAGE_VERIFY_HEARTBEAT_THRESHOLDS_SECONDS", (3,))
    monkeypatch.setattr(image_verification, "_IMAGE_VERIFY_HEARTBEAT_EVERY_SECONDS", 60)
    events: list[dict] = []

    def _step_fn(**kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        time.sleep(1.2)
        return _executed_step()

    _ = _run_step_with_heartbeat(
        session_manager=object(),
        session_id="s1",
        iteration=1,
        check_index=1,
        check_total=1,
        check_id="c1",
        step_fn=_step_fn,
        step_inputs={},
        progress_cb=lambda evt: events.append(evt if isinstance(evt, dict) else {}),
        llm_call_seq=1,
        phase_attempt=1,
        focus_decision_key="range",
        check_decision_key="range",
        timeout_seconds=10,
        heartbeat_thresholds_seconds=(1,),
        heartbeat_every_seconds=60,
    )
    assert events == []


def test_run_step_with_heartbeat_emits_only_thresholded_events(monkeypatch) -> None:
    monkeypatch.setattr(image_verification, "_IMAGE_VERIFY_HEARTBEAT_THRESHOLDS_SECONDS", (1,))
    monkeypatch.setattr(image_verification, "_IMAGE_VERIFY_HEARTBEAT_EVERY_SECONDS", 60)
    events: list[dict] = []

    def _step_fn(**kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        time.sleep(2.2)
        return _executed_step()

    _ = _run_step_with_heartbeat(
        session_manager=object(),
        session_id="s1",
        iteration=1,
        check_index=1,
        check_total=1,
        check_id="c1",
        step_fn=_step_fn,
        step_inputs={},
        progress_cb=lambda evt: events.append(evt if isinstance(evt, dict) else {}),
        llm_call_seq=2,
        phase_attempt=1,
        focus_decision_key="range",
        check_decision_key="range",
        timeout_seconds=10,
        heartbeat_thresholds_seconds=(1,),
        heartbeat_every_seconds=60,
    )
    assert len(events) == 1
    assert str(events[0].get("stage") or "") == "waiting"


def test_run_step_with_heartbeat_emits_wait_metadata(monkeypatch) -> None:
    monkeypatch.setattr(image_verification, "_IMAGE_VERIFY_HEARTBEAT_THRESHOLDS_SECONDS", (1,))
    events: list[dict] = []

    def _step_fn(**kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        time.sleep(1.3)
        return _executed_step()

    _ = _run_step_with_heartbeat(
        session_manager=object(),
        session_id="s1",
        iteration=1,
        check_index=1,
        check_total=1,
        check_id="c1",
        step_fn=_step_fn,
        step_inputs={},
        progress_cb=lambda evt: events.append(evt if isinstance(evt, dict) else {}),
        llm_call_seq=3,
        phase_attempt=1,
        focus_decision_key="range",
        check_decision_key="range",
        timeout_seconds=10,
        heartbeat_thresholds_seconds=(1,),
        heartbeat_every_seconds=60,
        phase_started_at_epoch_seconds=1773000001,
        max_attempts_per_check=1,
    )
    assert len(events) >= 1
    detail = events[0]
    assert detail.get("wait_reason") == "awaiting_image_verify_step_response"
    assert int(detail.get("timeout_seconds") or 0) == 10
    assert int(detail.get("max_attempts_per_check") or 0) == 1
    assert int(detail.get("phase_started_at_epoch_seconds") or 0) == 1773000001


def test_verify_mapping_critical_with_image_surfaces_region_refs_from_inline_outputs() -> None:
    def _step_fn(**kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        return SimpleNamespace(
            execution_state=StepExecutionState.EXECUTED,
            dashboard=_Dash({"tx_image_verify_ref": {"artifact_path": "in-memory://none"}}),
            refusal=None,
            step_record={
                "outputs_inline": {
                    "tx_image_verify_results": [{"check_id": "c1", "status": "match"}],
                    "tx_image_evidence_region_ref": {"artifact_path": "in-memory://region.jpg"},
                    "tx_image_evidence_context_ref": {"artifact_path": "in-memory://context.jpg"},
                }
            },
        )

    out = verify_mapping_critical_with_image(
        session_manager=object(),
        session_id="s1",
        iteration=1,
        dossier_id="D1",
        source_transcript_ref="in-memory://source.json",
        top_findings=[{"finding_id": "plss_range_conflict_001", "finding_type": "plss_consistency", "message": "Range token conflict"}],
        disagreement_hints={},
        source_image_refs=["in-memory://img.png"],
        model="gpt-5.2",
        step_fn=_step_fn,
        read_step_outputs_inline_fn=lambda record: (record.get("outputs_inline") if isinstance(record, dict) else {}),
        read_str_fn=lambda value: str(value) if isinstance(value, str) else None,
        progress_cb=None,
        focus_decision_key="range",
    )
    results = (out.get("payload") or {}).get("results") if isinstance(out.get("payload"), dict) else []
    assert isinstance(results, list) and results
    row = results[0]
    assert isinstance(row.get("tx_image_evidence_region_ref"), dict)
    assert str((row.get("tx_image_evidence_region_ref") or {}).get("artifact_path") or "") == "in-memory://region.jpg"

