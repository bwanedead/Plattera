"""Deterministic coverage for deed-to-IR semantic-head AgentResultView providers."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from domains.mapping.deed_to_ir.execution.draft_result_views import (
    SCHEMA_PATCH_IR_DRAFT,
    SCHEMA_SAVE_IR_ARTIFACT,
    build_patch_ir_draft_view,
    build_save_ir_artifact_view,
)
from domains.mapping.deed_to_ir.execution.finalization_result_views import (
    SCHEMA_FINALIZE_CURRENT_OUTPUT,
    build_finalize_current_output_view,
)
from domains.mapping.deed_to_ir.execution.mapping_result_views import (
    SCHEMA_SUBMIT_IR_FOR_MAPPING,
    build_submit_ir_for_mapping_view,
)
from domains.mapping.deed_to_ir.execution.result_view_common import (
    WORKING_HEAD_CONTINUITY_PREFIX,
    build_working_head_continuity_key,
)
from domains.mapping.deed_to_ir.execution.result_views import (
    attach_deed_to_ir_result_view,
    wrap_handler_with_result_view,
)
from domains.mapping.deed_to_ir.runtime_adapter import build_deed_to_ir_runtime_adapter
from harness.execution.agent_result_view import (
    MAX_AGENT_RESULT_VIEW_CHARS,
    agent_result_view_to_wire,
    measure_agent_result_view_chars,
    normalize_agent_result_view_pair,
)
from harness.execution.contracts import ActionDispatchResult, ExecutionStepRequest
from harness.execution.executor import ExecutionExecutor
from harness.execution.wire_codec import (
    action_dispatch_result_from_wire,
    action_dispatch_result_to_wire,
)
from tooling.mapping.deed_to_ir.finalizer_result_boundary import (
    normalize_finalizer_agent_visible_result,
)

_FIXTURE = Path(__file__).resolve().parent / "test_fixtures" / "transcript_edit_output_handoff.json"
_RESOLUTION = Path(__file__).resolve().parent / "test_fixtures" / "resolution_state_snapshot.json"

_SCOPE = {
    "dossier_id": "dossier-fixture",
    "transcription_id": "tx-fixture",
    "workspace_id": "ws-fixture",
    "run_id": "practice-row-live-20260619-76",
}

_EXPECTED_TOOL_IDS = (
    "hydrate_deed_to_ir_input",
    "describe_feature_graph_capabilities",
    "save_ir_artifact",
    "patch_ir_draft",
    "submit_ir_for_mapping",
    "finalize_current_deed_to_ir_output",
    "hydrate_artifact_refs",
    "list_feature_graph_artifacts",
)

_WRAPPED_ACTIONS = frozenset(
    {
        "save_ir_artifact",
        "patch_ir_draft",
        "submit_ir_for_mapping",
        "finalize_current_deed_to_ir_output",
    }
)


def _measure_view(view) -> int:
    return measure_agent_result_view_chars(agent_result_view_to_wire(view))


def _expected_continuity_key(**scope: str) -> str:
    canonical = json.dumps(
        {
            "dossier_id": scope["dossier_id"],
            "run_id": scope["run_id"],
            "transcription_id": scope["transcription_id"],
            "workspace_id": scope["workspace_id"],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{WORKING_HEAD_CONTINUITY_PREFIX}{digest}"


def _launch_context(**overrides: object) -> dict:
    base = {
        "dossier_id": _SCOPE["dossier_id"],
        "transcript_edit_output_path": str(_FIXTURE),
        "transcription_id": _SCOPE["transcription_id"],
        "workspace_id": _SCOPE["workspace_id"],
        "run_id": _SCOPE["run_id"],
        "resolution_state_ref": "transcript_edit:resolution_state:fixture-001",
        "resolution_state_snapshot": json.loads(_RESOLUTION.read_text(encoding="utf-8")),
    }
    base.update(overrides)
    return base


def _draft_outputs(*, current_ref: str, base_ref: str | None = None) -> dict:
    outputs = {
        "ir_artifact_ref": current_ref,
        "draft_ir_ref": current_ref,
        "working_draft_ref": current_ref,
        "draft_version": "v2",
        "draft_sequence_index": 2,
        "graph_id": "graph-1",
        "artifact_id": "graph-1_d2",
        "is_draft": True,
        "node_count": 3,
        "edge_count": 2,
        "course_count": 1,
        "compile_gap_count": 1,
        "judge_finding_count": 1,
        "compile_gaps": [{"code": "gap_a", "message": "missing bearing"}],
        "judge_findings": [{"code": "finding_a", "message": "ambiguous corner"}],
        "draft_repair_items": [{"code": "repair_a", "message": "fix course length"}],
        "current_draft_ir": {
            "draft_ir_ref": current_ref,
            "working_draft_ref": current_ref,
            "draft_version": "v2",
            "graph_id": "graph-1",
            "node_count": 3,
            "edge_count": 2,
            "compile_gap_count": 1,
            "judge_finding_count": 1,
            "compile_gaps": [{"code": "gap_a", "message": "missing bearing"}],
            "judge_findings": [{"code": "finding_a", "message": "ambiguous corner"}],
            "draft_repair_items": [{"code": "repair_a", "message": "fix course length"}],
            "nodes": [{"id": "n1"}, {"id": "n2"}, {"id": "n3"}],
            "edges": [{"id": "e1"}, {"id": "e2"}],
        },
        "world_bbox": (1.0, 2.0, 3.0, 4.0),
        "absolute_path": "C:/host/secret/ir.json",
        "metadata": {"path": "C:/host/meta.json", "b64": "QUJD", "ok": True},
    }
    if base_ref:
        outputs["base_draft_ref"] = base_ref
        outputs["node_upserts_applied"] = 1
        outputs["patch_warnings"] = [{"kind": "node_removal_noop", "node_id": "gone"}]
    return outputs


def _mapping_outputs(*, mapping_ref: str, ir_ref: str, historical: bool = False) -> dict:
    outputs = {
        "mapping_artifact_ref": mapping_ref,
        "compile_artifact_ref": "feature_graph:compile:c1",
        "judge_artifact_ref": "feature_graph:judge:j1",
        "geometry_ref": "feature_graph:geometry:g1",
        "control_render_ref": "feature_graph:control:r1",
        "clean_render_ref": "feature_graph:clean:r1",
        "graph_id": "graph-1",
        "compiled_feature_count": 4,
        "rendered_feature_count": 3,
        "skipped_feature_count": 1,
        "world_bbox": (10.0, 20.0, 30.0, 40.0),
        "current_mapping_lineage": {
            "mapping_artifact_ref": mapping_ref,
            "source_ir_artifact_ref": ir_ref,
            "lineage_current": True,
            "use_for_next_preview": True,
            "stale": False,
        },
        "mapping_review": {
            "mapping_artifact_ref": mapping_ref,
            "source_ir_artifact_ref": ir_ref,
            "control_render_ref": "feature_graph:control:r1",
            "geometry_ref": "feature_graph:geometry:g1",
            "compile_gap_count": 0,
            "judge_gap_count": 1,
            "skipped_feature_count": 1,
            "lineage_current": True,
            "current_mapping_artifact_ref": mapping_ref,
            "sanity_review": {
                "conclusion": "needs_repair",
                "summary": "One judge gap remains on the current lineage.",
                "feature_metrics": [
                    {
                        "feature_id": "f1",
                        "endpoint_displacement": 1.2,
                        "total_length": 100.0,
                        "vertex_count": 4,
                    }
                ],
                "review_questions": ["Does the judge gap match the intended corner?"],
            },
            "correction_posture": {
                "active": True,
                "reason_codes": ["repair_judge_gap"],
                "candidate_deltas": [
                    {
                        "target_entity_id": "entity-1",
                        "value_kind": "bearing",
                        "selected_ir_display_value": "N 10 E",
                    }
                ],
            },
            "draft_patch_targets": [
                {"patch_target_id": "pt1", "node_id": "n1", "field": "bearing"}
            ],
            "recommended_publish_refs": ["feature_graph:control:r1"],
        },
        "active_finalization_session": {
            "status": "pending_decisions",
            "lineage": {
                "mapping_artifact_ref": mapping_ref,
                "source_ir_artifact_ref": ir_ref,
            },
            "requirements": {
                "scope_ids": ["parcel_1"],
                "correction_candidates": [{"target_entity_id": "corr_1"}],
                "dependency_candidates": [],
            },
            "decisions": {
                "scope_statuses": {},
                "correction_dispositions": {},
                "dependency_dispositions": {},
                "rationales": {},
            },
        },
        "active_handoff_context": {"handoff_id": "h1", "status": "active"},
        "absolute_path": "C:/host/mapping.json",
    }
    if historical:
        outputs["historical_mapping_refs"] = [
            "feature_graph:mapping:old",
            "feature_graph:ir:old",
        ]
        outputs["prior_mapping_lineage"] = {
            "mapping_artifact_ref": "feature_graph:mapping:old",
            "source_ir_artifact_ref": "feature_graph:ir:old",
            "lineage_current": False,
            "stale": True,
        }
    return outputs


def _pending_session(*, mapping_ref: str, ir_ref: str) -> dict:
    return {
        "status": "pending_decisions",
        "lineage": {
            "mapping_artifact_ref": mapping_ref,
            "source_ir_artifact_ref": ir_ref,
        },
        "requirements": {
            "scope_ids": ["parcel_1"],
            "correction_candidates": [{"target_entity_id": "corr_1"}],
            "dependency_candidates": [{"candidate_id": "dep_1"}],
        },
        "decisions": {
            "scope_statuses": {},
            "correction_dispositions": {},
            "dependency_dispositions": {},
            "rationales": {},
        },
    }


# --- Continuity key ---------------------------------------------------------


def test_working_head_continuity_key_stable_and_scoped() -> None:
    key_a = build_working_head_continuity_key(**_SCOPE)
    key_b = build_working_head_continuity_key(**_SCOPE)
    assert key_a == key_b == _expected_continuity_key(**_SCOPE)
    assert key_a.startswith(WORKING_HEAD_CONTINUITY_PREFIX)
    assert len(key_a) <= 256

    other = build_working_head_continuity_key(
        dossier_id=_SCOPE["dossier_id"],
        transcription_id=_SCOPE["transcription_id"],
        workspace_id=_SCOPE["workspace_id"],
        run_id="different-run",
    )
    assert other is not None
    assert other != key_a

    assert (
        build_working_head_continuity_key(
            dossier_id=_SCOPE["dossier_id"],
            transcription_id=_SCOPE["transcription_id"],
            workspace_id=_SCOPE["workspace_id"],
            run_id=None,
        )
        is None
    )


def test_save_patch_submit_finalizer_share_continuity_key() -> None:
    continuity = build_working_head_continuity_key(**_SCOPE)
    assert continuity is not None

    save_view, _ = build_save_ir_artifact_view(
        _draft_outputs(current_ref="feature_graph:ir:v1"),
        continuity_key=continuity,
    )
    patch_view, _ = build_patch_ir_draft_view(
        _draft_outputs(current_ref="feature_graph:ir:v2", base_ref="feature_graph:ir:v1"),
        continuity_key=continuity,
    )
    submit_view, _ = build_submit_ir_for_mapping_view(
        _mapping_outputs(
            mapping_ref="feature_graph:mapping:m1",
            ir_ref="feature_graph:ir:v2",
        ),
        continuity_key=continuity,
    )
    finalizer_view, _ = build_finalize_current_output_view(
        {
            "executed": True,
            "outputs": {
                "finalization_status": "published",
                "final_package_preview_ref": "deed_to_ir:preview:p1",
                "output_revision_ref": "deed_to_ir:output:o1",
                "mapping_artifact_ref": "feature_graph:mapping:m1",
                "ir_artifact_ref": "feature_graph:ir:v2",
                "next_required_action": "complete_run",
                "idempotent_replay": False,
            },
        },
        continuity_key=continuity,
    )
    assert save_view is not None and patch_view is not None
    assert submit_view is not None and finalizer_view is not None
    assert {
        save_view.continuity_key,
        patch_view.continuity_key,
        submit_view.continuity_key,
        finalizer_view.continuity_key,
    } == {continuity}
    for view in (save_view, patch_view, submit_view, finalizer_view):
        wire = agent_result_view_to_wire(view)
        assert "continuity_key" not in wire["payload"]
        assert continuity not in json.dumps(wire["payload"])
        assert _measure_view(view) <= MAX_AGENT_RESULT_VIEW_CHARS


# --- Envelope integrity -----------------------------------------------------


def test_schema_ids_and_json_native_tuple_conversion() -> None:
    continuity = build_working_head_continuity_key(**_SCOPE)
    draft_raw = _draft_outputs(current_ref="feature_graph:ir:v1")
    assert isinstance(draft_raw["world_bbox"], tuple)
    save_view, save_om = build_save_ir_artifact_view(draft_raw, continuity_key=continuity)
    assert save_om is None and save_view is not None
    assert save_view.schema_id == SCHEMA_SAVE_IR_ARTIFACT
    assert isinstance(draft_raw["world_bbox"], tuple)

    mapping_raw = _mapping_outputs(
        mapping_ref="feature_graph:mapping:m1",
        ir_ref="feature_graph:ir:v1",
    )
    assert isinstance(mapping_raw["world_bbox"], tuple)
    submit_view, submit_om = build_submit_ir_for_mapping_view(
        mapping_raw, continuity_key=continuity
    )
    assert submit_om is None and submit_view is not None
    assert submit_view.schema_id == SCHEMA_SUBMIT_IR_FOR_MAPPING
    assert isinstance(mapping_raw["world_bbox"], tuple)
    assert submit_view.payload["world_bbox"] == [10.0, 20.0, 30.0, 40.0]


def test_host_paths_and_binary_fields_stripped_recursively() -> None:
    continuity = build_working_head_continuity_key(**_SCOPE)
    outputs = _draft_outputs(current_ref="feature_graph:ir:v1")
    outputs["current_draft_ir"]["compile_gaps"] = [
        {
            "code": "gap_a",
            "message": "missing bearing",
            "absolute_path": "C:/host/secret.bin",
            "meta": {"path": "C:/host/child.json", "b64": "bbbb", "n": 1},
        }
    ]
    view, omitted = build_save_ir_artifact_view(outputs, continuity_key=continuity)
    assert omitted is None and view is not None
    blob = json.dumps(view.payload)
    assert "absolute_path" not in blob
    assert "image_b64" not in blob
    assert '"path"' not in blob
    assert "b64" not in blob
    assert "C:/host" not in blob
    assert "bbbb" not in blob
    assert view.payload["compile_gaps"][0]["meta"] == {"n": 1}


def test_oversized_collection_rows_omitted_whole_with_counts() -> None:
    continuity = build_working_head_continuity_key(**_SCOPE)
    outputs = _draft_outputs(current_ref="feature_graph:ir:v1")
    outputs["current_draft_ir"]["compile_gaps"] = [
        {"code": f"gap_{i}", "message": ("M" * 4000) + f"_{i}"} for i in range(8)
    ]
    outputs["current_draft_ir"]["judge_findings"] = [{"code": "keep", "message": "short finding"}]
    view, omitted = build_save_ir_artifact_view(outputs, continuity_key=continuity)
    assert omitted is None and view is not None
    assert _measure_view(view) <= MAX_AGENT_RESULT_VIEW_CHARS
    assert view.payload.get("judge_findings") == [{"code": "keep", "message": "short finding"}]
    omitted_count = int(view.payload.get("compile_gaps_omitted_count") or 0)
    kept = view.payload.get("compile_gaps") or []
    assert omitted_count >= 1
    assert len(kept) + omitted_count == 8
    for row in kept:
        suffix = row["code"].split("_", 1)[1]
        assert row["message"] == ("M" * 4000) + f"_{suffix}"
    assert "compile_gaps" not in view.payload["current_draft_ir"]
    assert view.payload["current_ir_artifact_ref"] == "feature_graph:ir:v1"

def test_invalid_view_emits_canonical_omission_marker() -> None:
    attached = attach_deed_to_ir_result_view(
        {
            "executed": True,
            "outputs": {
                "ir_artifact_ref": "R" * 20_000,
                "working_draft_ref": "R" * 20_000,
                "current_draft_ir": {"draft_ir_ref": "R" * 20_000, "pad": "P" * 20_000},
            },
        },
        action_id="save_ir_artifact",
        **_SCOPE,
    )
    assert "agent_result_view" not in attached
    assert "agent_result_view_omitted" in attached
    assert attached["agent_result_view_omitted"]["reason"] in {
        "view_budget",
        "invalid_shape",
        "not_json_safe",
    }


# --- Attachment gates -------------------------------------------------------


def test_failed_save_patch_submit_do_not_attach_working_head_view() -> None:
    refused = {
        "executed": False,
        "refusal": {"reason_code": "feature_graph_validation_failed", "retryable": True},
        "outputs": {"validation_errors": ["bad node"]},
    }
    for action_id in ("save_ir_artifact", "patch_ir_draft", "submit_ir_for_mapping"):
        out = attach_deed_to_ir_result_view(refused, action_id=action_id, **_SCOPE)
        assert "agent_result_view" not in out
        assert "agent_result_view_omitted" not in out
        assert out["refusal"]["reason_code"] == "feature_graph_validation_failed"


def test_attach_preserves_raw_result_equality_aside_from_view_field() -> None:
    raw = {
        "executed": True,
        "outputs": _draft_outputs(current_ref="feature_graph:ir:v1"),
        "artifact_refs": ["feature_graph:ir:v1"],
    }
    before = copy.deepcopy(raw)
    attached = attach_deed_to_ir_result_view(raw, action_id="save_ir_artifact", **_SCOPE)
    assert "agent_result_view" in attached
    raw_without_view = {k: v for k, v in attached.items() if k != "agent_result_view"}
    assert raw_without_view == before
    assert attached["outputs"] == before["outputs"]
    assert isinstance(attached["outputs"]["world_bbox"], tuple)
    assert isinstance(raw["outputs"]["world_bbox"], tuple)


# --- Draft behavior ---------------------------------------------------------


def test_save_and_patch_identify_current_ir() -> None:
    continuity = build_working_head_continuity_key(**_SCOPE)
    save_view, _ = build_save_ir_artifact_view(
        _draft_outputs(current_ref="feature_graph:ir:v1"),
        continuity_key=continuity,
    )
    assert save_view is not None
    assert save_view.payload["current_ir_artifact_ref"] == "feature_graph:ir:v1"
    assert save_view.payload["current_draft_ir"]["working_draft_ref"] == "feature_graph:ir:v1"
    assert save_view.payload["compile_gaps"]
    assert save_view.payload["judge_findings"]
    assert save_view.payload["draft_repair_items"]

    patch_view, _ = build_patch_ir_draft_view(
        _draft_outputs(current_ref="feature_graph:ir:v2", base_ref="feature_graph:ir:v1"),
        continuity_key=continuity,
    )
    assert patch_view is not None
    assert patch_view.schema_id == SCHEMA_PATCH_IR_DRAFT
    assert patch_view.payload["current_ir_artifact_ref"] == "feature_graph:ir:v2"
    assert patch_view.payload["base_draft_ref"] == "feature_graph:ir:v1"
    assert patch_view.payload["parent_draft_ref"] == "feature_graph:ir:v1"
    assert patch_view.payload["node_upserts_applied"] == 1
    assert patch_view.payload.get("current_ir_artifact_ref") != patch_view.payload.get(
        "base_draft_ref"
    )


# --- Mapping behavior -------------------------------------------------------


def test_mapping_view_lineage_pair_and_session() -> None:
    continuity = build_working_head_continuity_key(**_SCOPE)
    view, omitted = build_submit_ir_for_mapping_view(
        _mapping_outputs(
            mapping_ref="feature_graph:mapping:m2",
            ir_ref="feature_graph:ir:v3",
            historical=True,
        ),
        continuity_key=continuity,
    )
    assert omitted is None and view is not None
    lineage = view.payload["current_mapping_lineage"]
    assert lineage["mapping_artifact_ref"] == "feature_graph:mapping:m2"
    assert lineage["source_ir_artifact_ref"] == "feature_graph:ir:v3"
    assert view.payload["mapping_artifact_ref"] == "feature_graph:mapping:m2"
    assert view.payload["ir_artifact_ref"] == "feature_graph:ir:v3"
    assert view.payload["mapping_review"]["sanity_review"]["conclusion"] == "needs_repair"
    assert view.payload["mapping_review"]["correction_posture"]["active"] is True
    assert view.payload["mapping_review"]["draft_patch_targets"][0]["node_id"] == "n1"
    assert "active_finalization_session" in view.payload
    blob = json.dumps(view.payload)
    assert "feature_graph:mapping:old" not in blob
    assert "prior_mapping_lineage" not in blob
    assert "historical_mapping_refs" not in blob


def test_mapping_view_survives_envelope_pressure() -> None:
    continuity = build_working_head_continuity_key(**_SCOPE)
    outputs = _mapping_outputs(
        mapping_ref="feature_graph:mapping:m1",
        ir_ref="feature_graph:ir:v1",
    )
    outputs["mapping_review"]["sanity_review"]["detail_pad"] = "P" * 8_000
    outputs["mapping_review"]["draft_patch_targets"] = [
        {"patch_target_id": f"pt{i}", "node_id": f"n{i}", "field": "bearing", "note": "N" * 200}
        for i in range(40)
    ]
    view, omitted = build_submit_ir_for_mapping_view(outputs, continuity_key=continuity)
    assert omitted is None and view is not None
    assert _measure_view(view) <= MAX_AGENT_RESULT_VIEW_CHARS
    assert view.payload["current_mapping_lineage"]["mapping_artifact_ref"] == (
        "feature_graph:mapping:m1"
    )
    assert view.payload["mapping_review"]["sanity_review"]["conclusion"] == "needs_repair"
    assert view.payload["mapping_review"]["correction_posture"]["active"] is True


# --- Finalizer behavior -----------------------------------------------------


def test_finalizer_missing_decision_refusal_view() -> None:
    continuity = build_working_head_continuity_key(**_SCOPE)
    session = _pending_session(
        mapping_ref="feature_graph:mapping:m1",
        ir_ref="feature_graph:ir:v1",
    )
    raw = {
        "executed": False,
        "refusal": {
            "reason_code": "missing_finalization_decisions",
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "missing": {
                "scope_ids": ["parcel_1"],
                "correction_ids": ["corr_1"],
                "dependency_ids": ["dep_1"],
                "rationale_ids": ["parcel_1", "corr_1", "dep_1"],
            },
            "active_finalization_session": session,
            "prompt_carry_forward": {
                "schema_version": "prompt_carry_forward.v1",
                "payload": {"missing": {"scope_ids": ["parcel_1"]}},
            },
            "recommended_publish_request": {"action_id": "publish_deed_to_ir_from_preview"},
            "next_required_action": "finalize_current_deed_to_ir_output",
        },
    }
    normalized = normalize_finalizer_agent_visible_result(raw)
    attached = attach_deed_to_ir_result_view(
        normalized,
        action_id="finalize_current_deed_to_ir_output",
        **_SCOPE,
    )
    assert attached["executed"] is False
    assert "agent_result_view" in attached
    view, om = normalize_agent_result_view_pair(attached["agent_result_view"], None)
    assert om is None and view is not None
    assert view.schema_id == SCHEMA_FINALIZE_CURRENT_OUTPUT
    assert view.continuity_key == continuity
    assert view.payload["missing"]["scope_ids"] == ["parcel_1"]
    assert view.payload["missing"]["correction_ids"] == ["corr_1"]
    assert "active_finalization_session" in view.payload
    assert "prompt_carry_forward" not in view.payload
    assert "prompt_carry_forward" not in json.dumps(view.payload)
    assert "prepare_deed_to_ir_final_package" not in json.dumps(view.payload)
    assert "publish_deed_to_ir_from_preview" not in json.dumps(view.payload)
    assert "publish_deed_to_ir_output" not in json.dumps(view.payload)


def test_finalizer_hitl_does_not_invent_tool_next_action() -> None:
    continuity = build_working_head_continuity_key(**_SCOPE)
    raw = {
        "executed": False,
        "refusal": {
            "reason_code": "finalization_requires_hitl",
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "finalization_status": "pending_decisions",
            "active_finalization_session": _pending_session(
                mapping_ref="feature_graph:mapping:m1",
                ir_ref="feature_graph:ir:v1",
            ),
            "next_required_action": "prepare_deed_to_ir_final_package",
        },
    }
    normalized = normalize_finalizer_agent_visible_result(raw)
    view, omitted = build_finalize_current_output_view(
        normalized, continuity_key=continuity
    )
    assert omitted is None and view is not None
    blob = json.dumps(view.payload)
    assert "prepare_deed_to_ir_final_package" not in blob
    assert "publish_deed_to_ir_from_preview" not in blob
    # HITL must not invent a tool next action; boundary may clear retired IDs.
    assert view.payload.get("next_required_action") not in {
        "prepare_deed_to_ir_final_package",
        "publish_deed_to_ir_from_preview",
        "publish_deed_to_ir_output",
        "finalize_current_deed_to_ir_output",
        "submit_ir_for_mapping",
    }


def test_finalizer_success_contains_preview_and_output_refs() -> None:
    continuity = build_working_head_continuity_key(**_SCOPE)
    raw = {
        "executed": True,
        "outputs": {
            "finalization_status": "published",
            "final_package_preview_ref": "deed_to_ir:preview:immutable-1",
            "output_revision_ref": "deed_to_ir:output:rev-1",
            "mapping_artifact_ref": "feature_graph:mapping:m1",
            "ir_artifact_ref": "feature_graph:ir:v1",
            "idempotent_replay": False,
            "next_required_action": "complete_run",
            "prompt_carry_forward": {"should": "not appear"},
        },
    }
    normalized = normalize_finalizer_agent_visible_result(raw)
    attached = attach_deed_to_ir_result_view(
        normalized,
        action_id="finalize_current_deed_to_ir_output",
        **_SCOPE,
    )
    view, om = normalize_agent_result_view_pair(attached["agent_result_view"], None)
    assert om is None and view is not None
    assert view.payload["final_package_preview_ref"] == "deed_to_ir:preview:immutable-1"
    assert view.payload["output_revision_ref"] == "deed_to_ir:output:rev-1"
    assert "prompt_carry_forward" not in view.payload


def test_finalizer_view_attached_only_after_boundary() -> None:
    """Composition wraps the handler that already returns boundary-normalized results."""
    adapter = build_deed_to_ir_runtime_adapter()
    surface = adapter.build_turn_surface(_launch_context())
    handler = next(
        b.handler
        for b in surface.tool_bindings
        if b.tool_id == "finalize_current_deed_to_ir_output"
    )
    pre_boundary = {
        "executed": False,
        "refusal": {
            "reason_code": "missing_finalization_decisions",
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "missing": {
                "scope_ids": ["parcel_1"],
                "correction_ids": [],
                "dependency_ids": [],
                "rationale_ids": ["parcel_1"],
            },
            "active_finalization_session": _pending_session(
                mapping_ref="feature_graph:mapping:m1",
                ir_ref="feature_graph:ir:v1",
            ),
            "next_required_action": "prepare_deed_to_ir_final_package",
            "prompt_carry_forward": {"schema_version": "prompt_carry_forward.v1", "payload": {}},
        },
    }

    def _fake_finalize(**_kwargs: object) -> dict[str, object]:
        # Mimic tooling finalizer: normalize before returning to composition.
        return normalize_finalizer_agent_visible_result(pre_boundary)

    with patch(
        "domains.mapping.deed_to_ir.runtime_adapter.composition.finalize_current_deed_to_ir_output",
        side_effect=_fake_finalize,
    ):
        result = handler({})
    assert "agent_result_view" in result
    assert "prepare_deed_to_ir_final_package" not in json.dumps(result.get("outputs") or {})
    view, om = normalize_agent_result_view_pair(result["agent_result_view"], None)
    assert om is None and view is not None
    assert "prepare_deed_to_ir_final_package" not in json.dumps(view.payload)


# --- Composition + executor -------------------------------------------------


def test_composition_wraps_exactly_four_state_advancing_handlers() -> None:
    adapter = build_deed_to_ir_runtime_adapter()
    surface = adapter.build_turn_surface(_launch_context())
    tool_ids = [b.tool_id for b in surface.tool_bindings]
    assert tool_ids == list(_EXPECTED_TOOL_IDS)

    save_outputs = _draft_outputs(current_ref="feature_graph:ir:v1")
    patch_outputs = _draft_outputs(
        current_ref="feature_graph:ir:v2", base_ref="feature_graph:ir:v1"
    )
    submit_outputs = _mapping_outputs(
        mapping_ref="feature_graph:mapping:m1",
        ir_ref="feature_graph:ir:v2",
    )

    with (
        patch(
            "domains.mapping.deed_to_ir.runtime_adapter.composition.save_ir_artifact",
            return_value={"executed": True, "outputs": save_outputs},
        ),
        patch(
            "domains.mapping.deed_to_ir.runtime_adapter.composition.patch_ir_draft",
            return_value={"executed": True, "outputs": patch_outputs},
        ),
        patch(
            "domains.mapping.deed_to_ir.runtime_adapter.composition.submit_ir_for_mapping",
            return_value={"executed": True, "outputs": submit_outputs},
        ),
        patch(
            "domains.mapping.deed_to_ir.runtime_adapter.composition.finalize_current_deed_to_ir_output",
            return_value=normalize_finalizer_agent_visible_result(
                {
                    "executed": True,
                    "outputs": {
                        "finalization_status": "published",
                        "final_package_preview_ref": "deed_to_ir:preview:p1",
                        "output_revision_ref": "deed_to_ir:output:o1",
                        "next_required_action": "complete_run",
                    },
                }
            ),
        ),
    ):
        by_id = {b.tool_id: b.handler for b in surface.tool_bindings}
        save_result = by_id["save_ir_artifact"]({"feature_graph": {"graph_id": "g", "nodes": [], "edges": []}})
        patch_result = by_id["patch_ir_draft"]({"base_draft_ref": "feature_graph:ir:v1"})
        submit_result = by_id["submit_ir_for_mapping"]({"ir_artifact_ref": "feature_graph:ir:v2"})
        finalize_result = by_id["finalize_current_deed_to_ir_output"]({})
        for action_id, result in (
            ("save_ir_artifact", save_result),
            ("patch_ir_draft", patch_result),
            ("submit_ir_for_mapping", submit_result),
            ("finalize_current_deed_to_ir_output", finalize_result),
        ):
            assert "agent_result_view" in result, action_id
            view, om = normalize_agent_result_view_pair(result["agent_result_view"], None)
            assert om is None and view is not None
            assert view.continuity_key == build_working_head_continuity_key(**_SCOPE)

        describe = by_id["describe_feature_graph_capabilities"]({})
        assert "agent_result_view" not in describe

        with patch(
            "domains.mapping.deed_to_ir.runtime_adapter.composition.list_feature_graph_artifacts",
            return_value={"executed": True, "outputs": {"artifacts": []}},
        ):
            listed = by_id["list_feature_graph_artifacts"]({})
        assert "agent_result_view" not in listed

        hydrate_input = by_id["hydrate_deed_to_ir_input"]({"sections": ["issues"]})
        assert "agent_result_view" not in hydrate_input


def test_executor_normalization_preserves_attached_views() -> None:
    continuity = build_working_head_continuity_key(**_SCOPE)
    assert continuity is not None

    executor = ExecutionExecutor()
    executor.register(
        "save_ir_artifact",
        wrap_handler_with_result_view(
            lambda _r: {
                "executed": True,
                "outputs": _draft_outputs(current_ref="feature_graph:ir:v1"),
            },
            action_id="save_ir_artifact",
            **_SCOPE,
        ),
    )
    result = executor.execute(
        ExecutionStepRequest(session_id="s1", action_id="save_ir_artifact", idempotency_key="k1")
    )
    assert result.agent_result_view is not None
    assert result.agent_result_view.schema_id == SCHEMA_SAVE_IR_ARTIFACT
    assert result.agent_result_view.continuity_key == continuity
    assert result.agent_result_view_omitted is None
    assert isinstance(result.outputs["world_bbox"], tuple)

    adr = ActionDispatchResult(
        action_id="save_ir_artifact",
        executed=True,
        outputs=dict(result.outputs),
        agent_result_view=result.agent_result_view,
    )
    wire = action_dispatch_result_to_wire(adr)
    restored = action_dispatch_result_from_wire(wire)
    assert restored is not None
    assert restored.agent_result_view is not None
    assert restored.agent_result_view.schema_id == SCHEMA_SAVE_IR_ARTIFACT
    assert restored.agent_result_view.continuity_key == continuity


# --- Pre-commit pressure / ownership regressions ----------------------------


def test_finalizer_capacity_session_preserves_missing_ids() -> None:
    from domains.mapping.deed_to_ir.payloads.published_output import (
        MAX_EXTERNAL_DEPENDENCIES,
        MAX_SCOPE_RESULTS,
        MAX_UPSTREAM_CORRECTIONS,
    )

    continuity = build_working_head_continuity_key(**_SCOPE)
    scope_ids = [f"scope-{'s' * 90}-{i:02d}" for i in range(MAX_SCOPE_RESULTS)]
    correction_ids = [f"corr-{'c' * 90}-{i:02d}" for i in range(MAX_UPSTREAM_CORRECTIONS)]
    dependency_ids = [f"dep-{'d' * 90}-{i:02d}" for i in range(MAX_EXTERNAL_DEPENDENCIES)]
    # Accept half the scopes so missing lists stay large but accepted decisions exist.
    accepted_scopes = {scope_ids[i]: "handoffable" for i in range(0, MAX_SCOPE_RESULTS, 2)}
    missing = {
        "scope_ids": [sid for sid in scope_ids if sid not in accepted_scopes],
        "correction_ids": list(correction_ids),
        "dependency_ids": list(dependency_ids),
        "rationale_ids": [],
    }
    session = {
        "status": "pending_decisions",
        "lineage": {
            "mapping_artifact_ref": "feature_graph:mapping:m1",
            "source_ir_artifact_ref": "feature_graph:ir:v1",
        },
        "requirements": {
            "scope_ids": scope_ids,
            "correction_candidates": [{"target_entity_id": cid} for cid in correction_ids],
            "dependency_candidates": [{"candidate_id": did} for did in dependency_ids],
        },
        "decisions": {
            "scope_statuses": accepted_scopes,
            "correction_dispositions": {},
            "dependency_dispositions": {},
            "rationales": {},
        },
        "diagnostics": [
            {"code": "finalization_requirements_capacity_exceeded", "lane": "scope_ids"}
        ],
    }
    result = {
        "executed": False,
        "refusal": {
            "reason_code": "missing_finalization_decisions",
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "missing": missing,
            "active_finalization_session": session,
            "next_required_action": "finalize_current_deed_to_ir_output",
        },
    }
    view, omitted = build_finalize_current_output_view(result, continuity_key=continuity)
    assert omitted is None and view is not None
    chars = _measure_view(view)
    assert chars <= MAX_AGENT_RESULT_VIEW_CHARS
    assert view.payload["missing"]["scope_ids"] == missing["scope_ids"]
    assert view.payload["missing"]["correction_ids"] == missing["correction_ids"]
    assert view.payload["missing"]["dependency_ids"] == missing["dependency_ids"]
    session_payload = view.payload.get("active_finalization_session")
    if session_payload is not None:
        assert "missing" not in session_payload
        assert "scope_ids" not in (session_payload.get("requirements") or {})
        assert session_payload["requirement_counts"]["scope_ids"] == MAX_SCOPE_RESULTS
        assert session_payload["requirement_counts"]["correction_ids"] == MAX_UPSTREAM_CORRECTIONS
        assert session_payload["requirement_counts"]["dependency_ids"] == MAX_EXTERNAL_DEPENDENCIES
        assert session_payload["decisions"]["scope_statuses"] == accepted_scopes
    else:
        assert view.payload["active_finalization_session_omitted"]["reason"] == "view_budget"
    assert chars < 15_399
    # Expose measured size for the completion report via assertion message.
    assert chars > 0, f"capacity envelope chars={chars}"


def test_finalizer_does_not_infer_published_status() -> None:
    continuity = build_working_head_continuity_key(**_SCOPE)
    view, omitted = build_finalize_current_output_view(
        {
            "executed": True,
            "outputs": {
                "final_package_preview_ref": "deed_to_ir:preview:p1",
                "output_revision_ref": "deed_to_ir:output:o1",
                "next_required_action": "complete_run",
            },
        },
        continuity_key=continuity,
    )
    assert omitted is None and view is not None
    assert "finalization_status" not in view.payload


def test_draft_oversized_nested_gap_keeps_current_ir_identity() -> None:
    continuity = build_working_head_continuity_key(**_SCOPE)
    outputs = _draft_outputs(current_ref="feature_graph:ir:v1")
    outputs["current_draft_ir"]["compile_gaps"] = [
        {"code": "huge_gap", "message": "G" * 20_000}
    ]
    outputs["current_draft_ir"]["judge_findings"] = [{"code": "ok", "message": "fine"}]
    view, omitted = build_save_ir_artifact_view(outputs, continuity_key=continuity)
    assert omitted is None and view is not None
    assert view.payload["current_ir_artifact_ref"] == "feature_graph:ir:v1"
    assert "compile_gaps" not in view.payload.get("current_draft_ir", {})
    assert view.payload.get("compile_gaps_omitted_count") == 1
    assert view.payload.get("compile_gaps") in (None, [])
    assert view.payload.get("judge_findings") == [{"code": "ok", "message": "fine"}]
    assert _measure_view(view) <= MAX_AGENT_RESULT_VIEW_CHARS
    assert ("G" * 40) not in json.dumps(view.payload)


def test_intake_omission_counts_equal_original_valid_rows() -> None:
    from domains.mapping.deed_to_ir.execution.result_view_common import (
        MAX_COLLECTION_ROWS,
        fit_payload_collections,
        mapping_rows,
    )

    continuity = build_working_head_continuity_key(**_SCOPE)
    raw = [{"code": f"row_{i}", "message": f"m{i}"} for i in range(40)]
    raw.extend(["not-a-mapping", 42, None])  # malformed: skipped, not counted
    rows, intake_omitted = mapping_rows(raw)
    assert len(rows) == MAX_COLLECTION_ROWS
    assert intake_omitted == 40 - MAX_COLLECTION_ROWS
    view, omitted = fit_payload_collections(
        schema_id=SCHEMA_SAVE_IR_ARTIFACT,
        continuity_key=continuity,
        base={"current_ir_artifact_ref": "feature_graph:ir:v1"},
        collections={"compile_gaps": rows},
        intake_omitted={"compile_gaps": intake_omitted},
    )
    assert omitted is None and view is not None
    kept = view.payload.get("compile_gaps") or []
    omitted_count = int(view.payload.get("compile_gaps_omitted_count") or 0)
    assert len(kept) + omitted_count == 40
    assert omitted_count >= intake_omitted


def test_intake_and_pressure_omissions_combine() -> None:
    from domains.mapping.deed_to_ir.execution.result_view_common import (
        MAX_COLLECTION_ROWS,
        fit_payload_collections,
        mapping_rows,
    )

    continuity = build_working_head_continuity_key(**_SCOPE)
    raw = [{"code": f"gap_{i}", "message": ("M" * 3500) + f"_{i}"} for i in range(40)]
    rows, intake_omitted = mapping_rows(raw)
    assert intake_omitted == 40 - MAX_COLLECTION_ROWS
    view, omitted = fit_payload_collections(
        schema_id=SCHEMA_SAVE_IR_ARTIFACT,
        continuity_key=continuity,
        base={"current_ir_artifact_ref": "feature_graph:ir:v1", "draft_version": "v1"},
        collections={"compile_gaps": rows},
        intake_omitted={"compile_gaps": intake_omitted},
    )
    assert omitted is None and view is not None
    kept = view.payload.get("compile_gaps") or []
    omitted_count = int(view.payload.get("compile_gaps_omitted_count") or 0)
    assert len(kept) + omitted_count == 40
    assert omitted_count > intake_omitted  # some fitted rows also dropped under pressure
    assert _measure_view(view) <= MAX_AGENT_RESULT_VIEW_CHARS


def test_mapping_long_summary_does_not_evict_repair_guidance() -> None:
    continuity = build_working_head_continuity_key(**_SCOPE)
    outputs = _mapping_outputs(
        mapping_ref="feature_graph:mapping:m1",
        ir_ref="feature_graph:ir:v1",
    )
    outputs["mapping_review"]["sanity_review"]["summary"] = "S" * 20_000
    view, omitted = build_submit_ir_for_mapping_view(outputs, continuity_key=continuity)
    assert omitted is None and view is not None
    assert _measure_view(view) <= MAX_AGENT_RESULT_VIEW_CHARS
    assert view.payload["current_mapping_lineage"]["mapping_artifact_ref"] == (
        "feature_graph:mapping:m1"
    )
    sanity = view.payload["mapping_review"]["sanity_review"]
    assert sanity["conclusion"] == "needs_repair"
    assert sanity.get("summary_omitted") is True
    assert sanity.get("summary_chars") == 20_000
    assert "summary" not in sanity or len(str(sanity.get("summary") or "")) <= 240
    assert ("S" * 40) not in json.dumps(view.payload)
    assert view.payload["mapping_review"]["correction_posture"]["active"] is True
    assert view.payload["mapping_review"]["draft_patch_targets"][0]["node_id"] == "n1"
    assert "active_finalization_session" in view.payload or view.payload.get(
        "active_finalization_session_omitted", {}
    ).get("reason") == "view_budget"


def test_no_duplicate_retired_action_registry_in_common() -> None:
    import domains.mapping.deed_to_ir.execution.result_view_common as common

    assert not hasattr(common, "RETIRED_FINALIZATION_ACTION_IDS")
    assert not hasattr(common, "scrub_retired_finalizer_fields")
    assert not hasattr(common, "_STRIP_FINALIZER_KEYS")


def test_draft_compactor_truncation_omissions_are_counted() -> None:
    continuity = build_working_head_continuity_key(**_SCOPE)
    outputs = _draft_outputs(current_ref="feature_graph:ir:v1")
    outputs["current_draft_ir"]["nodes"] = [{"id": f"n{i}"} for i in range(40)]
    outputs["current_draft_ir"]["node_count"] = 40
    outputs["current_draft_ir"]["compile_gaps"] = [
        {"code": f"gap_{i}", "message": f"m{i}"} for i in range(20)
    ]
    outputs["current_draft_ir"]["compile_gap_count"] = 20
    view, omitted = build_save_ir_artifact_view(outputs, continuity_key=continuity)
    assert omitted is None and view is not None
    nodes = view.payload.get("nodes") or []
    nodes_omitted = int(view.payload.get("nodes_omitted_count") or 0)
    assert len(nodes) + nodes_omitted == 40
    gaps = view.payload.get("compile_gaps") or []
    gaps_omitted = int(view.payload.get("compile_gaps_omitted_count") or 0)
    assert len(gaps) + gaps_omitted == 20


def test_mapping_bounds_oversized_conclusion_without_evicting_repair() -> None:
    continuity = build_working_head_continuity_key(**_SCOPE)
    outputs = _mapping_outputs(
        mapping_ref="feature_graph:mapping:m1",
        ir_ref="feature_graph:ir:v1",
    )
    outputs["mapping_review"]["sanity_review"]["conclusion"] = "C" * 20_000
    outputs["mapping_review"]["sanity_review"]["status"] = {"not": "a-string"}
    view, omitted = build_submit_ir_for_mapping_view(outputs, continuity_key=continuity)
    assert omitted is None and view is not None
    sanity = view.payload["mapping_review"]["sanity_review"]
    assert sanity.get("conclusion_omitted") is True
    assert sanity.get("conclusion_chars") == 20_000
    assert "conclusion" not in sanity
    assert "status" not in sanity
    assert ("C" * 40) not in json.dumps(view.payload)
    assert view.payload["mapping_review"]["correction_posture"]["active"] is True
    assert view.payload["mapping_review"]["draft_patch_targets"][0]["node_id"] == "n1"


def test_session_diagnostics_drop_before_whole_session() -> None:
    from domains.mapping.deed_to_ir.execution.finalization_result_views import (
        resolve_session_summary_for_envelope,
    )

    core = {
        "status": "pending_decisions",
        "lineage": {
            "mapping_artifact_ref": "feature_graph:mapping:m1",
            "source_ir_artifact_ref": "feature_graph:ir:v1",
        },
        "allowed_values": {"scope_statuses": ["handoffable", "blocked"]},
        "requirement_counts": {"scope_ids": 1, "correction_ids": 0, "dependency_ids": 0},
        "decisions": {"scope_statuses": {"parcel_1": "handoffable"}},
    }
    huge_diags = [{"code": f"d{i}", "message": "D" * 2000} for i in range(20)]
    summary = {**core, "diagnostics": huge_diags}

    calls: list[bool] = []

    def fits(candidate):
        # Full summary with diagnostics does not fit; core without diagnostics does.
        ok = "diagnostics" not in candidate
        calls.append(ok)
        return ok

    resolved, markers = resolve_session_summary_for_envelope(summary, fits=fits)
    assert markers == {}
    assert resolved is not None
    assert "diagnostics" not in resolved
    assert resolved["diagnostics_omitted_count"] == 20
    assert resolved["diagnostics_omitted"]["reason"] == "view_budget"
    assert resolved["status"] == "pending_decisions"
    assert resolved["lineage"]["mapping_artifact_ref"] == "feature_graph:mapping:m1"


def test_lineage_fallback_uses_top_level_ir_ref() -> None:
    continuity = build_working_head_continuity_key(**_SCOPE)
    outputs = {
        "mapping_artifact_ref": "feature_graph:mapping:m9",
        "ir_artifact_ref": "feature_graph:ir:top-level",
        "compiled_feature_count": 1,
    }
    view, omitted = build_submit_ir_for_mapping_view(outputs, continuity_key=continuity)
    assert omitted is None and view is not None
    assert view.payload["current_mapping_lineage"]["mapping_artifact_ref"] == (
        "feature_graph:mapping:m9"
    )
    assert view.payload["current_mapping_lineage"]["source_ir_artifact_ref"] == (
        "feature_graph:ir:top-level"
    )
    assert view.payload["ir_artifact_ref"] == "feature_graph:ir:top-level"
