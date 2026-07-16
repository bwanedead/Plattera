"""Deterministic tests for compact current-head finalizer (D2IR-BR-013)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from domains.mapping.deed_to_ir.payloads.finalize_current_output_tool_schema import (
    build_finalize_current_deed_to_ir_output_request_json_shape,
)
from domains.mapping.deed_to_ir.payloads.published_output import ALLOWED_CLOSURE_DIMENSION_IDS
from tooling.mapping.deed_to_ir.finalization_decisions import (
    convert_compact_decisions_to_prepare_inputs,
    evaluate_merged_finalization_completeness,
    merge_finalization_decisions,
    validate_compact_finalization_decisions,
)
from tooling.mapping.deed_to_ir.finalization_session import (
    REQUIREMENTS_CAPACITY_EXCEEDED,
    SCOPE_INVENTORY_UNAVAILABLE,
    STATUS_PENDING_DECISIONS,
    STATUS_PREVIEW_READY,
    STATUS_PUBLISHED,
    STATUS_STALE,
    build_pending_finalization_session,
    compact_finalization_session_for_prompt,
    empty_finalization_decisions,
)
from tooling.mapping.deed_to_ir.finalization_session_persistence import (
    read_finalization_session,
    write_finalization_session,
)
from tooling.mapping.deed_to_ir.finalize_current_output import finalize_current_deed_to_ir_output
from tooling.mapping.deed_to_ir.preview_refs import PREVIEW_REV_PREFIX
from tooling.mapping.deed_to_ir.test_correction_posture import (
    _PRACTICE_CORRECT_DISTANCE,
    _resolution_snapshot,
)
from tooling.mapping.deed_to_ir.test_mapping_lineage_intent_first import _submit_with_lineage


def _assert_revision_preview_ref(ref: str | None) -> None:
    assert isinstance(ref, str) and ref.startswith(PREVIEW_REV_PREFIX)
    digits = ref[len(PREVIEW_REV_PREFIX) :]
    assert digits.isdigit() and len(digits) == 4


def _assert_retryable(result: dict, code: str) -> None:
    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == code
    assert result["refusal"]["retryable"] is True


def _complete_request(**overrides):
    base = {
        "scope_statuses": {"parcel_1": "handoffable", "parcel_2": "blocked"},
        "correction_dispositions": {"p1_call2_distance": "confirmed_source_repair"},
        "dependency_dispositions": {"parcel_2_continuation_scope": "include"},
        "rationales": {},
    }
    base.update(overrides)
    return base


def _finalize(persistence, ctx, **decision_maps):
    return finalize_current_deed_to_ir_output(
        dossier_id="d-preview",
        transcription_id=ctx["transcription_id"],
        workspace_id=ctx["workspace_id"],
        run_id=ctx["run_id"],
        transcript_edit_source_revision_ref=ctx["transcript_edit_source_revision_ref"],
        resolution_state_ref=ctx["resolution_state_ref"],
        resolution_state_snapshot=_resolution_snapshot(),
        persistence=persistence,
        **decision_maps,
    )


def _session_fixture(**overrides):
    session = build_pending_finalization_session(
        mapping_artifact_ref="feature_graph:mapping:m1",
        source_ir_artifact_ref="feature_graph:ir:i1",
        scope_ids=["parcel_1", "parcel_2"],
        correction_candidates=[
            {
                "target_entity_id": "p1_call2_distance",
                "inherited_value": "618",
                "selected_ir_display_value": "518",
            }
        ],
        dependency_candidates=[
            {
                "candidate_id": "parcel_2_continuation_scope",
                "dependency_id": "parcel_2_continuation_scope",
                "affected_scope": "parcel_2",
                "description": "Continuation unavailable.",
            }
        ],
    )
    session.update(overrides)
    return session


# --- Schema ---


def test_action_schema_accepts_four_optional_maps() -> None:
    shape = build_finalize_current_deed_to_ir_output_request_json_shape()
    assert shape["type"] == "object"
    assert shape["additionalProperties"] is False
    props = shape["properties"]
    assert set(props) == {
        "scope_statuses",
        "correction_dispositions",
        "dependency_dispositions",
        "rationales",
    }
    assert props["scope_statuses"]["additionalProperties"]["enum"] == [
        "handoffable",
        "blocked",
    ]
    assert "confirmed_source_repair" in props["correction_dispositions"]["additionalProperties"][
        "enum"
    ]
    assert props["dependency_dispositions"]["additionalProperties"]["enum"] == [
        "include",
        "not_applicable",
    ]


def test_action_schema_rejects_artifact_refs_and_unknown_fields() -> None:
    shape = build_finalize_current_deed_to_ir_output_request_json_shape()
    props = shape["properties"]
    for forbidden in (
        "mapping_artifact_ref",
        "ir_artifact_ref",
        "final_package_preview_ref",
        "use_current_mapping_lineage",
        "scope_dispositions",
        "closure_dispositions",
        "upstream_corrections",
        "resolution_used_by_ir",
    ):
        assert forbidden not in props
    assert shape["additionalProperties"] is False


# --- Preflight refusals ---


def test_missing_session_refusal(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        from tooling.mapping.deed_to_ir.test_final_package_preview import (
            _context,
            _patch_deed_root,
            _services,
        )

        _patch_deed_root(monkeypatch, tmp)
        ctx = _context()
        persistence = _services(tmp)
        result = _finalize(persistence, ctx)
        _assert_retryable(result, "finalization_session_missing")


def test_stale_session_refusal(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, _submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        session = read_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert session is not None
        stale = dict(session)
        stale["status"] = STATUS_STALE
        stale["stale"] = True
        write_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
            session=stale,
        )
        result = _finalize(persistence, ctx)
        _assert_retryable(result, "finalization_session_stale")


def test_lineage_mismatch_refusal(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, _submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        session = read_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert session is not None
        mismatched = dict(session)
        mismatched["lineage"] = {
            "mapping_artifact_ref": "feature_graph:mapping:other",
            "source_ir_artifact_ref": session["lineage"]["source_ir_artifact_ref"],
        }
        write_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
            session=mismatched,
        )
        result = _finalize(persistence, ctx)
        _assert_retryable(result, "finalization_session_stale")


def test_scope_inventory_diagnostic_refusal(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, mapping_ref, _submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        session = read_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert session is not None
        broken = dict(session)
        broken["requirements"] = {
            "scope_ids": [],
            "correction_candidates": [],
            "dependency_candidates": [],
        }
        broken["diagnostics"] = [{"code": SCOPE_INVENTORY_UNAVAILABLE, "message": "empty"}]
        write_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
            session=broken,
        )
        result = _finalize(persistence, ctx, **_complete_request())
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "finalization_scope_inventory_unavailable"
        assert result["refusal"]["retryable"] is False
        _ = mapping_ref


def test_capacity_diagnostic_refusal(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, _submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        session = read_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert session is not None
        over = dict(session)
        over["diagnostics"] = [
            {
                "code": REQUIREMENTS_CAPACITY_EXCEEDED,
                "lane": "scope_ids",
                "observed_count": 99,
                "maximum_count": 32,
            }
        ]
        write_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
            session=over,
        )
        result = _finalize(persistence, ctx, **_complete_request())
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "finalization_requirements_capacity_exceeded"
        assert result["refusal"]["retryable"] is False


# --- Decision validation / merge ---


def test_empty_request_returns_exact_missing_ids(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, _submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        result = _finalize(persistence, ctx)
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "missing_finalization_decisions"
        missing = result["outputs"]["missing"]
        assert "parcel_1" in missing["scope_ids"]
        assert "parcel_2" in missing["scope_ids"]
        assert "p1_call2_distance" in missing["correction_ids"]
        assert "parcel_2_continuation_scope" in missing["dependency_ids"]
        assert missing["rationale_ids"] == []


def test_valid_partial_decisions_persist(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, _submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        result = _finalize(
            persistence,
            ctx,
            scope_statuses={"parcel_1": "handoffable"},
        )
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "missing_finalization_decisions"
        disk = read_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert disk is not None
        assert disk["decisions"]["scope_statuses"]["parcel_1"] == "handoffable"
        assert "parcel_2" in result["outputs"]["missing"]["scope_ids"]


def test_previously_accepted_decisions_need_not_be_resubmitted(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, _submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        first = _finalize(
            persistence,
            ctx,
            scope_statuses={"parcel_1": "handoffable", "parcel_2": "blocked"},
            correction_dispositions={"p1_call2_distance": "confirmed_source_repair"},
        )
        assert first["refusal"]["reason_code"] == "missing_finalization_decisions"
        second = _finalize(
            persistence,
            ctx,
            dependency_dispositions={"parcel_2_continuation_scope": "include"},
        )
        assert second["executed"] is True
        assert second["outputs"]["finalization_status"] == "published"


def test_unknown_ids_cause_no_mutation(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, _submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        before = read_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        result = _finalize(
            persistence,
            ctx,
            scope_statuses={"parcel_99": "handoffable"},
        )
        _assert_retryable(result, "finalization_decision_unknown_id")
        after = read_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert after is not None and before is not None
        assert after["decisions"] == before["decisions"]


def test_invalid_values_cause_no_mutation(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, _submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        before = read_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        result = _finalize(
            persistence,
            ctx,
            scope_statuses={"parcel_1": "ready"},
        )
        _assert_retryable(result, "finalization_decision_invalid")
        after = read_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert after is not None and before is not None
        assert after["decisions"] == before["decisions"]


def test_exceptional_correction_missing_rationale_remains_unresolved() -> None:
    session = _session_fixture()
    validated = validate_compact_finalization_decisions(
        session=session,
        request={
            "scope_statuses": {"parcel_1": "handoffable", "parcel_2": "blocked"},
            "correction_dispositions": {"p1_call2_distance": "ir_only_exception"},
            "dependency_dispositions": {"parcel_2_continuation_scope": "include"},
        },
    )
    assert validated.get("ok") is True
    merged = merge_finalization_decisions(session=session, incoming=validated["incoming"])
    completeness = evaluate_merged_finalization_completeness(merged)
    assert completeness["complete"] is False
    assert "p1_call2_distance" in completeness["missing"]["rationale_ids"]


def test_dependency_decline_missing_rationale_remains_unresolved() -> None:
    session = _session_fixture()
    validated = validate_compact_finalization_decisions(
        session=session,
        request={
            "scope_statuses": {"parcel_1": "handoffable", "parcel_2": "blocked"},
            "correction_dispositions": {"p1_call2_distance": "confirmed_source_repair"},
            "dependency_dispositions": {"parcel_2_continuation_scope": "not_applicable"},
        },
    )
    assert validated.get("ok") is True
    merged = merge_finalization_decisions(session=session, incoming=validated["incoming"])
    completeness = evaluate_merged_finalization_completeness(merged)
    assert completeness["complete"] is False
    assert "parcel_2_continuation_scope" in completeness["missing"]["rationale_ids"]


# --- Conversion ---


def test_confirmed_source_repair_conversion() -> None:
    session = _session_fixture()
    converted = convert_compact_decisions_to_prepare_inputs(
        session=session,
        scope_statuses={"parcel_1": "handoffable", "parcel_2": "blocked"},
        correction_dispositions={"p1_call2_distance": "confirmed_source_repair"},
        dependency_dispositions={"parcel_2_continuation_scope": "include"},
        rationales={},
    )
    assert converted.get("ok") is True
    row = converted["correction_decisions"][0]
    assert row["posture"] == "confirmed_from_source"
    assert row["resolution_used_by_ir"] is True
    assert row["recommended_action"] == "transcript_amendment"
    assert "p1_call2_distance" in row["rationale"]
    assert "518" in row["rationale"]
    assert "618" in row["rationale"]


def test_ir_only_exception_conversion() -> None:
    session = _session_fixture()
    converted = convert_compact_decisions_to_prepare_inputs(
        session=session,
        scope_statuses={"parcel_1": "handoffable", "parcel_2": "blocked"},
        correction_dispositions={"p1_call2_distance": "ir_only_exception"},
        dependency_dispositions={"parcel_2_continuation_scope": "include"},
        rationales={"p1_call2_distance": "IR-only exception for scoped handoff."},
    )
    assert converted.get("ok") is True
    row = converted["correction_decisions"][0]
    assert row["posture"] == "suspected"
    assert row["recommended_action"] == "ir_only_note"
    assert row["rationale"] == "IR-only exception for scoped handoff."


def test_needs_hitl_prevents_preview_and_publication(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, _submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        with patch(
            "tooling.mapping.deed_to_ir.finalize_current_output.prepare_deed_to_ir_final_package"
        ) as prepare_mock, patch(
            "tooling.mapping.deed_to_ir.finalize_current_output.publish_deed_to_ir_output"
        ) as publish_mock:
            result = _finalize(
                persistence,
                ctx,
                **_complete_request(
                    correction_dispositions={"p1_call2_distance": "needs_hitl"},
                ),
            )
            assert result["executed"] is False
            assert result["refusal"]["reason_code"] == "finalization_requires_hitl"
            assert result["refusal"]["retryable"] is True
            prepare_mock.assert_not_called()
            publish_mock.assert_not_called()
        disk = read_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert disk is not None
        assert disk["status"] == STATUS_PENDING_DECISIONS
        assert disk["decisions"]["correction_dispositions"]["p1_call2_distance"] == "needs_hitl"
        assert disk["preview_ref"] is None


def test_dependency_include_and_decline_conversion() -> None:
    session = _session_fixture()
    included = convert_compact_decisions_to_prepare_inputs(
        session=session,
        scope_statuses={"parcel_1": "handoffable", "parcel_2": "blocked"},
        correction_dispositions={"p1_call2_distance": "confirmed_source_repair"},
        dependency_dispositions={"parcel_2_continuation_scope": "include"},
        rationales={},
    )
    assert included["dependency_decisions"] == [
        {
            "candidate_id": "parcel_2_continuation_scope",
            "disposition": "include",
            "status": "blocked",
        }
    ]
    declined = convert_compact_decisions_to_prepare_inputs(
        session=session,
        scope_statuses={"parcel_1": "handoffable", "parcel_2": "handoffable"},
        correction_dispositions={"p1_call2_distance": "confirmed_source_repair"},
        dependency_dispositions={"parcel_2_continuation_scope": "not_applicable"},
        rationales={"parcel_2_continuation_scope": "Not in scoped handoff."},
    )
    assert declined["dependency_decisions"] == [
        {
            "candidate_id": "parcel_2_continuation_scope",
            "disposition": "not_applicable",
            "rationale": "Not in scoped handoff.",
        }
    ]


def test_included_dependency_versus_handoffable_scope_conflict() -> None:
    session = _session_fixture()
    converted = convert_compact_decisions_to_prepare_inputs(
        session=session,
        scope_statuses={"parcel_1": "handoffable", "parcel_2": "handoffable"},
        correction_dispositions={"p1_call2_distance": "confirmed_source_repair"},
        dependency_dispositions={"parcel_2_continuation_scope": "include"},
        rationales={},
    )
    assert converted.get("executed") is False
    assert converted["refusal"]["reason_code"] == "finalization_scope_dependency_conflict"
    assert converted["refusal"]["retryable"] is True


def test_four_closure_rows_generated_closed() -> None:
    session = _session_fixture()
    converted = convert_compact_decisions_to_prepare_inputs(
        session=session,
        scope_statuses={"parcel_1": "handoffable", "parcel_2": "blocked"},
        correction_dispositions={"p1_call2_distance": "confirmed_source_repair"},
        dependency_dispositions={"parcel_2_continuation_scope": "include"},
        rationales={},
    )
    closures = converted["closure_dispositions"]
    assert {row["dimension_id"] for row in closures} == set(ALLOWED_CLOSURE_DIMENSION_IDS)
    assert all(row["status"] == "closed" for row in closures)


# --- Orchestration / publication ---


def test_successful_prepare_persists_preview_ready_before_publication(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, _submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        seen_statuses: list[str] = []
        original_write = write_finalization_session

        def _tracking_write(**kwargs):
            session = kwargs["session"]
            seen_statuses.append(str(session.get("status")))
            return original_write(**kwargs)

        monkeypatch.setattr(
            "tooling.mapping.deed_to_ir.finalize_current_output.write_finalization_session",
            _tracking_write,
        )
        result = _finalize(persistence, ctx, **_complete_request())
        assert result["executed"] is True
        _assert_revision_preview_ref(result["outputs"]["final_package_preview_ref"])
        disk = read_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert disk is not None
        _assert_revision_preview_ref(disk["preview_ref"])
        assert STATUS_PREVIEW_READY in seen_statuses
        assert seen_statuses.index(STATUS_PREVIEW_READY) < seen_statuses.index(STATUS_PUBLISHED)


def test_publication_failure_retains_same_preview_ref(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, _submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        real_prepare = None
        from tooling.mapping.deed_to_ir import final_package_preview_persistence as prep_mod

        real_prepare = prep_mod.prepare_deed_to_ir_final_package

        def _prepare_then_fail_publish(*args, **kwargs):
            return real_prepare(*args, **kwargs)

        monkeypatch.setattr(
            "tooling.mapping.deed_to_ir.finalize_current_output.prepare_deed_to_ir_final_package",
            _prepare_then_fail_publish,
        )
        monkeypatch.setattr(
            "tooling.mapping.deed_to_ir.finalize_current_output.publish_deed_to_ir_output",
            lambda **kwargs: {
                "executed": False,
                "refusal": {
                    "reason_code": "publication_in_progress",
                    "retryable": False,
                    "blocked_by_invariant": True,
                    "blocked_by_budget": False,
                    "missing_inputs": [],
                },
                "outputs": {"error": {"code": "publication_in_progress", "message": "busy"}},
            },
        )
        result = _finalize(persistence, ctx, **_complete_request())
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "publication_in_progress"
        assert result["refusal"]["retryable"] is True
        assert result["refusal"]["blocked_by_invariant"] is False
        assert result["outputs"]["next_required_action"] == "finalize_current_deed_to_ir_output"
        disk = read_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert disk is not None
        assert disk["status"] == STATUS_PREVIEW_READY
        preview_ref = disk["preview_ref"]
        _assert_revision_preview_ref(preview_ref)
        assert result["outputs"]["final_package_preview_ref"] == preview_ref


def test_retry_from_preview_ready_does_not_create_another_preview(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, _submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        monkeypatch.setattr(
            "tooling.mapping.deed_to_ir.finalize_current_output.publish_deed_to_ir_output",
            lambda **kwargs: {
                "executed": False,
                "refusal": {
                    "reason_code": "publication_in_progress",
                    "retryable": False,
                    "blocked_by_invariant": True,
                    "blocked_by_budget": False,
                    "missing_inputs": [],
                },
                "outputs": {"error": {"code": "publication_in_progress", "message": "busy"}},
            },
        )
        first = _finalize(persistence, ctx, **_complete_request())
        assert first["executed"] is False
        disk = read_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert disk is not None
        preview_ref = disk["preview_ref"]
        preview_dir = (
            Path(tmp)
            / "artifacts"
            / "deed_to_ir"
            / "d-preview"
            / ctx["transcription_id"]
            / ctx["workspace_id"]
            / "final_package_preview"
        )
        first_revs = list(preview_dir.glob("rev_*.json"))
        assert len(first_revs) == 1

        prepare_calls = {"n": 0}
        real_prepare = None
        from tooling.mapping.deed_to_ir.final_package_preview_persistence import (
            prepare_deed_to_ir_final_package as _real,
        )

        real_prepare = _real

        def _counting_prepare(*args, **kwargs):
            prepare_calls["n"] += 1
            return real_prepare(*args, **kwargs)

        monkeypatch.setattr(
            "tooling.mapping.deed_to_ir.finalize_current_output.prepare_deed_to_ir_final_package",
            _counting_prepare,
        )
        monkeypatch.setattr(
            "tooling.mapping.deed_to_ir.finalize_current_output.publish_deed_to_ir_output",
            lambda **kwargs: {
                "executed": True,
                "artifact_refs": ["deed_to_ir:output", "deed_to_ir:output:rev:0001"],
                "outputs": {
                    "output_revision_ref": "deed_to_ir:output:rev:0001",
                    "mapping_artifact_ref": "feature_graph:mapping:m",
                    "ir_artifact_ref": "feature_graph:ir:i",
                    "final_package_preview_ref": preview_ref,
                },
            },
        )
        second = _finalize(persistence, ctx)
        assert second["executed"] is True
        assert prepare_calls["n"] == 0
        assert list(preview_dir.glob("rev_*.json")) == first_revs
        assert (
            read_finalization_session(
                dossier_id="d-preview",
                transcription_id=ctx["transcription_id"],
                workspace_id=ctx["workspace_id"],
                run_id=ctx["run_id"],
            )["preview_ref"]
            == preview_ref
        )


def test_retry_publication_uses_br012_idempotency(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, _submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        first = _finalize(persistence, ctx, **_complete_request())
        assert first["executed"] is True
        preview_ref = first["outputs"]["final_package_preview_ref"]
        output_ref = first["outputs"]["output_revision_ref"]
        second = _finalize(persistence, ctx)
        assert second["executed"] is True
        assert second["outputs"]["idempotent_replay"] is True
        assert second["outputs"]["final_package_preview_ref"] == preview_ref
        assert second["outputs"]["output_revision_ref"] == output_ref
        assert second["outputs"]["next_required_action"] == "complete_run"


def test_decision_mutation_after_preview_is_refused(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, _submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        monkeypatch.setattr(
            "tooling.mapping.deed_to_ir.finalize_current_output.publish_deed_to_ir_output",
            lambda **kwargs: {
                "executed": False,
                "refusal": {
                    "reason_code": "publication_in_progress",
                    "retryable": False,
                    "blocked_by_invariant": True,
                    "blocked_by_budget": False,
                    "missing_inputs": [],
                },
                "outputs": {"error": {"code": "publication_in_progress", "message": "busy"}},
            },
        )
        first = _finalize(persistence, ctx, **_complete_request())
        assert first["executed"] is False
        refused = _finalize(
            persistence,
            ctx,
            scope_statuses={"parcel_1": "blocked"},
        )
        _assert_retryable(refused, "finalization_decisions_frozen")


def test_successful_publication_persists_published_and_next_action(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, mapping_ref, _submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        result = _finalize(persistence, ctx, **_complete_request())
        assert result["executed"] is True
        outputs = result["outputs"]
        assert outputs["finalization_status"] == "published"
        assert outputs["next_required_action"] == "complete_run"
        _assert_revision_preview_ref(outputs["final_package_preview_ref"])
        assert outputs["output_revision_ref"]
        assert outputs["mapping_artifact_ref"] == mapping_ref or outputs["mapping_artifact_ref"]
        assert outputs["ir_artifact_ref"]
        disk = read_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert disk is not None
        assert disk["status"] == STATUS_PUBLISHED
        _assert_revision_preview_ref(disk["preview_ref"])
        assert disk["preview_ref"] == outputs["final_package_preview_ref"]
        assert disk["output_revision_ref"] == outputs["output_revision_ref"]


def test_published_replay_creates_no_preview_or_output(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, _submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        first = _finalize(persistence, ctx, **_complete_request())
        assert first["executed"] is True
        preview_dir = (
            Path(tmp)
            / "artifacts"
            / "deed_to_ir"
            / "d-preview"
            / ctx["transcription_id"]
            / ctx["workspace_id"]
            / "final_package_preview"
        )
        output_dir = (
            Path(tmp)
            / "artifacts"
            / "deed_to_ir"
            / "d-preview"
            / ctx["transcription_id"]
            / ctx["workspace_id"]
            / "output"
        )
        preview_revs = list(preview_dir.glob("rev_*.json"))
        output_revs = list(output_dir.glob("rev_*.json"))
        second = _finalize(persistence, ctx)
        assert second["executed"] is True
        assert second["outputs"]["idempotent_replay"] is True
        assert list(preview_dir.glob("rev_*.json")) == preview_revs
        assert list(output_dir.glob("rev_*.json")) == output_revs
        frozen = _finalize(
            persistence,
            ctx,
            scope_statuses={"parcel_1": "blocked"},
        )
        _assert_retryable(frozen, "finalization_decisions_frozen")


# --- Prompt projections ---


def test_pending_preview_ready_and_published_prompt_projections() -> None:
    pending = _session_fixture()
    compact_pending = compact_finalization_session_for_prompt(pending)
    assert compact_pending is not None
    assert compact_pending["status"] == STATUS_PENDING_DECISIONS
    assert "parcel_1" in compact_pending["missing"]["scope_ids"]
    assert "rationale_ids" in compact_pending["missing"]
    assert compact_pending["allowed_values"]["scope_statuses"] == ["handoffable", "blocked"]

    preview_ready = dict(pending)
    preview_ready["status"] = STATUS_PREVIEW_READY
    preview_ready["preview_ref"] = "deed_to_ir:final_package_preview:rev:0001"
    compact_ready = compact_finalization_session_for_prompt(preview_ready)
    assert compact_ready == {
        "status": STATUS_PREVIEW_READY,
        "final_package_preview_ref": "deed_to_ir:final_package_preview:rev:0001",
        "next_required_action": "finalize_current_deed_to_ir_output",
    }

    published = dict(preview_ready)
    published["status"] = STATUS_PUBLISHED
    published["output_revision_ref"] = "deed_to_ir:output:rev:0001"
    compact_published = compact_finalization_session_for_prompt(published)
    assert compact_published == {
        "status": STATUS_PUBLISHED,
        "output_revision_ref": "deed_to_ir:output:rev:0001",
        "final_package_preview_ref": "deed_to_ir:final_package_preview:rev:0001",
        "next_required_action": "complete_run",
    }

    stale = dict(pending)
    stale["status"] = STATUS_STALE
    assert compact_finalization_session_for_prompt(stale) is None


def test_prepare_and_publish_absent_from_agent_surface_but_callable_internally() -> None:
    from domains.mapping.deed_to_ir.execution.tool_specs import build_deed_to_ir_tool_specs
    from tooling.mapping.deed_to_ir.final_package_preview_persistence import prepare_deed_to_ir_final_package
    from tooling.mapping.deed_to_ir.output_persistence import publish_deed_to_ir_output

    ids = [spec.tool_id for spec in build_deed_to_ir_tool_specs()]
    assert "finalize_current_deed_to_ir_output" in ids
    assert "prepare_deed_to_ir_final_package" not in ids
    assert "publish_deed_to_ir_output" not in ids
    assert callable(prepare_deed_to_ir_final_package)
    assert callable(publish_deed_to_ir_output)


def test_no_deterministic_statuses_or_dispositions_before_agent_decisions() -> None:
    session = build_pending_finalization_session(
        mapping_artifact_ref="feature_graph:mapping:m1",
        source_ir_artifact_ref="feature_graph:ir:i1",
        scope_ids=["parcel_1"],
        correction_candidates=[{"target_entity_id": "p1_call2_distance"}],
        dependency_candidates=[
            {"candidate_id": "dep_1", "affected_scope": "parcel_1"},
        ],
    )
    assert session["status"] == STATUS_PENDING_DECISIONS
    assert session["decisions"] == empty_finalization_decisions()
    compact = compact_finalization_session_for_prompt(session)
    assert compact is not None
    assert "decisions" not in compact
    assert compact["missing"]["scope_ids"] == ["parcel_1"]
    assert compact["missing"]["correction_ids"] == ["p1_call2_distance"]
    assert compact["missing"]["dependency_ids"] == ["dep_1"]


# --- Persistence hard gates ---


def test_persistence_failure_after_decision_merge(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, _submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        before = read_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        with patch(
            "tooling.mapping.deed_to_ir.finalize_current_output.write_finalization_session",
            return_value=None,
        ), patch(
            "tooling.mapping.deed_to_ir.finalize_current_output.prepare_deed_to_ir_final_package"
        ) as prepare_mock, patch(
            "tooling.mapping.deed_to_ir.finalize_current_output.publish_deed_to_ir_output"
        ) as publish_mock:
            result = _finalize(persistence, ctx, **_complete_request())
            _assert_retryable(result, "finalization_session_persistence_failed")
            prepare_mock.assert_not_called()
            publish_mock.assert_not_called()
        after = read_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert after is not None and before is not None
        assert after["decisions"] == before["decisions"]


def test_persistence_failure_before_publication(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, _submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        real_write = write_finalization_session
        captured_revision: dict[str, str] = {}

        def _fail_preview_ready(**kwargs):
            session = kwargs["session"]
            if session.get("status") == STATUS_PREVIEW_READY:
                captured_revision["ref"] = str(session.get("preview_ref") or "")
                return None
            return real_write(**kwargs)

        with patch(
            "tooling.mapping.deed_to_ir.finalize_current_output.write_finalization_session",
            side_effect=_fail_preview_ready,
        ), patch(
            "tooling.mapping.deed_to_ir.finalize_current_output.publish_deed_to_ir_output"
        ) as publish_mock:
            result = _finalize(persistence, ctx, **_complete_request())
            _assert_retryable(result, "finalization_session_persistence_failed")
            publish_mock.assert_not_called()
        _assert_revision_preview_ref(captured_revision.get("ref"))
        assert result["outputs"]["final_package_preview_ref"] == captured_revision["ref"]
        disk = read_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert disk is not None
        assert disk["status"] == STATUS_PENDING_DECISIONS


def test_persistence_failure_after_publication(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, _submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        real_write = write_finalization_session

        def _fail_published(**kwargs):
            session = kwargs["session"]
            if session.get("status") == STATUS_PUBLISHED:
                return None
            return real_write(**kwargs)

        with patch(
            "tooling.mapping.deed_to_ir.finalize_current_output.write_finalization_session",
            side_effect=_fail_published,
        ):
            result = _finalize(persistence, ctx, **_complete_request())
            _assert_retryable(result, "finalization_session_persistence_failed")
        assert result["outputs"]["next_required_action"] == "finalize_current_deed_to_ir_output"
        _assert_revision_preview_ref(result["outputs"]["final_package_preview_ref"])
        assert result["outputs"]["output_revision_ref"]
        disk = read_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert disk is not None
        assert disk["status"] == STATUS_PREVIEW_READY
        _assert_revision_preview_ref(disk["preview_ref"])


# --- Malformed inputs / stored decisions ---


def test_malformed_decision_map_rejected_before_preview_publish(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, _submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        with patch(
            "tooling.mapping.deed_to_ir.finalize_current_output.publish_deed_to_ir_output",
            return_value={
                "executed": False,
                "refusal": {
                    "reason_code": "publication_in_progress",
                    "retryable": False,
                    "blocked_by_invariant": True,
                    "blocked_by_budget": False,
                    "missing_inputs": [],
                },
                "outputs": {"error": {"code": "publication_in_progress", "message": "busy"}},
            },
        ):
            first = _finalize(persistence, ctx, **_complete_request())
            assert first["executed"] is False
        disk = read_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert disk is not None
        assert disk["status"] == STATUS_PREVIEW_READY
        with patch(
            "tooling.mapping.deed_to_ir.finalize_current_output.publish_deed_to_ir_output"
        ) as publish_mock:
            result = _finalize(persistence, ctx, scope_statuses=["parcel_1"])
            _assert_retryable(result, "finalization_decision_invalid")
            publish_mock.assert_not_called()


def test_malformed_scalar_map_rejected_on_pending(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, _submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        with patch(
            "tooling.mapping.deed_to_ir.finalize_current_output.prepare_deed_to_ir_final_package"
        ) as prepare_mock:
            result = _finalize(persistence, ctx, rationales="not-a-map")
            _assert_retryable(result, "finalization_decision_invalid")
            prepare_mock.assert_not_called()


def test_invalid_stored_value_refuses_without_prepare(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, _submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        session = read_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert session is not None
        corrupted = dict(session)
        corrupted["decisions"] = {
            "scope_statuses": {"parcel_1": "ready"},
            "correction_dispositions": {},
            "dependency_dispositions": {},
            "rationales": {},
        }
        write_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
            session=corrupted,
        )
        with patch(
            "tooling.mapping.deed_to_ir.finalize_current_output.prepare_deed_to_ir_final_package"
        ) as prepare_mock, patch(
            "tooling.mapping.deed_to_ir.finalize_current_output.publish_deed_to_ir_output"
        ) as publish_mock:
            result = _finalize(persistence, ctx, **_complete_request())
            _assert_retryable(result, "finalization_session_invalid")
            prepare_mock.assert_not_called()
            publish_mock.assert_not_called()


def test_unknown_stored_id_refuses_without_prepare(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, _submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        session = read_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert session is not None
        corrupted = dict(session)
        corrupted["decisions"] = {
            "scope_statuses": {"parcel_99": "handoffable"},
            "correction_dispositions": {},
            "dependency_dispositions": {},
            "rationales": {},
        }
        write_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
            session=corrupted,
        )
        with patch(
            "tooling.mapping.deed_to_ir.finalize_current_output.prepare_deed_to_ir_final_package"
        ) as prepare_mock, patch(
            "tooling.mapping.deed_to_ir.finalize_current_output.publish_deed_to_ir_output"
        ) as publish_mock:
            result = _finalize(persistence, ctx)
            _assert_retryable(result, "finalization_session_invalid")
            prepare_mock.assert_not_called()
            publish_mock.assert_not_called()


def test_malformed_stored_lane_refuses_without_prepare(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, _submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        session = read_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert session is not None
        corrupted = dict(session)
        corrupted["decisions"] = {
            "scope_statuses": ["parcel_1"],
            "correction_dispositions": {},
            "dependency_dispositions": {},
            "rationales": {},
        }
        write_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
            session=corrupted,
        )
        with patch(
            "tooling.mapping.deed_to_ir.finalize_current_output.prepare_deed_to_ir_final_package"
        ) as prepare_mock, patch(
            "tooling.mapping.deed_to_ir.finalize_current_output.publish_deed_to_ir_output"
        ) as publish_mock:
            result = _finalize(persistence, ctx)
            _assert_retryable(result, "finalization_session_invalid")
            prepare_mock.assert_not_called()
            publish_mock.assert_not_called()


def test_prepare_without_immutable_revision_ref_refuses_publish(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, _ir, _mapping, _submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )

        def _prepare_without_revision(**kwargs):
            return {
                "executed": True,
                "artifact_refs": ["deed_to_ir:final_package_preview"],
                "outputs": {
                    "final_package_preview_ref": "deed_to_ir:final_package_preview",
                    # intentionally omit final_package_preview_revision_ref
                },
            }

        with patch(
            "tooling.mapping.deed_to_ir.finalize_current_output.prepare_deed_to_ir_final_package",
            side_effect=_prepare_without_revision,
        ), patch(
            "tooling.mapping.deed_to_ir.finalize_current_output.publish_deed_to_ir_output"
        ) as publish_mock:
            result = _finalize(persistence, ctx, **_complete_request())
            assert result["executed"] is False
            assert (
                result["refusal"]["reason_code"]
                == "final_package_preview_revision_ref_missing"
            )
            assert result["refusal"]["retryable"] is True
            assert result["refusal"]["blocked_by_invariant"] is False
            assert result["outputs"]["next_required_action"] == "submit_ir_for_mapping"
            publish_mock.assert_not_called()
