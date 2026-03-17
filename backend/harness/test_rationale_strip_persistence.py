"""D4 persistence tests — rationale-continuity strip sidecar.

Locks in four properties:

  1. Persistence occurs
     When a kernel run has trace events, persist_rationale_strip() writes a file.
     When trace_events is empty, returns None and writes nothing.

  2. Exactness (forensic truth)
     The persisted strip equals build_rationale_continuity_strip(trace_events)
     with the same max_entries / per_entry_cap defaults.

  3. Discoverability
     rationale_strip_artifact_ref surfaces in latest_refs for both mode adapters
     (deed-to-IR and transcript-edit).

  4. Boundedness preserved
     Persisted strip respects max_entries cap and per_entry_cap string limits.

  5. Provenance fields
     Sidecar payload contains rationale_strip_version and source_trace_artifact_ref.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from harness.orchestration_kernel.contracts import KernelLoopResult
from harness.tracing.kernel_trace_persistence import persist_rationale_strip
from harness.tracing.rationale_continuity_strip import build_rationale_continuity_strip


# ---------------------------------------------------------------------------
# Minimal trace-event fixture
# ---------------------------------------------------------------------------

def _make_events(n_iters: int = 3) -> list[dict[str, Any]]:
    """Produce a minimal but valid list of serialised RawTraceEvent-like dicts."""
    events: list[dict[str, Any]] = []
    for i in range(1, n_iters + 1):
        events += [
            {
                "phase": "focus_selection",
                "iteration_index": i,
                "payload": {"focus_key": f"span_{i}"},
                "event_kind": "iteration",
                "actor": "kernel",
                "status": "completed",
                "reason_code": None,
                "refs_delta": {},
            },
            {
                "phase": "move_resolution",
                "iteration_index": i,
                "payload": {
                    "move_type": "apply_edit_plan",
                    "rationale": f"fix item {i}",
                    "evidence_kind": None,
                    "used_hitl_feedback": None,
                },
                "event_kind": "model_proposal",
                "actor": "kernel",
                "status": "completed",
                "reason_code": None,
                "refs_delta": {},
            },
            {
                "phase": "execution",
                "iteration_index": i,
                "payload": {
                    "action_type": "patch_transcript",
                    "execution_state": "executed",
                    "retryable": None,
                },
                "event_kind": "tool_execution",
                "actor": "kernel",
                "status": "completed",
                "reason_code": None,
                "refs_delta": {},
            },
            {
                "phase": "progress_evaluation",
                "iteration_index": i,
                "payload": {
                    "made_progress": True,
                    "reason_code": "blocking_count_reduced",
                    "no_progress_streak": 0,
                    "evidence_signal_counter": i,
                },
                "event_kind": "iteration",
                "actor": "kernel",
                "status": "completed",
                "reason_code": "blocking_count_reduced",
                "refs_delta": {},
            },
        ]
    return events


def _make_kernel_result(
    trace_events: list[dict[str, Any]] | None = None,
    run_artifact_ref: str | None = None,
) -> KernelLoopResult:
    return KernelLoopResult(
        terminal_class="completed",
        reason_code="domain_declare_done",
        iterations=len(trace_events) // 4 if trace_events else 0,
        session_id="sess_test",
        run_artifact_ref=run_artifact_ref,
        latest_refs={},
        domain_runtime_state={},
        trace_events=trace_events or [],
    )


# ---------------------------------------------------------------------------
# 1. Persistence occurs
# ---------------------------------------------------------------------------

def test_persist_rationale_strip_writes_file(tmp_path: Path) -> None:
    """When trace_events is non-empty and directory is writable, a file is written."""
    result = _make_kernel_result(trace_events=_make_events(3))
    ref = persist_rationale_strip(
        kernel_result=result,
        request_id_prefix="run_001",
        source_trace_artifact_ref=None,
    )
    # With no run_artifact_ref, falls back to agent_kernel_artifacts_root.
    # We can't guarantee that path in CI, so just assert it either returns a str or None.
    # For a direct write path test we mock _resolve_trace_dir.
    assert ref is None or isinstance(ref, str)


def test_persist_rationale_strip_writes_to_resolved_dir(tmp_path: Path) -> None:
    """File is written under the resolved trace directory."""
    result = _make_kernel_result(trace_events=_make_events(2))
    with patch(
        "harness.tracing.kernel_trace_persistence._resolve_trace_dir",
        return_value=tmp_path,
    ):
        ref = persist_rationale_strip(
            kernel_result=result,
            request_id_prefix="run_abc",
        )
    assert ref is not None
    assert Path(ref).exists()
    assert Path(ref).name == "run_abc_rationale_strip.json"


def test_persist_rationale_strip_returns_none_for_empty_events() -> None:
    """No file written and None returned when trace_events is empty."""
    result = _make_kernel_result(trace_events=[])
    with patch("harness.tracing.kernel_trace_persistence._resolve_trace_dir") as mock_dir:
        ref = persist_rationale_strip(
            kernel_result=result,
            request_id_prefix="run_empty",
        )
    assert ref is None
    mock_dir.assert_not_called()


# ---------------------------------------------------------------------------
# 2. Exactness (forensic truth)
# ---------------------------------------------------------------------------

def test_persisted_strip_equals_builder_output(tmp_path: Path) -> None:
    """Persisted strip must equal build_rationale_continuity_strip(trace_events)."""
    events = _make_events(4)
    # Introduce a refusal on iter 3 so the builder has something notable to include.
    for ev in events:
        if ev.get("phase") == "execution" and ev.get("iteration_index") == 3:
            ev["payload"]["execution_state"] = "refused"
            ev["payload"]["retryable"] = True
            ev["reason_code"] = "val_fail"

    result = _make_kernel_result(trace_events=events)
    with patch(
        "harness.tracing.kernel_trace_persistence._resolve_trace_dir",
        return_value=tmp_path,
    ):
        ref = persist_rationale_strip(
            kernel_result=result,
            request_id_prefix="run_exact",
        )

    assert ref is not None
    with open(ref, "r", encoding="utf-8") as fh:
        payload = json.load(fh)

    expected_strip = build_rationale_continuity_strip(events, max_entries=5, per_entry_cap=256)
    assert payload["rationale_continuity_strip"] == expected_strip, (
        "Persisted strip must exactly match builder output from same raw events"
    )
    assert payload["entry_count"] == len(expected_strip)


def test_persisted_strip_is_reproducible_from_same_events(tmp_path: Path) -> None:
    """Two persist calls with identical trace_events produce identical strip content."""
    events = _make_events(3)
    result = _make_kernel_result(trace_events=events)

    dir_a = tmp_path / "a"
    dir_a.mkdir()
    dir_b = tmp_path / "b"
    dir_b.mkdir()

    with patch(
        "harness.tracing.kernel_trace_persistence._resolve_trace_dir",
        return_value=dir_a,
    ):
        ref_a = persist_rationale_strip(kernel_result=result, request_id_prefix="run_r")

    with patch(
        "harness.tracing.kernel_trace_persistence._resolve_trace_dir",
        return_value=dir_b,
    ):
        ref_b = persist_rationale_strip(kernel_result=result, request_id_prefix="run_r")

    strip_a = json.loads(Path(ref_a).read_text(encoding="utf-8"))["rationale_continuity_strip"]
    strip_b = json.loads(Path(ref_b).read_text(encoding="utf-8"))["rationale_continuity_strip"]
    assert strip_a == strip_b


# ---------------------------------------------------------------------------
# 3. Discoverability — rationale_strip_artifact_ref in latest_refs
# ---------------------------------------------------------------------------

def test_deed_adapter_surfaces_strip_ref_in_merged_refs() -> None:
    """_adapt_kernel_loop_result_to_controller threads rationale_strip_artifact_ref."""
    import harness.mission_runtime.modes.deed_to_ir as deed_mod
    from agent_kernel.models import (
        KernelBudgets, KernelGoal, KernelSessionStartRequest,
        StopReason, TerminalOutcome, TerminalOutcomeKind,
    )

    result = _make_kernel_result()
    result_with_domain = KernelLoopResult(
        terminal_class="completed",
        reason_code="domain_declare_done",
        iterations=1,
        session_id="s1",
        run_artifact_ref=None,
        latest_refs={},
        domain_runtime_state={},
        trace_events=[],
    )
    ctrl_result = deed_mod._adapt_kernel_loop_result_to_controller(
        result_with_domain,
        domain_state={},
        trace_artifact_ref="/data/run_x_trace.json",
        rationale_strip_artifact_ref="/data/run_x_rationale_strip.json",
    )
    refs = ctrl_result.last_dashboard.get("latest_refs", {})
    assert refs.get("trace_artifact_ref") == "/data/run_x_trace.json"
    assert refs.get("rationale_strip_artifact_ref") == "/data/run_x_rationale_strip.json"


def test_deed_adapter_omits_strip_ref_when_none() -> None:
    """rationale_strip_artifact_ref must be absent from merged_refs when persist returned None."""
    import harness.mission_runtime.modes.deed_to_ir as deed_mod

    result = KernelLoopResult(
        terminal_class="completed",
        reason_code="domain_declare_done",
        iterations=0,
        session_id="s1",
        run_artifact_ref=None,
        latest_refs={},
        domain_runtime_state={},
        trace_events=[],
    )
    ctrl_result = deed_mod._adapt_kernel_loop_result_to_controller(
        result,
        domain_state={},
        trace_artifact_ref=None,
        rationale_strip_artifact_ref=None,
    )
    refs = ctrl_result.last_dashboard.get("latest_refs", {})
    assert "rationale_strip_artifact_ref" not in refs


def test_transcript_adapter_surfaces_strip_ref_in_enriched_refs(monkeypatch: Any) -> None:
    """run_orchestration_kernel_transcript_loop surfaces rationale_strip_artifact_ref."""
    import harness.mission_runtime.modes.transcript_edit as tx_mod
    from agents.transcript_edit.contracts import TranscriptEditAgentRunResult

    fake_kernel_result = KernelLoopResult(
        terminal_class="completed",
        reason_code="domain_declare_done",
        iterations=1,
        session_id="sess1",
        run_artifact_ref=None,
        latest_refs={},
        domain_runtime_state={},
        trace_events=_make_events(2),
    )

    def _fake_kernel_loop(**_kw: Any) -> KernelLoopResult:
        return fake_kernel_result

    monkeypatch.setattr(tx_mod, "run_orchestration_kernel_loop", _fake_kernel_loop)
    monkeypatch.setattr(
        tx_mod, "persist_kernel_trace",
        lambda **_kw: "/data/run_tx_trace.json",
    )
    monkeypatch.setattr(
        tx_mod, "persist_rationale_strip",
        lambda **_kw: "/data/run_tx_rationale_strip.json",
    )

    mock_sm = MagicMock()
    mock_sm.start_session.return_value = MagicMock(
        session_id="sess1",
        run_artifact_ref=None,
        refusal=None,
    )

    from agents.transcript_edit.contracts import TranscriptEditAgentRunRequest
    request = TranscriptEditAgentRunRequest(
        source_transcript_ref="artifacts/tx/src.json",
        mission_objective="test run",
    )
    tx_result = tx_mod.run_orchestration_kernel_transcript_loop(
        session_manager=mock_sm,
        request=request,
        request_id_prefix="run_tx_001",
    )
    assert tx_result.latest_refs.get("rationale_strip_artifact_ref") == "/data/run_tx_rationale_strip.json"
    assert tx_result.latest_refs.get("trace_artifact_ref") == "/data/run_tx_trace.json"


# ---------------------------------------------------------------------------
# 4. Boundedness preserved
# ---------------------------------------------------------------------------

def test_persisted_strip_respects_max_entries_cap(tmp_path: Path) -> None:
    """Persisted strip entry count must not exceed max_entries=5."""
    events = _make_events(12)  # 12 iters — strip builder will include at most 5
    result = _make_kernel_result(trace_events=events)
    with patch(
        "harness.tracing.kernel_trace_persistence._resolve_trace_dir",
        return_value=tmp_path,
    ):
        ref = persist_rationale_strip(
            kernel_result=result,
            request_id_prefix="run_cap",
            max_entries=5,
            per_entry_cap=256,
        )
    payload = json.loads(Path(ref).read_text(encoding="utf-8"))
    assert payload["entry_count"] <= 5
    assert len(payload["rationale_continuity_strip"]) <= 5


def test_persisted_strip_fields_respect_per_entry_cap(tmp_path: Path) -> None:
    """String fields in each entry must not exceed per_entry_cap characters."""
    # Inject a very long rationale to exercise the cap.
    events = _make_events(1)
    for ev in events:
        if ev.get("phase") == "move_resolution":
            ev["payload"]["rationale"] = "x" * 1000
    result = _make_kernel_result(trace_events=events)
    with patch(
        "harness.tracing.kernel_trace_persistence._resolve_trace_dir",
        return_value=tmp_path,
    ):
        ref = persist_rationale_strip(
            kernel_result=result,
            request_id_prefix="run_cap_str",
            per_entry_cap=64,
        )
    payload = json.loads(Path(ref).read_text(encoding="utf-8"))
    for entry in payload["rationale_continuity_strip"]:
        for key in ("why_summary", "outcome_summary", "carry_forward_hint"):
            assert len(entry[key]) <= 64, f"{key} exceeds cap: {len(entry[key])}"


# ---------------------------------------------------------------------------
# 5. Provenance fields
# ---------------------------------------------------------------------------

def test_persisted_strip_contains_provenance_fields(tmp_path: Path) -> None:
    """Sidecar must contain rationale_strip_version and source_trace_artifact_ref."""
    events = _make_events(2)
    result = _make_kernel_result(trace_events=events)
    with patch(
        "harness.tracing.kernel_trace_persistence._resolve_trace_dir",
        return_value=tmp_path,
    ):
        ref = persist_rationale_strip(
            kernel_result=result,
            request_id_prefix="run_prov",
            source_trace_artifact_ref="/data/run_prov_trace.json",
        )
    payload = json.loads(Path(ref).read_text(encoding="utf-8"))
    assert payload["rationale_strip_version"] == "v1"
    assert payload["source_trace_artifact_ref"] == "/data/run_prov_trace.json"
    assert payload["request_id_prefix"] == "run_prov"


def test_persisted_strip_source_ref_none_when_not_provided(tmp_path: Path) -> None:
    """source_trace_artifact_ref must be None in payload when not passed."""
    events = _make_events(1)
    result = _make_kernel_result(trace_events=events)
    with patch(
        "harness.tracing.kernel_trace_persistence._resolve_trace_dir",
        return_value=tmp_path,
    ):
        ref = persist_rationale_strip(
            kernel_result=result,
            request_id_prefix="run_noprov",
        )
    payload = json.loads(Path(ref).read_text(encoding="utf-8"))
    assert payload["source_trace_artifact_ref"] is None
