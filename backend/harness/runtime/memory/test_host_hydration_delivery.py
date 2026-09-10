"""MAPDEP-BR-027: bounded host hydration result transport."""

from __future__ import annotations

from typing import Any

from harness.execution.agent_result_view import (
    MAX_AGENT_RESULT_VIEW_CHARS,
    AgentResultView,
    AgentResultViewOmission,
    OMISSION_REASON_NOT_JSON_SAFE,
    agent_result_view_to_wire,
    build_agent_result_view,
    measure_agent_result_view_chars,
)
from harness.execution.contracts import (
    ActionDispatchResult,
    ExecutionDashboard,
    ExecutionLatestRefs,
    ExecutionState,
    ExecutionStepRequest,
    ExecutionStepResult,
    SessionExecutionRecord,
)
from harness.runtime.memory.host_hydration_delivery import (
    HOST_HYDRATION_DELIVERY_SCHEMA_VERSION,
    MAX_HOST_HYDRATION_PROMPT_CHARS,
    apply_combined_hydration_lane_budget,
    attach_hydration_result_representation,
    measure_framed_hydration_prompt_chars,
    project_oneshot_hydration_for_prompt,
    project_pinned_hydration_for_prompt,
    validate_stored_oneshot_hydration_record,
    validate_stored_pinned_hydration_record,
)
from harness.runtime.memory.result_delivery import (
    admit_pending_result_delivery,
    project_latest_action_results,
)
from harness.runtime.memory.result_representation import (
    REASON_LANE_BUDGET,
    REASON_MISSING_VIEW,
    REPRESENTATION_AGENT_RESULT_VIEW,
    REPRESENTATION_EXACT_OUTPUTS,
    REPRESENTATION_UNAVAILABLE,
    measure_compact_json_chars,
    select_result_representation,
)


def _dashboard() -> ExecutionDashboard:
    return ExecutionDashboard(
        latest_refs=ExecutionLatestRefs(refs={}),
        budgets_remaining={},
        last_refusal=None,
    )


def _hydrate_step(
    *,
    outputs: dict[str, Any],
    agent_result_view: AgentResultView | None = None,
    agent_result_view_omitted: AgentResultViewOmission | None = None,
    image_evidence: tuple[dict[str, Any], ...] = (),
) -> ExecutionStepResult:
    request = ExecutionStepRequest(session_id="s", action_id="hydrate_artifact_refs")
    result = ActionDispatchResult(
        action_id="hydrate_artifact_refs",
        executed=True,
        outputs=outputs,
        agent_result_view=agent_result_view,
        agent_result_view_omitted=agent_result_view_omitted,
        image_evidence=image_evidence,
    )
    record = SessionExecutionRecord(session_id="s", run_id="r", request=request, result=result)
    return ExecutionStepResult(
        session_id="s",
        idempotency_key="",
        execution_state=ExecutionState.EXECUTED,
        dashboard=_dashboard(),
        record=record,
    )


def test_small_oneshot_hydration_remains_exact() -> None:
    record: dict[str, Any] = {"resolved_refs": ["r-1"]}
    step = _hydrate_step(outputs={"results": [{"ref_id": "r-1", "kind": "stub"}], "errors": []})
    attach_hydration_result_representation(record, step)
    assert record["schema_version"] == HOST_HYDRATION_DELIVERY_SCHEMA_VERSION
    assert record["result_representation"]["representation_kind"] == REPRESENTATION_EXACT_OUTPUTS
    assert "hydrated_results" not in record
    prompt = project_oneshot_hydration_for_prompt(
        {
            "source_turn_index": 1,
            "requested_refs": ["r-1"],
            "resolved_refs": ["r-1"],
            "result_representation": record["result_representation"],
        }
    )
    assert prompt is not None
    assert prompt["result_representation"]["representation_kind"] == REPRESENTATION_EXACT_OUTPUTS
    assert "hydrated_results" not in prompt


def test_small_pinned_hydration_remains_exact() -> None:
    record: dict[str, Any] = {"refs": ["pin-1"]}
    step = _hydrate_step(outputs={"results": [{"ref_id": "pin-1"}], "errors": []})
    attach_hydration_result_representation(record, step)
    assert record["result_representation"]["representation_kind"] == REPRESENTATION_EXACT_OUTPUTS
    prompt = project_pinned_hydration_for_prompt(record)
    assert prompt is not None
    assert prompt["result_representation"]["representation_kind"] == REPRESENTATION_EXACT_OUTPUTS


def test_oversized_hydration_uses_provider_view_without_continuity_key() -> None:
    big_payload = "x" * (MAX_AGENT_RESULT_VIEW_CHARS + 500)
    outputs = {"results": [{"ref_id": "tx", "kind": "transcript", "payload": {"text": big_payload}}], "errors": []}
    view = AgentResultView(
        schema_version="agent_result_view.v1",
        schema_id="transcript_edit.hydrate_artifact_refs.v1",
        payload={"results": [{"ref_id": "tx", "kind": "transcript", "summary": "bounded"}]},
        continuity_key="hydrate:tx",
    )
    record: dict[str, Any] = {}
    attach_hydration_result_representation(record, _hydrate_step(outputs=outputs, agent_result_view=view))
    rr = record["result_representation"]
    assert rr["representation_kind"] == REPRESENTATION_AGENT_RESULT_VIEW
    assert rr["representation"]["continuity_key"] == "hydrate:tx"
    prompt = project_oneshot_hydration_for_prompt(
        {
            "source_turn_index": 2,
            "requested_refs": ["tx"],
            "resolved_refs": ["tx"],
            "result_representation": rr,
        }
    )
    assert prompt is not None
    projected = prompt["result_representation"]["representation"]
    assert "continuity_key" not in projected
    assert projected["schema_id"] == "transcript_edit.hydrate_artifact_refs.v1"


def test_dossier_shaped_hydration_uses_same_generic_path() -> None:
    """Harness must not branch on dossier/transcript action IDs — only outputs+view."""
    big = "y" * (MAX_AGENT_RESULT_VIEW_CHARS + 200)
    outputs = {
        "results": [{"ref_id": "dossier:seg:1", "kind": "dossier_segment", "payload": {"body": big}}],
        "errors": [],
    }
    view = AgentResultView(
        schema_version="agent_result_view.v1",
        schema_id="deed_to_ir.hydrate_artifact_refs.v1",
        payload={"results": [{"ref_id": "dossier:seg:1", "omitted": True}]},
        continuity_key=None,
    )
    kind, representation = select_result_representation(outputs=outputs, view=view, view_omission=None)
    assert kind == REPRESENTATION_AGENT_RESULT_VIEW
    assert representation["schema_id"] == "deed_to_ir.hydrate_artifact_refs.v1"


def test_oversized_without_view_is_unavailable_never_prefix() -> None:
    big = "z" * (MAX_AGENT_RESULT_VIEW_CHARS + 100)
    outputs = {"results": [{"payload": big}], "errors": []}
    kind, representation = select_result_representation(outputs=outputs, view=None, view_omission=None)
    assert kind == REPRESENTATION_UNAVAILABLE
    assert representation["reason"] == REASON_MISSING_VIEW
    assert big not in str(representation)


def test_invalid_non_json_safe_view_fails_closed() -> None:
    outputs = {"results": [{"payload": "x" * (MAX_AGENT_RESULT_VIEW_CHARS + 50)}], "errors": []}
    omission = AgentResultViewOmission(reason=OMISSION_REASON_NOT_JSON_SAFE)
    kind, representation = select_result_representation(
        outputs=outputs, view=None, view_omission=omission
    )
    assert kind == REPRESENTATION_UNAVAILABLE
    assert representation["reason"] == "invalid_agent_result_view"
    assert representation["view_omission"]["reason"] == OMISSION_REASON_NOT_JSON_SAFE


def test_combined_lane_budget_prefers_oneshot_and_marks_lane_budget() -> None:
    oneshot_view = _near_cap_provider_view(schema_id="oneshot.hydrate.v1", continuity_key="c:one")
    pinned_view = _near_cap_provider_view(schema_id="pinned.hydrate.v1", continuity_key="c:pin")
    oneshot = {
        "source_turn_index": 1,
        "requested_refs": ["one"],
        "resolved_refs": ["one"],
        "result_representation": {
            "representation_kind": REPRESENTATION_AGENT_RESULT_VIEW,
            "representation": agent_result_view_to_wire(oneshot_view),
        },
    }
    pinned = {
        "refs": ["pin"],
        "status": "surfaced",
        "result_representation": {
            "representation_kind": REPRESENTATION_AGENT_RESULT_VIEW,
            "representation": agent_result_view_to_wire(pinned_view),
        },
    }
    oneshot_prompt = project_oneshot_hydration_for_prompt(oneshot)
    pinned_prompt = project_pinned_hydration_for_prompt(pinned)
    assert oneshot_prompt is not None and pinned_prompt is not None
    assert (
        measure_framed_hydration_prompt_chars(oneshot_prompt, pinned_prompt)
        > MAX_HOST_HYDRATION_PROMPT_CHARS
    )

    out_one, out_pin = apply_combined_hydration_lane_budget(
        oneshot=oneshot_prompt, pinned=pinned_prompt
    )
    assert out_one is not None and out_pin is not None
    assert out_one["result_representation"]["representation_kind"] == REPRESENTATION_AGENT_RESULT_VIEW
    assert "continuity_key" not in out_one["result_representation"]["representation"]
    assert out_one["resolved_refs"] == ["one"]
    assert out_pin["refs"] == ["pin"]
    assert out_pin["result_representation"]["representation_kind"] == REPRESENTATION_UNAVAILABLE
    assert out_pin["result_representation"]["representation"]["reason"] == REASON_LANE_BUDGET
    framed = measure_framed_hydration_prompt_chars(out_one, out_pin)
    assert framed <= MAX_HOST_HYDRATION_PROMPT_CHARS


def _near_cap_provider_view(*, schema_id: str, continuity_key: str | None = None) -> AgentResultView:
    overhead = measure_agent_result_view_chars(
        {
            "schema_version": "agent_result_view.v1",
            "schema_id": schema_id,
            "payload": {"pad": ""},
            **({"continuity_key": continuity_key} if continuity_key else {}),
        }
    )
    pad_len = MAX_AGENT_RESULT_VIEW_CHARS - overhead
    assert pad_len > 1000
    view, omitted = build_agent_result_view(
        schema_id=schema_id,
        payload={"pad": "v" * pad_len},
        continuity_key=continuity_key,
    )
    assert omitted is None and view is not None
    wire = agent_result_view_to_wire(view)
    assert measure_agent_result_view_chars(wire) == MAX_AGENT_RESULT_VIEW_CHARS
    return view


def test_lane_budget_is_not_content_exposure() -> None:
    pinned = {
        "refs": ["pin"],
        "status": "surfaced",
        "result_representation": {
            "representation_kind": REPRESENTATION_UNAVAILABLE,
            "representation": {"reason": REASON_LANE_BUDGET},
        },
    }
    prompt = project_pinned_hydration_for_prompt(pinned)
    assert prompt is not None
    assert prompt["refs"] == ["pin"]
    assert prompt["result_representation"]["representation"]["reason"] == REASON_LANE_BUDGET


def test_path_bearing_errors_cannot_escape_lane_or_resume() -> None:
    record: dict = {}
    step = _hydrate_step(
        outputs={
            "results": [{"ref_id": "r-1", "kind": "stub"}],
            "errors": [
                {
                    "reason_code": "not_found",
                    "absolute_path": "C:/secret/file.json",
                    "b64": "ZmFrZQ==",
                    "message": "x" * 5000,
                    "path": "/tmp/host",
                }
            ],
        }
    )
    attach_hydration_result_representation(record, step)
    blob = measure_compact_json_chars(record)
    assert "C:/secret" not in str(record)
    assert "ZmFrZQ==" not in str(record)
    assert "/tmp/host" not in str(record)
    assert record["hydration_errors"][0]["reason_code"] == "not_found"
    assert record["hydration_errors"][0]["message_omitted"] is True
    assert "fields_omitted_count" in record["hydration_errors"][0]

    # Malformed resume with raw path-bearing errors refuses.
    bad = {
        "schema_version": HOST_HYDRATION_DELIVERY_SCHEMA_VERSION,
        "source_turn_index": 1,
        "requested_refs": ["r-1"],
        "resolved_refs": ["r-1"],
        "errors": [],
        "hydration_errors": [{"reason_code": "x", "absolute_path": "/bad"}],
        "status": "surfaced",
        "surfaced_iteration": 2,
        "result_representation": None,
    }
    assert validate_stored_oneshot_hydration_record(bad) is None
    assert blob > 0


def test_metadata_only_pressure_cannot_exceed_framed_cap() -> None:
    huge_errors = [{"reason_code": f"code_{i}", "message": "m" * 300} for i in range(40)]
    oneshot = project_oneshot_hydration_for_prompt(
        {
            "source_turn_index": 1,
            "requested_refs": [f"ref:{i}" for i in range(32)],
            "resolved_refs": [f"ref:{i}" for i in range(32)],
            "reason": "r" * 400,
            "errors": huge_errors,
            "hydration_errors": huge_errors,
            "result_representation": {
                "representation_kind": REPRESENTATION_AGENT_RESULT_VIEW,
                "representation": agent_result_view_to_wire(
                    _near_cap_provider_view(schema_id="meta.oneshot.v1")
                ),
            },
        }
    )
    pinned = project_pinned_hydration_for_prompt(
        {
            "refs": [f"pin:{i}" for i in range(32)],
            "status": "surfaced",
            "hydration_errors": huge_errors,
            "result_representation": {
                "representation_kind": REPRESENTATION_AGENT_RESULT_VIEW,
                "representation": agent_result_view_to_wire(
                    _near_cap_provider_view(schema_id="meta.pinned.v1")
                ),
            },
        }
    )
    out_one, out_pin = apply_combined_hydration_lane_budget(oneshot=oneshot, pinned=pinned)
    framed = measure_framed_hydration_prompt_chars(out_one, out_pin)
    assert framed <= MAX_HOST_HYDRATION_PROMPT_CHARS
    if out_one is not None:
        assert "absolute_path" not in str(out_one)
        assert out_one.get("requested_refs") is not None or out_one.get("requested_refs_omitted_count")


def test_small_leaf_with_absolute_path_uses_provider_view() -> None:
    outputs = {
        "results": [
            {
                "ref_id": "image:1",
                "kind": "derived_image",
                "absolute_path": "C:/data/x.png",
                "b64": "ZmFrZQ==",
            }
        ],
        "errors": [],
    }
    view = AgentResultView(
        schema_version="agent_result_view.v1",
        schema_id="generic.hydrate.v1",
        payload={"results": [{"ref_id": "image:1", "kind": "derived_image"}]},
    )
    record: dict = {}
    attach_hydration_result_representation(
        record, _hydrate_step(outputs=outputs, agent_result_view=view)
    )
    assert record["result_representation"]["representation_kind"] == REPRESENTATION_AGENT_RESULT_VIEW
    assert "absolute_path" not in str(record["result_representation"])
    assert "ZmFrZQ==" not in str(record["result_representation"])


def test_small_leaf_with_absolute_path_without_view_is_unavailable() -> None:
    outputs = {
        "results": [{"ref_id": "leaf", "absolute_path": "/tmp/x", "payload": {"ok": True}}],
        "errors": [],
    }
    record: dict = {}
    attach_hydration_result_representation(record, _hydrate_step(outputs=outputs))
    assert record["result_representation"]["representation_kind"] == REPRESENTATION_UNAVAILABLE
    assert record["result_representation"]["representation"]["reason"] == REASON_MISSING_VIEW
    assert "/tmp/x" not in str(record["result_representation"])


def test_final_prompt_body_measurement_uses_lane_keys() -> None:
    oneshot_view = _near_cap_provider_view(schema_id="body.oneshot.v1")
    pinned_view = _near_cap_provider_view(schema_id="body.pinned.v1")
    oneshot = project_oneshot_hydration_for_prompt(
        {
            "source_turn_index": 9,
            "requested_refs": ["a"],
            "resolved_refs": ["a"],
            "result_representation": {
                "representation_kind": REPRESENTATION_AGENT_RESULT_VIEW,
                "representation": agent_result_view_to_wire(oneshot_view),
            },
        }
    )
    pinned = project_pinned_hydration_for_prompt(
        {
            "refs": ["b"],
            "status": "surfaced",
            "result_representation": {
                "representation_kind": REPRESENTATION_AGENT_RESULT_VIEW,
                "representation": agent_result_view_to_wire(pinned_view),
            },
        }
    )
    out_one, out_pin = apply_combined_hydration_lane_budget(oneshot=oneshot, pinned=pinned)
    fragment: dict = {}
    if out_one is not None:
        fragment["agent_requested_hydration"] = out_one
    if out_pin is not None:
        fragment["pinned_refs_hydration"] = out_pin
    assert measure_compact_json_chars(fragment) <= MAX_HOST_HYDRATION_PROMPT_CHARS
    assert measure_framed_hydration_prompt_chars(out_one, out_pin) == measure_compact_json_chars(
        fragment
    )


def test_image_evidence_still_attached_when_json_uses_view() -> None:
    big = "i" * (MAX_AGENT_RESULT_VIEW_CHARS + 100)
    outputs = {"results": [{"ref_id": "image:1", "kind": "derived_image", "meta": big}], "errors": []}
    view = AgentResultView(
        schema_version="agent_result_view.v1",
        schema_id="generic.hydrate.v1",
        payload={"results": [{"ref_id": "image:1", "kind": "derived_image"}]},
    )
    evidence = ({"ref_id": "image:1", "b64": "ZmFrZQ==", "media_type": "image/png"},)
    step = _hydrate_step(outputs=outputs, agent_result_view=view, image_evidence=evidence)
    assert step.record is not None
    assert step.record.result.image_evidence == evidence
    record: dict[str, Any] = {}
    attach_hydration_result_representation(record, step)
    assert record["result_representation"]["representation_kind"] == REPRESENTATION_AGENT_RESULT_VIEW
    # Representation must not embed base64/host paths.
    assert "ZmFrZQ==" not in str(record["result_representation"])
    assert "/tmp" not in str(record["result_representation"])


def test_resume_round_trips_canonical_record() -> None:
    row = {
        "schema_version": HOST_HYDRATION_DELIVERY_SCHEMA_VERSION,
        "source_turn_index": 3,
        "requested_refs": ["r-1"],
        "resolved_refs": ["r-1"],
        "reason": None,
        "errors": [],
        "result_representation": {
            "representation_kind": REPRESENTATION_EXACT_OUTPUTS,
            "representation": {"results": [{"ref_id": "r-1"}], "errors": []},
        },
        "hydration_errors": None,
        "status": "surfaced",
        "surfaced_iteration": 4,
    }
    out = validate_stored_oneshot_hydration_record(row)
    assert out == row


def test_legacy_raw_records_canonicalize_once() -> None:
    legacy = {
        "source_turn_index": 3,
        "requested_refs": ["r-1"],
        "resolved_refs": ["r-1"],
        "reason": None,
        "errors": [],
        "hydrated_results": [{"ref_id": "r-1", "kind": "stub", "payload": {}}],
        "hydration_errors": None,
        "status": "surfaced",
        "surfaced_iteration": 4,
    }
    out = validate_stored_oneshot_hydration_record(legacy)
    assert out is not None
    assert "hydrated_results" not in out
    assert out["schema_version"] == HOST_HYDRATION_DELIVERY_SCHEMA_VERSION
    assert out["result_representation"]["representation_kind"] == REPRESENTATION_EXACT_OUTPUTS
    prompt = project_oneshot_hydration_for_prompt(out)
    assert prompt is not None
    assert "hydrated_results" not in prompt


def test_malformed_resume_records_refuse() -> None:
    assert validate_stored_oneshot_hydration_record({"status": "pending"}) is None
    assert (
        validate_stored_oneshot_hydration_record(
            {
                "schema_version": HOST_HYDRATION_DELIVERY_SCHEMA_VERSION,
                "source_turn_index": "3",
                "requested_refs": [],
                "resolved_refs": [],
                "status": "pending",
            }
        )
        is None
    )
    assert (
        validate_stored_pinned_hydration_record(
            {
                "schema_version": HOST_HYDRATION_DELIVERY_SCHEMA_VERSION,
                "refs": ["a"],
                "status": "surfaced",
                "result_representation": {
                    "representation_kind": REPRESENTATION_EXACT_OUTPUTS,
                    "representation": "not-a-dict",
                },
            }
        )
        is None
    )
    assert (
        validate_stored_oneshot_hydration_record(
            {
                "schema_version": HOST_HYDRATION_DELIVERY_SCHEMA_VERSION,
                "source_turn_index": 1,
                "requested_refs": ["r"],
                "resolved_refs": ["r"],
                "errors": [{"reason_code": "ok", "absolute_path": "/x"}],
                "status": "pending",
                "result_representation": None,
            }
        )
        is None
    )
    assert (
        validate_stored_oneshot_hydration_record(
            {
                "schema_version": HOST_HYDRATION_DELIVERY_SCHEMA_VERSION,
                "source_turn_index": 1,
                "requested_refs": ["r"],
                "resolved_refs": ["r"],
                "errors": [],
                "status": "surfaced",
                "surfaced_iteration": 2,
                "result_representation": {
                    "representation_kind": REPRESENTATION_EXACT_OUTPUTS,
                    "representation": {"results": [{"absolute_path": "/x"}]},
                },
            }
        )
        is None
    )


def test_oneshot_priority_retains_provider_view_when_errors_and_pinned_pressure() -> None:
    """Near-cap one-shot view + large errors + pinned content keeps the one-shot view."""
    oneshot_view = _near_cap_provider_view(schema_id="priority.oneshot.v1", continuity_key="c:p")
    pinned_view = _near_cap_provider_view(schema_id="priority.pinned.v1")
    huge_errors = [{"reason_code": f"err_{i}", "message": "m" * 350} for i in range(20)]
    oneshot = project_oneshot_hydration_for_prompt(
        {
            "source_turn_index": 3,
            "requested_refs": ["need-this"],
            "resolved_refs": ["need-this"],
            "errors": huge_errors,
            "hydration_errors": huge_errors,
            "result_representation": {
                "representation_kind": REPRESENTATION_AGENT_RESULT_VIEW,
                "representation": agent_result_view_to_wire(oneshot_view),
            },
        }
    )
    pinned = project_pinned_hydration_for_prompt(
        {
            "refs": ["pin-heavy"],
            "status": "surfaced",
            "hydration_errors": huge_errors,
            "result_representation": {
                "representation_kind": REPRESENTATION_AGENT_RESULT_VIEW,
                "representation": agent_result_view_to_wire(pinned_view),
            },
        }
    )
    assert oneshot is not None and pinned is not None
    assert (
        measure_framed_hydration_prompt_chars(oneshot, pinned) > MAX_HOST_HYDRATION_PROMPT_CHARS
    )
    out_one, out_pin = apply_combined_hydration_lane_budget(oneshot=oneshot, pinned=pinned)
    assert out_one is not None
    assert out_one["result_representation"]["representation_kind"] == REPRESENTATION_AGENT_RESULT_VIEW
    assert out_one["result_representation"]["representation"]["schema_id"] == "priority.oneshot.v1"
    assert "continuity_key" not in out_one["result_representation"]["representation"]
    assert measure_framed_hydration_prompt_chars(out_one, out_pin) <= MAX_HOST_HYDRATION_PROMPT_CHARS


def test_resume_rejects_contradictory_status_and_incomplete_omission_pairs() -> None:
    base_pending = {
        "schema_version": HOST_HYDRATION_DELIVERY_SCHEMA_VERSION,
        "source_turn_index": 1,
        "requested_refs": ["r"],
        "resolved_refs": ["r"],
        "errors": [],
        "status": "pending",
        "surfaced_iteration": None,
        "result_representation": None,
        "hydration_errors": None,
    }
    assert validate_stored_oneshot_hydration_record(base_pending) is not None

    pending_with_iteration = dict(base_pending)
    pending_with_iteration["surfaced_iteration"] = 2
    assert validate_stored_oneshot_hydration_record(pending_with_iteration) is None

    pending_with_rr = dict(base_pending)
    pending_with_rr["result_representation"] = {
        "representation_kind": REPRESENTATION_EXACT_OUTPUTS,
        "representation": {"ok": True},
    }
    assert validate_stored_oneshot_hydration_record(pending_with_rr) is None

    pending_with_hyd_errors = dict(base_pending)
    pending_with_hyd_errors["hydration_errors"] = [{"reason_code": "x"}]
    assert validate_stored_oneshot_hydration_record(pending_with_hyd_errors) is None

    surfaced_empty = {
        "schema_version": HOST_HYDRATION_DELIVERY_SCHEMA_VERSION,
        "source_turn_index": 1,
        "requested_refs": ["r"],
        "resolved_refs": ["r"],
        "errors": [],
        "status": "surfaced",
        "surfaced_iteration": 2,
        "result_representation": None,
        "hydration_errors": None,
    }
    assert validate_stored_oneshot_hydration_record(surfaced_empty) is None

    surfaced_no_iteration = {
        "schema_version": HOST_HYDRATION_DELIVERY_SCHEMA_VERSION,
        "source_turn_index": 1,
        "requested_refs": ["r"],
        "resolved_refs": ["r"],
        "errors": [{"reason_code": "placeholder_not_found"}],
        "status": "surfaced",
        "surfaced_iteration": None,
        "result_representation": None,
        "hydration_errors": None,
    }
    assert validate_stored_oneshot_hydration_record(surfaced_no_iteration) is None

    assert (
        validate_stored_pinned_hydration_record(
            {
                "schema_version": HOST_HYDRATION_DELIVERY_SCHEMA_VERSION,
                "refs": ["p"],
                "status": "pending",
                "surfaced_iteration": None,
                "result_representation": None,
                "hydration_errors": [],
            }
        )
        is None
    )

    incomplete_message = {
        "schema_version": HOST_HYDRATION_DELIVERY_SCHEMA_VERSION,
        "source_turn_index": 1,
        "requested_refs": ["r"],
        "resolved_refs": ["r"],
        "errors": [{"reason_code": "x", "message_omitted": True}],
        "status": "pending",
        "surfaced_iteration": None,
        "result_representation": None,
        "hydration_errors": None,
    }
    assert validate_stored_oneshot_hydration_record(incomplete_message) is None

    incomplete_hint = {
        "schema_version": HOST_HYDRATION_DELIVERY_SCHEMA_VERSION,
        "source_turn_index": 1,
        "requested_refs": ["r"],
        "resolved_refs": ["r"],
        "errors": [{"reason_code": "x", "hint_chars": 12}],
        "status": "pending",
        "surfaced_iteration": None,
        "result_representation": None,
        "hydration_errors": None,
    }
    assert validate_stored_oneshot_hydration_record(incomplete_hint) is None

    zero_omission = dict(base_pending)
    zero_omission["errors_omitted_count"] = 0
    assert validate_stored_oneshot_hydration_record(zero_omission) is None


def test_malformed_reason_code_increments_omission_accounting() -> None:
    from harness.runtime.memory.host_hydration_errors import project_hydration_error_lane

    rows, omitted = project_hydration_error_lane(
        [{"reason_code": 123, "requested_ref": "r-1"}, "   ", {"not": "a reason"}]
    )
    assert omitted >= 1 or any(r.get("fields_omitted_count", 0) > 0 for r in rows)
    replaced = [r for r in rows if r.get("reason_code") == "hydration_error"]
    assert replaced
    assert any(r.get("fields_omitted_count", 0) >= 1 for r in replaced)


def test_oneshot_prompt_preserves_hydration_errors_omitted_when_rows_empty() -> None:
    prompt = project_oneshot_hydration_for_prompt(
        {
            "source_turn_index": 4,
            "requested_refs": ["r-1"],
            "resolved_refs": ["r-1"],
            "errors": [],
            "hydration_errors": [],
            "hydration_errors_omitted_count": 3,
            "result_representation": {
                "representation_kind": REPRESENTATION_UNAVAILABLE,
                "representation": {"reason": REASON_MISSING_VIEW},
            },
        }
    )
    assert prompt is not None
    assert "hydration_errors" not in prompt
    assert prompt["hydration_errors_omitted_count"] == 3


def test_pinned_prompt_preserves_hydration_errors_omitted_when_rows_empty() -> None:
    prompt = project_pinned_hydration_for_prompt(
        {
            "refs": ["pin-1"],
            "status": "surfaced",
            "hydration_errors": [],
            "hydration_errors_omitted_count": 5,
            "result_representation": {
                "representation_kind": REPRESENTATION_UNAVAILABLE,
                "representation": {"reason": REASON_MISSING_VIEW},
            },
        }
    )
    assert prompt is not None
    assert "hydration_errors" not in prompt
    assert prompt["hydration_errors_omitted_count"] == 5


def test_all_omitted_hydration_errors_retain_accounting_through_attach_and_prompt() -> None:
    """Production-shaped: every source error row omitted by sanitization still surfaces the count."""
    record: dict[str, Any] = {
        "schema_version": HOST_HYDRATION_DELIVERY_SCHEMA_VERSION,
        "source_turn_index": 2,
        "requested_refs": ["artifact:x"],
        "resolved_refs": ["artifact:x"],
        "errors": [],
        "status": "surfaced",
        "surfaced_iteration": 3,
    }
    # Whitespace / empty bare strings project to None → row omission (no invented rows).
    unusable_errors = ["", "   ", "\t", "\n", "  "]
    step = _hydrate_step(
        outputs={
            "results": [{"ref_id": "artifact:x", "kind": "stub", "ok": True}],
            "errors": unusable_errors,
        }
    )
    attach_hydration_result_representation(record, step)
    assert record.get("hydration_errors") == []
    assert record.get("hydration_errors_omitted_count") == len(unusable_errors)

    oneshot_prompt = project_oneshot_hydration_for_prompt(record)
    assert oneshot_prompt is not None
    assert "hydration_errors" not in oneshot_prompt
    assert oneshot_prompt["hydration_errors_omitted_count"] == len(unusable_errors)

    pinned_prompt = project_pinned_hydration_for_prompt(
        {
            "refs": ["artifact:x"],
            "status": "surfaced",
            "hydration_errors": record["hydration_errors"],
            "hydration_errors_omitted_count": record["hydration_errors_omitted_count"],
            "result_representation": record.get("result_representation"),
        }
    )
    assert pinned_prompt is not None
    assert "hydration_errors" not in pinned_prompt
    assert pinned_prompt["hydration_errors_omitted_count"] == len(unusable_errors)


def test_latest_action_results_behavior_unchanged_for_small_admit() -> None:
    deliveries: list[dict[str, Any]] = []
    result = ActionDispatchResult(
        action_id="save_workspace_artifact",
        executed=True,
        outputs={"ok": True, "revision_ref": "rev:1"},
    )
    outcome = admit_pending_result_delivery(
        deliveries,
        result=result,
        source_turn_index=1,
        action_index=0,
        action_alias="save",
        execution_state="executed",
    )
    assert outcome.status == "admitted"
    proj = project_latest_action_results(deliveries)
    assert len(proj.latest_action_results) == 1
    assert proj.latest_action_results[0]["representation_kind"] == REPRESENTATION_EXACT_OUTPUTS


def test_no_domain_imports_in_generic_hydration_modules() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    owners = [
        root / "runtime" / "memory" / "result_representation.py",
        root / "runtime" / "memory" / "host_hydration_delivery.py",
        root / "runtime" / "orchestration" / "hydrate_next_hooks.py",
        root / "runtime" / "orchestration" / "pinned_refs_hooks.py",
        root / "runtime" / "orchestration" / "prompt_packet_builder.py",
    ]
    banned = ("tooling.mapping.transcript_edit", "tooling.mapping.deed_to_ir", "domains.mapping")
    for path in owners:
        text = path.read_text(encoding="utf-8")
        for token in banned:
            assert token not in text, f"{path} contains {token}"
