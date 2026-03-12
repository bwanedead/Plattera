from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from harness.tracing.adapters.transcript_edit import (
    build_transcript_edit_trace,
    build_transcript_edit_trace_from_path,
)


def _ledger_snapshot(*, unresolved_count: int, mapping_blocking: int) -> dict:
    return {
        "items": [
            {
                "key": "range",
                "state": "verified" if unresolved_count == 0 else "disputed",
                "mapping_blocking": mapping_blocking > 0,
            }
        ],
        "summary": {
            "unresolved_count": unresolved_count,
            "mapping_blocking_unresolved_count": mapping_blocking,
        },
        "source_completeness": "partial_truncated" if unresolved_count > 0 else "complete",
    }


def _completed_run_entry() -> dict:
    return {
        "run_id": "tx_agent_1000_abcd",
        "status": "completed",
        "request": {
            "mode": "audit_then_repair_then_promote",
            "validation_mode": "off",
            "trigger": "manual",
            "dossier_id": "dossier-42",
        },
        "snapshot": {
            "run_id": "tx_agent_1000_abcd",
            "status": "completed",
            "reason_code": "tx_agent_transcript_clean_promoted",
            "iterations": 2,
            "session_id": "tx-agent-tx_agent_1000_abcd-kernel::tx-agent-tx_agent_1000_abcd-kernel-session-1",
            "run_artifact_ref": "artifact://tx-run-1",
            "latest_refs": {"tx_source_transcript_ref": {"artifact_path": "artifact://tx-source-1"}},
            "review_required": False,
            "progress_log": [
                {"timestamp_epoch_seconds": 100, "iteration": 0, "phase": "starting", "message": "starting"},
                {"timestamp_epoch_seconds": 101, "iteration": 1, "phase": "audit", "message": "audit"},
                {
                    "timestamp_epoch_seconds": 102,
                    "iteration": 1,
                    "phase": "audit_result",
                    "message": "audit result",
                    "detail": {"decision_ledger": _ledger_snapshot(unresolved_count=0, mapping_blocking=0)},
                },
                {
                    "timestamp_epoch_seconds": 103,
                    "iteration": 1,
                    "phase": "resolver_attempt",
                    "event_type": "resolver_attempt",
                    "message": "resolver attempt",
                    "detail": {"decision_key": "range"},
                },
                {
                    "timestamp_epoch_seconds": 104,
                    "iteration": 1,
                    "phase": "plan_result",
                    "message": "plan result",
                    "detail": {"op_count": 1, "plan_reason": "repair"},
                },
                {
                    "timestamp_epoch_seconds": 105,
                    "iteration": 1,
                    "phase": "apply_result",
                    "message": "apply result",
                    "execution_state": "running",
                    "detail": {"plan_op_count": 1},
                },
                {
                    "timestamp_epoch_seconds": 106,
                    "iteration": 2,
                    "phase": "image_verify_result",
                    "message": "verify result",
                    "detail": {"decision_ledger": _ledger_snapshot(unresolved_count=0, mapping_blocking=0)},
                },
            ],
            "critical_events": [
                {
                    "timestamp_epoch_seconds": 107,
                    "iteration": 2,
                    "phase": "ticket_integrated",
                    "event_type": "human_resolution_ticket",
                    "ticket_id": "ticket-001",
                    "decision_key": "range",
                    "lifecycle_state": "integrated",
                    "message": "ticket integrated",
                }
            ],
            "runtime_hitl_state": {
                "hitl_lifecycle_log": [],
                "blocker_registry": {
                    "updated_at": 106,
                    "rows": [],
                    "history": [],
                    "counts": {"total": 0},
                },
            },
            "terminal_summary": {
                "terminal_classification": "mapping_ready",
                "human_feedback_pending": False,
                "decision_ledger": _ledger_snapshot(unresolved_count=0, mapping_blocking=0),
            },
            "waiting_feedback": False,
            "resumable": False,
        },
    }


def _waiting_feedback_run_entry() -> dict:
    return {
        "run_id": "tx_agent_2000_wait",
        "status": "waiting_feedback",
        "request": {"mode": "audit_then_repair", "trigger": "manual"},
        "snapshot": {
            "run_id": "tx_agent_2000_wait",
            "status": "waiting_feedback",
            "reason_code": "tx_agent_closure_requirements_unresolved",
            "iterations": 3,
            "session_id": "tx-agent-wait-kernel::tx-agent-wait-kernel-session-1",
            "run_artifact_ref": "artifact://tx-run-wait",
            "progress_log": [
                {"timestamp_epoch_seconds": 200, "iteration": 0, "phase": "starting", "message": "starting"},
                {
                    "timestamp_epoch_seconds": 201,
                    "iteration": 3,
                    "phase": "human_feedback_needed",
                    "event_type": "human_feedback_needed",
                    "prompt_id": "hitl_range_3",
                    "message": "Need human range choice",
                },
                {
                    "timestamp_epoch_seconds": 202,
                    "iteration": 3,
                    "phase": "blocker_update",
                    "event_type": "blocker_update",
                    "message": "non-authoritative blocker update",
                    "detail": {"blocker_id": "blocker:non_authoritative"},
                },
            ],
            "critical_events": [
                {
                    "timestamp_epoch_seconds": 203,
                    "iteration": 3,
                    "phase": "human_feedback_prompt_superseded",
                    "event_type": "human_feedback_needed",
                    "prompt_id": "hitl_range_2",
                    "replacement_prompt_id": "hitl_range_3",
                    "message": "superseded",
                }
            ],
            "runtime_hitl_state": {
                "hitl_lifecycle_log": [
                    {
                        "timestamp_epoch_seconds": 204,
                        "iteration": 3,
                        "phase": "human_feedback_needed",
                        "prompt_id": "hitl_range_3",
                        "ticket_id": "ticket-range-3",
                        "decision_key": "range",
                        "lifecycle_state": "waiting_feedback",
                    }
                ],
                "blocker_registry": {
                    "updated_at": 204,
                    "rows": [
                        {
                            "blocker_id": "blocker:range",
                            "decision_key": "range",
                            "state": "waiting_feedback",
                            "feedback_status": "pending",
                            "linked_prompt_id": "hitl_range_3",
                            "linked_ticket_id": "ticket-range-3",
                            "updated_at": 204,
                            "last_transition_reason": "prompt_issued",
                        }
                    ],
                    "history": [
                        {
                            "timestamp_epoch_seconds": 204,
                            "iteration": 3,
                            "active_blocker_id": "blocker:range",
                            "prior_state": "open",
                            "new_state": "waiting_feedback",
                            "action_attempted": "request_hitl",
                            "result": "waiting_feedback",
                            "reason": "prompt_issued",
                        }
                    ],
                    "counts": {"waiting_feedback": 1, "total": 1},
                },
            },
            "terminal_summary": {
                "terminal_classification": "blocked_waiting_feedback",
                "human_feedback_pending": True,
                "decision_ledger": _ledger_snapshot(unresolved_count=1, mapping_blocking=1),
            },
            "waiting_feedback": True,
            "resumable": True,
        },
    }


def test_transcript_edit_adapter_normal_completion() -> None:
    trace = build_transcript_edit_trace(
        run_snapshot=_completed_run_entry(),
        snapshot_ref="state://tx_run_completed",
    )
    kinds = {event.event_kind for event in trace.events}
    assert "request_start" in kinds
    assert "iteration" in kinds
    assert "model_proposal" in kinds
    assert "tool_execution" in kinds
    assert "verification" in kinds
    assert "terminal_outcome" in kinds
    assert trace.terminal.terminal_class == "completed"
    assert trace.terminal.terminal_reason_code == "tx_agent_transcript_clean_promoted"


def test_transcript_edit_adapter_waiting_feedback_case() -> None:
    trace = build_transcript_edit_trace(
        run_snapshot=_waiting_feedback_run_entry(),
        snapshot_ref="state://tx_run_waiting",
    )
    hitl_events = [event for event in trace.events if event.event_kind == "hitl_escalation"]
    blocker_events = [event for event in trace.events if event.event_kind == "blocker_transition"]
    assert hitl_events
    assert any(event.payload.get("prompt_id") == "hitl_range_3" for event in hitl_events)
    assert blocker_events
    assert all(event.source_origin.kind in {"tx_blocker_registry_history", "tx_blocker_registry_rows"} for event in blocker_events)
    assert trace.terminal.terminal_class == "waiting_human"


def test_transcript_edit_adapter_partial_history_marking() -> None:
    run = _completed_run_entry()
    run["snapshot"]["progress_log"] = [
        {"timestamp_epoch_seconds": 100 + idx, "iteration": idx, "phase": "audit", "message": f"evt-{idx}"}
        for idx in range(40)
    ]
    run["snapshot"]["critical_events"] = [
        {"timestamp_epoch_seconds": 200 + idx, "iteration": idx, "phase": "audit_result", "message": f"crit-{idx}"}
        for idx in range(200)
    ]
    trace = build_transcript_edit_trace(run_snapshot=run)
    assert trace.completeness_status == "partial"
    assert "tx_progress_log_history" in trace.missing_components
    assert "tx_critical_events_history" in trace.missing_components
    assert "tx_progress_log_bounded" in trace.normalization_warnings
    assert "tx_critical_events_bounded" in trace.normalization_warnings


def test_transcript_edit_adapter_authority_closure_ledger_only() -> None:
    run = _waiting_feedback_run_entry()
    run["snapshot"]["terminal_summary"]["decision_ledger"] = {"summary": {"unresolved_count": 99}}
    run["snapshot"]["runtime_hitl_state"]["blocker_registry"]["rows"][0]["state"] = "resolved"
    trace = build_transcript_edit_trace(run_snapshot=run)
    closure_events = [
        event for event in trace.events if isinstance(event.payload.get("closure"), dict)
    ]
    assert closure_events
    assert all(event.payload["closure"].get("source") == "decision_ledger" for event in closure_events)
    blocker_events = [event for event in trace.events if event.event_kind == "blocker_transition"]
    assert any(event.payload.get("state") == "resolved" for event in blocker_events)


def test_transcript_edit_adapter_authority_missing_ledger_is_explicit_gap() -> None:
    run = _completed_run_entry()
    run["snapshot"]["progress_log"][2]["detail"] = {}
    run["snapshot"]["progress_log"][6]["detail"] = {}
    run["snapshot"]["terminal_summary"]["decision_ledger"] = {}
    run["snapshot"]["terminal_summary"]["terminal_classification"] = "mapping_ready"
    trace = build_transcript_edit_trace(run_snapshot=run)
    assert trace.completeness_status == "partial"
    assert "decision_ledger_closure_source" in trace.missing_components
    assert "decision_ledger_missing_for_closure_truth" in trace.normalization_warnings
    assert all("closure" not in event.payload for event in trace.events)
    assert "closure" not in trace.terminal.terminal_metadata


def test_transcript_edit_adapter_closure_is_event_local_not_terminal_backfilled() -> None:
    run = _completed_run_entry()
    run["snapshot"]["progress_log"][2]["detail"] = {}
    run["snapshot"]["terminal_summary"]["decision_ledger"] = _ledger_snapshot(unresolved_count=7, mapping_blocking=4)
    trace = build_transcript_edit_trace(run_snapshot=run)
    audit_result_event = next(
        event for event in trace.events if event.phase == "audit_result" and event.source_origin.kind == "tx_progress_log"
    )
    assert "closure" not in audit_result_event.payload
    terminal_event = next(event for event in trace.events if event.event_kind == "terminal_outcome")
    assert terminal_event.payload.get("closure", {}).get("source") == "decision_ledger"


def test_transcript_edit_adapter_terminal_prefers_terminal_summary_ledger() -> None:
    run = _completed_run_entry()
    run["snapshot"]["progress_log"][6]["detail"]["decision_ledger"] = _ledger_snapshot(unresolved_count=0, mapping_blocking=0)
    run["snapshot"]["terminal_summary"]["decision_ledger"] = _ledger_snapshot(unresolved_count=7, mapping_blocking=3)
    trace = build_transcript_edit_trace(run_snapshot=run)
    terminal_event = next(event for event in trace.events if event.event_kind == "terminal_outcome")
    assert terminal_event.payload.get("closure", {}).get("unresolved_count") == 7
    assert trace.terminal.terminal_metadata.get("closure", {}).get("unresolved_count") == 7


def test_transcript_edit_adapter_hitl_actor_semantics() -> None:
    run = _waiting_feedback_run_entry()
    run["snapshot"]["critical_events"].append(
        {
            "timestamp_epoch_seconds": 205,
            "iteration": 3,
            "phase": "human_feedback_received",
            "event_type": "human_feedback",
            "prompt_id": "hitl_range_3",
            "message": "feedback received",
        }
    )
    trace = build_transcript_edit_trace(run_snapshot=run)
    needed_event = next(
        event for event in trace.events if event.phase == "human_feedback_needed" and event.source_origin.kind == "tx_progress_log"
    )
    received_event = next(
        event
        for event in trace.events
        if event.phase == "human_feedback_received" and event.source_origin.kind == "tx_critical_events"
    )
    assert needed_event.actor == "harness"
    assert received_event.actor == "human"


def test_transcript_edit_adapter_provenance_distinguishes_sources() -> None:
    trace = build_transcript_edit_trace(
        run_snapshot=_waiting_feedback_run_entry(),
        snapshot_ref="state://tx_provenance",
    )
    kinds = {event.source_origin.kind for event in trace.events}
    assert "tx_progress_log" in kinds
    assert "tx_critical_events" in kinds
    assert "tx_blocker_registry_rows" in kinds
    assert "tx_blocker_registry_history" in kinds
    assert "tx_runtime_hitl_state" in kinds
    assert "tx_terminal_summary" in kinds
    blocker_row_event = next(event for event in trace.events if event.source_origin.kind == "tx_blocker_registry_rows")
    assert blocker_row_event.payload.get("blocker_id") == "blocker:range"
    hitl_event = next(event for event in trace.events if event.source_origin.kind == "tx_runtime_hitl_state")
    assert hitl_event.payload.get("prompt_id") == "hitl_range_3"
    assert hitl_event.payload.get("ticket_id") == "ticket-range-3"


def test_transcript_edit_adapter_determinism() -> None:
    run = _waiting_feedback_run_entry()
    trace_a = build_transcript_edit_trace(run_snapshot=copy.deepcopy(run), snapshot_ref="state://tx_det")
    trace_b = build_transcript_edit_trace(run_snapshot=copy.deepcopy(run), snapshot_ref="state://tx_det")
    assert [event.event_id for event in trace_a.events] == [event.event_id for event in trace_b.events]
    assert [event.event_index for event in trace_a.events] == [event.event_index for event in trace_b.events]
    assert json.dumps(trace_a.model_dump(mode="json"), sort_keys=True) == json.dumps(
        trace_b.model_dump(mode="json"), sort_keys=True
    )


def test_transcript_edit_adapter_path_loader(tmp_path: Path) -> None:
    path = tmp_path / "tx_run_snapshot.json"
    path.write_text(json.dumps(_completed_run_entry()), encoding="utf-8")
    trace = build_transcript_edit_trace_from_path(snapshot_path=str(path))
    assert trace.loop_family == "transcript_edit"
    assert trace.run_id == "tx_agent_1000_abcd"
