"""End-to-end harness trunk: trace → run summary → review bundle."""

from __future__ import annotations

import json
from pathlib import Path

from harness.review.tool import build_single_run_review_bundle
from harness.run_summary.build import (
    build_mission_flow_run_summary,
    build_orchestration_kernel_run_summary,
)
from harness.tracing.service import build_canonical_trace_from_payload

_FIXTURES = Path(__file__).resolve().parent / "test_fixtures" / "harness_regression_pack"


def _load(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def test_composition_orchestration_kernel_fixture() -> None:
    payload = _load("composition_orchestration_kernel.json")
    trace = build_canonical_trace_from_payload(payload=payload)
    assert trace.loop_family == "orchestration_kernel"
    assert trace.run_id == "run-comp-orch"
    assert trace.terminal.terminal_class == "completed"

    inner = payload["orchestration_kernel"]
    summary = build_orchestration_kernel_run_summary(orchestration_kernel_payload=inner)
    assert summary.loop_family == "orchestration_kernel"
    assert summary.run_id == "run-comp-orch"

    bundle = build_single_run_review_bundle(payload=payload)
    run0 = bundle["runs"][0]
    assert run0["trace"]["loop_family"] == "orchestration_kernel"
    assert run0["run_summary"]["loop_family"] == "orchestration_kernel"
    assert any(pe.get("pack_id") == "pack-comp" for pe in run0["prompt_events"])


def test_composition_mission_flow_fixture() -> None:
    payload = _load("composition_mission_flow.json")
    trace = build_canonical_trace_from_payload(payload=payload)
    assert trace.loop_family == "mission_flow"
    assert trace.run_id == "mission-comp-1"

    summary = build_mission_flow_run_summary(mission_flow_payload=payload)
    assert summary.loop_family == "mission_flow"
    assert summary.mission_state.opaque_payload.get("fixture_opaque") is True
    assert summary.terminal_summary.terminal_class == "completed"

    bundle = build_single_run_review_bundle(payload=payload)
    run0 = bundle["runs"][0]
    assert run0["trace"]["loop_family"] == "mission_flow"
    assert run0["run_summary"]["run_id"] == "mission-comp-1"
