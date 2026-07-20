"""Coverage for deed-to-IR hydrate_artifact_refs AgentResultView (BR-026)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from domains.mapping.deed_to_ir.execution.artifact_hydration_result_views import (
    SCHEMA_HYDRATE_ARTIFACT_REFS,
    build_hydrate_artifact_refs_view,
)
from domains.mapping.deed_to_ir.execution.result_view_common import (
    build_working_head_continuity_key,
)
from domains.mapping.deed_to_ir.execution.result_views import (
    SCHEMA_SAVE_IR_ARTIFACT,
    attach_deed_to_ir_result_view,
    wrap_handler_with_result_view,
)
from harness.execution.agent_result_view import (
    MAX_AGENT_RESULT_VIEW_CHARS,
    agent_result_view_to_wire,
    measure_agent_result_view_chars,
    normalize_agent_result_view_pair,
)
from harness.execution.contracts import ActionDispatchResult, ExecutionStepRequest
from harness.execution.executor import ExecutionExecutor
from harness.runtime.memory.result_delivery import (
    REPRESENTATION_AGENT_RESULT_VIEW,
    admit_pending_result_delivery,
    project_latest_action_results,
)
from tooling.mapping.deed_to_ir.operand_suite import build_operand_suite_payload

_SCOPE = {
    "dossier_id": "d-fixture",
    "transcription_id": "tx-1",
    "workspace_id": "ws-1",
    "run_id": "run-1",
}
_CRITICAL_CROP = "image:derived:fba6f159e40d4010896245d6525d4acf"
_SOURCE_REPAIR_RESOLUTION = (
    Path(__file__).resolve().parents[4]
    / "practice_deeds"
    / "right_of_way"
    / "deed_to_ir"
    / "variants"
    / "corrupted_handoff_source_repair"
    / "resolution_state.json"
)
_DIAGNOSIS_KEYS = (
    "suspected_wrong_operand",
    "recommended_correction",
    "correct_value",
    "selected_evidence_ref",
    "requires_source_repair",
)


def _measure(view: Any) -> int:
    return measure_agent_result_view_chars(agent_result_view_to_wire(view))


def _operand_suite_row(*, ref_id: str = "deed_to_ir:operands:run-1") -> dict[str, Any]:
    snapshot = json.loads(_SOURCE_REPAIR_RESOLUTION.read_text(encoding="utf-8"))
    payload = build_operand_suite_payload(
        {
            "scope": {"run_id": "run-1", "workspace_id": "ws-1"},
            "resolution_state_snapshot": snapshot,
            "resolution_state_ref": "transcript_edit:resolution_state:source-repair",
        },
        operand_suite_ref=ref_id,
    )
    assert payload is not None
    return {
        "ref_id": ref_id,
        "artifact_type": "deed_to_ir_operand_suite",
        **payload,
    }


def _hydrate_outputs(
    *rows: dict[str, Any],
    errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result_rows = [dict(row) for row in rows]
    return {
        "results": result_rows,
        "errors": list(errors or []),
        "hydrated_count": len(result_rows),
        "cap_exceeded": False,
    }


def _assert_result_accounting(view: Any, *, source_count: int) -> None:
    kept = len(view.payload.get("results") or [])
    omitted = int(view.payload.get("results_omitted_count") or 0)
    assert kept + omitted == source_count


def _assert_error_accounting(view: Any, *, source_count: int) -> None:
    kept = len(view.payload.get("errors") or [])
    omitted = int(view.payload.get("errors_omitted_count") or 0)
    assert kept + omitted == source_count


def test_operand_evidence_preservation() -> None:
    suite = _operand_suite_row()
    view, omitted = build_hydrate_artifact_refs_view(
        _hydrate_outputs(suite),
        action_inputs={"ref_ids": [suite["ref_id"]]},
    )
    assert omitted is None and view is not None
    assert view.schema_id == SCHEMA_HYDRATE_ARTIFACT_REFS
    assert view.continuity_key is None
    _assert_result_accounting(view, source_count=1)
    results = view.payload.get("results") or []
    assert len(results) == 1
    row = results[0]
    assert row["artifact_type"] == "deed_to_ir_operand_suite"
    operands = row.get("operands") or []
    target = next(op for op in operands if op.get("operand_id") == "p1_call2_distance")
    assert _CRITICAL_CROP in (target.get("evidence_refs") or [])
    for key in (
        "operand_suite_ref",
        "projection_mode",
        "totals",
        "operand_groups",
        "operands",
    ):
        assert key in row


def test_no_deterministic_diagnosis_fields() -> None:
    suite = _operand_suite_row()
    view, omitted = build_hydrate_artifact_refs_view(_hydrate_outputs(suite))
    assert omitted is None and view is not None
    serialized = json.dumps(agent_result_view_to_wire(view), sort_keys=True)
    for banned in _DIAGNOSIS_KEYS:
        assert banned not in serialized


def test_pipeline_continuity_preserves_operand_evidence() -> None:
    suite = _operand_suite_row()
    # Force the agent_result_view representation path (exact outputs > 12k).
    oversized = {
        "ref_id": "feature_graph:ir:pad",
        "artifact_type": "ir",
        "pad": "X" * 8_000,
    }
    raw_outputs = _hydrate_outputs(suite, oversized)
    assert (
        len(json.dumps(raw_outputs, separators=(",", ":"), sort_keys=True))
        > MAX_AGENT_RESULT_VIEW_CHARS
    )

    wrapped = wrap_handler_with_result_view(
        lambda _r: {"executed": True, "outputs": raw_outputs},
        action_id="hydrate_artifact_refs",
        **_SCOPE,
    )
    executor = ExecutionExecutor()
    executor.register("hydrate_artifact_refs", wrapped)
    step = executor.execute(
        ExecutionStepRequest(
            session_id="s1",
            action_id="hydrate_artifact_refs",
            idempotency_key="h1",
            inputs={"ref_ids": [suite["ref_id"], oversized["ref_id"]]},
        )
    )
    assert step.agent_result_view is not None
    assert step.agent_result_view.continuity_key is None
    assert step.agent_result_view.schema_id == SCHEMA_HYDRATE_ARTIFACT_REFS

    deliveries: list[dict[str, Any]] = []
    outcome = admit_pending_result_delivery(
        deliveries,
        result=ActionDispatchResult(
            action_id="hydrate_artifact_refs",
            executed=True,
            outputs=dict(step.outputs),
            agent_result_view=step.agent_result_view,
        ),
        source_turn_index=3,
        action_index=0,
        action_alias="hydrate_artifact_refs",
        execution_state="executed",
    )
    assert outcome.status == "admitted"
    assert deliveries[0]["representation_kind"] == REPRESENTATION_AGENT_RESULT_VIEW

    projected = project_latest_action_results(deliveries)
    assert projected.latest_action_results
    delivered = projected.latest_action_results[0]
    blob = json.dumps(delivered, sort_keys=True)
    assert "p1_call2_distance" in blob
    assert _CRITICAL_CROP in blob


def test_mixed_result_pressure() -> None:
    oversized = {
        "ref_id": "feature_graph:ir:huge",
        "artifact_type": "ir",
        "graph": {"pad": "Y" * 20_000},
    }
    suite = _operand_suite_row()
    small = {
        "ref_id": "feature_graph:compile:c1",
        "artifact_type": "compile",
        "artifact_id": "c1",
        "status": "ok",
    }
    view, omitted = build_hydrate_artifact_refs_view(
        _hydrate_outputs(oversized, suite, small),
        action_inputs={
            "ref_ids": [oversized["ref_id"], suite["ref_id"], small["ref_id"]]
        },
    )
    assert omitted is None and view is not None
    assert _measure(view) <= MAX_AGENT_RESULT_VIEW_CHARS
    _assert_result_accounting(view, source_count=3)
    results = view.payload.get("results") or []
    refs = {row.get("ref_id") for row in results}
    assert suite["ref_id"] in refs
    assert small["ref_id"] in refs
    assert oversized["ref_id"] not in refs
    omitted_rows = view.payload.get("results_omitted") or []
    assert any(
        row.get("ref_id") == oversized["ref_id"] and row.get("reason") == "view_budget"
        for row in omitted_rows
    )
    assert int(view.payload.get("results_omitted_count") or 0) >= 1
    target = next(
        op
        for row in results
        if row.get("artifact_type") == "deed_to_ir_operand_suite"
        for op in (row.get("operands") or [])
        if op.get("operand_id") == "p1_call2_distance"
    )
    assert _CRITICAL_CROP in (target.get("evidence_refs") or [])


def test_images_metadata_only_raw_evidence_unchanged() -> None:
    image_row = {
        "ref_id": _CRITICAL_CROP,
        "kind": "upstream_derived_image",
        "basename": "crop.png",
        "role": "point_crop",
        "exists": True,
        "width_height": [120, 80],
        "parent_ref_id": "image:assoc:parent",
        "absolute_path": r"C:\secrets\crop.png",
        "path": "/tmp/crop.png",
        "image_b64": "iVBORw0KGgo=",
        "b64": "iVBORw0KGgo=",
    }
    evidence = {
        "ref_id": _CRITICAL_CROP,
        "b64": "iVBORw0KGgo=",
        "media_type": "image/png",
    }
    raw = {
        "executed": True,
        "outputs": _hydrate_outputs(image_row),
        "image_evidence": [copy.deepcopy(evidence)],
    }
    attached = attach_deed_to_ir_result_view(
        raw,
        action_id="hydrate_artifact_refs",
        action_inputs={"ref_ids": [_CRITICAL_CROP]},
        **_SCOPE,
    )
    assert attached["image_evidence"] == [evidence]
    view_wire = attached["agent_result_view"]
    view, om = normalize_agent_result_view_pair(view_wire, None)
    assert om is None and view is not None
    serialized = json.dumps(view.payload, sort_keys=True)
    for banned in ("absolute_path", "image_b64", "iVBORw0KGgo=", r"C:\\secrets"):
        assert banned not in serialized
    row = view.payload["results"][0]
    assert row["ref_id"] == _CRITICAL_CROP
    assert row["kind"] == "upstream_derived_image"
    assert row["basename"] == "crop.png"
    assert row["width_height"] == [120, 80]
    assert row["exists"] is True


def test_attachment_gates_and_ordering() -> None:
    suite = _operand_suite_row(ref_id="deed_to_ir:operands:a")
    small_b = {
        "ref_id": "feature_graph:ir:b",
        "artifact_type": "ir",
        "artifact_id": "b",
    }
    small_c = {
        "ref_id": "feature_graph:ir:c",
        "artifact_type": "ir",
        "artifact_id": "c",
    }
    # Returned order differs from request order.
    outputs = _hydrate_outputs(small_c, suite, small_b)

    success = attach_deed_to_ir_result_view(
        {"executed": True, "outputs": outputs},
        action_id="hydrate_artifact_refs",
        action_inputs={"ref_ids": [suite["ref_id"], small_b["ref_id"], small_c["ref_id"]]},
        **_SCOPE,
    )
    assert "agent_result_view" in success
    assert "agent_result_view_omitted" not in success
    view, _ = normalize_agent_result_view_pair(success["agent_result_view"], None)
    assert view is not None
    assert view.continuity_key is None
    order = [row["ref_id"] for row in view.payload["results"]]
    # Operand suites fit before other rows; within classes request order is preserved.
    assert order[0] == suite["ref_id"]
    assert order[1:] == [small_b["ref_id"], small_c["ref_id"]]

    refused = attach_deed_to_ir_result_view(
        {
            "executed": False,
            "refusal": {"reason_code": "ref_ids_required", "retryable": False},
            "outputs": {"error": {"code": "ref_ids_required"}},
        },
        action_id="hydrate_artifact_refs",
        **_SCOPE,
    )
    assert "agent_result_view" not in refused
    assert "agent_result_view_omitted" not in refused

    malformed = attach_deed_to_ir_result_view(
        {"executed": True, "outputs": ["not-a-mapping"]},
        action_id="hydrate_artifact_refs",
        **_SCOPE,
    )
    assert "agent_result_view" not in malformed
    assert "agent_result_view_omitted" not in malformed

    # Returned-order fallback when request has no valid ref_ids.
    # Fit priority still places operand suites ahead of other artifact rows;
    # within the non-operand class, returned order is preserved.
    fallback_view, _ = build_hydrate_artifact_refs_view(
        outputs,
        action_inputs={"ref_ids": [123, None]},  # type: ignore[list-item]
    )
    assert fallback_view is not None
    assert [row["ref_id"] for row in fallback_view.payload["results"]] == [
        suite["ref_id"],
        small_c["ref_id"],
        small_b["ref_id"],
    ]

    invalid_row = {"artifact_type": "ir", "pad": "z"}  # missing ref_id
    invalid_view, _ = build_hydrate_artifact_refs_view(
        _hydrate_outputs(invalid_row, small_b)
    )
    assert invalid_view is not None
    _assert_result_accounting(invalid_view, source_count=2)
    omitted_rows = invalid_view.payload.get("results_omitted") or []
    # Malformed rows without ref_id cannot emit a descriptor; count still rises.
    assert int(invalid_view.payload.get("results_omitted_count") or 0) >= 1
    assert not any(row.get("reason") == "view_budget" and "ref_id" not in row for row in omitted_rows)


def test_strict_collection_shape_validation() -> None:
    from harness.execution.agent_result_view import OMISSION_REASON_INVALID_SHAPE

    view_map, om_map = build_hydrate_artifact_refs_view(
        {"results": {"ref_id": "x"}, "hydrated_count": 0, "cap_exceeded": False}
    )
    assert view_map is None
    assert om_map is not None
    assert om_map.reason == OMISSION_REASON_INVALID_SHAPE

    view_str, om_str = build_hydrate_artifact_refs_view(
        {"results": "not-a-list", "hydrated_count": 0, "cap_exceeded": False}
    )
    assert view_str is None
    assert om_str is not None
    assert om_str.reason == OMISSION_REASON_INVALID_SHAPE

    view_err, om_err = build_hydrate_artifact_refs_view(
        {
            "results": [],
            "errors": {"reason": "broken"},
            "hydrated_count": 0,
            "cap_exceeded": False,
        }
    )
    assert view_err is None
    assert om_err is not None
    assert om_err.reason == OMISSION_REASON_INVALID_SHAPE

    attached = attach_deed_to_ir_result_view(
        {
            "executed": True,
            "outputs": {"results": {"a": 1}, "hydrated_count": 0, "cap_exceeded": False},
        },
        action_id="hydrate_artifact_refs",
        **_SCOPE,
    )
    assert "agent_result_view" not in attached
    assert attached["agent_result_view_omitted"]["reason"] == OMISSION_REASON_INVALID_SHAPE

    view_results_null, om_results_null = build_hydrate_artifact_refs_view(
        {"results": None, "hydrated_count": 0, "cap_exceeded": False}
    )
    assert view_results_null is None
    assert om_results_null is not None
    assert om_results_null.reason == OMISSION_REASON_INVALID_SHAPE

    view_errors_null, om_errors_null = build_hydrate_artifact_refs_view(
        {
            "results": [],
            "errors": None,
            "hydrated_count": 0,
            "cap_exceeded": False,
        }
    )
    assert view_errors_null is None
    assert om_errors_null is not None
    assert om_errors_null.reason == OMISSION_REASON_INVALID_SHAPE

    # Missing keys still use canonical empty-collection behavior.
    view_missing, om_missing = build_hydrate_artifact_refs_view(
        {"hydrated_count": 0, "cap_exceeded": False}
    )
    assert om_missing is None and view_missing is not None
    _assert_result_accounting(view_missing, source_count=0)
    _assert_error_accounting(view_missing, source_count=0)


def test_mixed_non_mapping_result_elements_counted() -> None:
    small = {
        "ref_id": "feature_graph:ir:ok",
        "artifact_type": "ir",
        "artifact_id": "ok",
    }
    outputs = {
        "results": [small, "skip-me", 42, None, small],
        "errors": [],
        "hydrated_count": 2,
        "cap_exceeded": False,
    }
    view, omitted = build_hydrate_artifact_refs_view(outputs)
    assert omitted is None and view is not None
    _assert_result_accounting(view, source_count=5)
    kept_refs = [row.get("ref_id") for row in view.payload["results"]]
    assert kept_refs == [small["ref_id"], small["ref_id"]]
    assert int(view.payload["results_omitted_count"]) == 3
    assert view.payload["hydrated_count"] == 2


def test_not_json_safe_rows_never_view_budget() -> None:
    from harness.execution.agent_result_view import OMISSION_REASON_NOT_JSON_SAFE

    class _Unsupported:
        pass

    bad_artifact = {
        "ref_id": "feature_graph:ir:bad",
        "artifact_type": "ir",
        "artifact_id": "bad",
        "nested": {"value": _Unsupported()},
    }
    good = {
        "ref_id": "feature_graph:compile:good",
        "artifact_type": "compile",
        "artifact_id": "good",
        "status": "ok",
    }
    view, omitted = build_hydrate_artifact_refs_view(
        _hydrate_outputs(bad_artifact, good)
    )
    assert omitted is None and view is not None
    _assert_result_accounting(view, source_count=2)
    refs = {row.get("ref_id") for row in view.payload["results"]}
    assert good["ref_id"] in refs
    assert bad_artifact["ref_id"] not in refs
    omitted_rows = view.payload.get("results_omitted") or []
    bad_desc = next(row for row in omitted_rows if row.get("ref_id") == bad_artifact["ref_id"])
    assert bad_desc["reason"] == OMISSION_REASON_NOT_JSON_SAFE
    assert bad_desc["reason"] != "view_budget"

    bad_image = {
        "ref_id": _CRITICAL_CROP,
        "kind": "upstream_derived_image",
        "basename": _Unsupported(),
        "exists": True,
        "width_height": [10, 10],
    }
    later = {
        "ref_id": "feature_graph:ir:later",
        "artifact_type": "ir",
        "artifact_id": "later",
    }
    raw = {
        "executed": True,
        "outputs": _hydrate_outputs(bad_image, later),
        "image_evidence": [{"ref_id": _CRITICAL_CROP, "b64": "abc", "media_type": "image/png"}],
    }
    evidence_before = copy.deepcopy(raw["image_evidence"])
    attached = attach_deed_to_ir_result_view(
        raw,
        action_id="hydrate_artifact_refs",
        **_SCOPE,
    )
    assert attached["image_evidence"] == evidence_before
    img_view, img_om = normalize_agent_result_view_pair(attached["agent_result_view"], None)
    assert img_om is None and img_view is not None
    _assert_result_accounting(img_view, source_count=2)
    assert later["ref_id"] in {row.get("ref_id") for row in img_view.payload["results"]}
    img_omitted = img_view.payload.get("results_omitted") or []
    img_desc = next(row for row in img_omitted if row.get("ref_id") == _CRITICAL_CROP)
    assert img_desc["reason"] == OMISSION_REASON_NOT_JSON_SAFE
    assert "view_budget" not in {row.get("reason") for row in img_omitted}


def test_strict_hydrated_count_rejects_bool() -> None:
    small = {
        "ref_id": "feature_graph:ir:one",
        "artifact_type": "ir",
        "artifact_id": "one",
    }
    view, omitted = build_hydrate_artifact_refs_view(
        {
            "results": [small],
            "errors": [],
            "hydrated_count": True,  # must not be treated as int 1
            "cap_exceeded": False,
        }
    )
    assert omitted is None and view is not None
    _assert_result_accounting(view, source_count=1)
    assert view.payload["hydrated_count"] == 1  # source-list fallback
    assert type(view.payload["hydrated_count"]) is int

    view2, omitted2 = build_hydrate_artifact_refs_view(
        {
            "results": [small],
            "errors": [],
            "hydrated_count": 7,
            "cap_exceeded": True,
        }
    )
    assert omitted2 is None and view2 is not None
    assert view2.payload["hydrated_count"] == 7
    assert view2.payload["cap_exceeded"] is True


def test_working_head_isolation() -> None:
    suite = _operand_suite_row()
    hydrate = attach_deed_to_ir_result_view(
        {"executed": True, "outputs": _hydrate_outputs(suite)},
        action_id="hydrate_artifact_refs",
        **_SCOPE,
    )
    save = attach_deed_to_ir_result_view(
        {
            "executed": True,
            "outputs": {
                "ir_artifact_ref": "feature_graph:ir:v1",
                "working_draft_ref": "feature_graph:ir:v1",
                "current_draft_ir": {
                    "draft_ir_ref": "feature_graph:ir:v1",
                    "working_draft_ref": "feature_graph:ir:v1",
                    "node_count": 1,
                },
            },
        },
        action_id="save_ir_artifact",
        **_SCOPE,
    )
    assert hydrate["agent_result_view"].get("continuity_key") is None
    assert hydrate["agent_result_view"]["schema_id"] == SCHEMA_HYDRATE_ARTIFACT_REFS
    head = build_working_head_continuity_key(**_SCOPE)
    assert head is not None
    assert save["agent_result_view"]["continuity_key"] == head
    assert save["agent_result_view"]["schema_id"] == SCHEMA_SAVE_IR_ARTIFACT


def test_mutual_exclusivity_and_envelope_budget() -> None:
    suite = _operand_suite_row()
    attached = attach_deed_to_ir_result_view(
        {"executed": True, "outputs": _hydrate_outputs(suite)},
        action_id="hydrate_artifact_refs",
        **_SCOPE,
    )
    assert ("agent_result_view" in attached) ^ ("agent_result_view_omitted" in attached)
    view, om = normalize_agent_result_view_pair(attached.get("agent_result_view"), None)
    assert om is None and view is not None
    assert _measure(view) <= MAX_AGENT_RESULT_VIEW_CHARS


def test_errors_do_not_evict_operand_content() -> None:
    suite = _operand_suite_row()
    errors = [
        {"ref_id": f"feature_graph:ir:missing-{i}", "reason": "not_found", "message": "m" * 200}
        for i in range(40)
    ]
    view, omitted = build_hydrate_artifact_refs_view(
        _hydrate_outputs(suite, errors=errors),
        action_inputs={"ref_ids": [suite["ref_id"]]},
    )
    assert omitted is None and view is not None
    _assert_result_accounting(view, source_count=1)
    _assert_error_accounting(view, source_count=40)
    results = view.payload.get("results") or []
    assert any(row.get("artifact_type") == "deed_to_ir_operand_suite" for row in results)
    target = next(
        op
        for row in results
        for op in (row.get("operands") or [])
        if op.get("operand_id") == "p1_call2_distance"
    )
    assert _CRITICAL_CROP in (target.get("evidence_refs") or [])
    assert _measure(view) <= MAX_AGENT_RESULT_VIEW_CHARS


def test_malformed_error_elements_accounted() -> None:
    small = {
        "ref_id": "feature_graph:ir:ok",
        "artifact_type": "ir",
        "artifact_id": "ok",
    }
    usable = {"ref_id": "feature_graph:ir:missing", "reason": "not_found"}
    outputs = {
        "results": [small],
        "errors": [usable, "skip", None, {}, 7, usable],
        "hydrated_count": 1,
        "cap_exceeded": False,
    }
    view, omitted = build_hydrate_artifact_refs_view(outputs)
    assert omitted is None and view is not None
    _assert_result_accounting(view, source_count=1)
    _assert_error_accounting(view, source_count=6)
    projected = view.payload.get("errors") or []
    assert len(projected) == 2
    assert all(row.get("ref_id") == usable["ref_id"] for row in projected)
    assert int(view.payload.get("errors_omitted_count") or 0) == 4


def test_operand_suite_discriminator_no_coercion() -> None:
    coerced = {
        "ref_id": "feature_graph:ir:not-suite",
        "artifact_type": ["deed_to_ir_operand_suite"],
        "artifact_id": "not-suite",
    }
    real = _operand_suite_row()
    view, omitted = build_hydrate_artifact_refs_view(_hydrate_outputs(coerced, real))
    assert omitted is None and view is not None
    _assert_result_accounting(view, source_count=2)
    # Non-string artifact_type must not be treated as an operand suite.
    types = [row.get("artifact_type") for row in view.payload["results"]]
    assert "deed_to_ir_operand_suite" in types
    assert any(row.get("ref_id") == coerced["ref_id"] for row in view.payload["results"]) or any(
        row.get("ref_id") == coerced["ref_id"]
        for row in (view.payload.get("results_omitted") or [])
    )
