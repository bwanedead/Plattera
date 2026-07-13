"""Tests for current mapping lineage persistence and intent-first prepare."""

from __future__ import annotations

import tempfile
from pathlib import Path

from domains.mapping.deed_to_ir.payloads.published_output import ALLOWED_CLOSURE_DIMENSION_IDS
from tooling.mapping.deed_to_ir.artifact_hydration import hydrate_artifact_refs
from tooling.mapping.deed_to_ir.final_package_preview_persistence import prepare_deed_to_ir_final_package
from tooling.mapping.deed_to_ir.ir_mapping_submission import submit_ir_for_mapping
from tooling.mapping.deed_to_ir.ir_persistence import save_ir_artifact
from tooling.mapping.deed_to_ir.mapping_lineage import (
    read_current_mapping_lineage,
)
from tooling.mapping.deed_to_ir.test_correction_posture import (
    _PRACTICE_CORRECT_DISTANCE,
    _resolution_snapshot,
    _source_repair_graph,
)
from tooling.mapping.deed_to_ir.test_final_package_preview import (
    _context,
    _patch_deed_root,
    _valid_rows,
)


def _compact_dispositions() -> dict:
    return {
        "scope_dispositions": [
            {"scope_id": "parcel_1", "status": "handoffable"},
            {"scope_id": "parcel_2", "status": "blocked"},
        ],
        "closure_dispositions": [
            {
                "dimension_id": dimension_id,
                "status": "partial" if dimension_id.endswith("scoped_completion") else "closed",
            }
            for dimension_id in sorted(ALLOWED_CLOSURE_DIMENSION_IDS)
        ],
    }


def _correction_decision() -> dict:
    return {
        "target_entity_id": "p1_call2_distance",
        "posture": "confirmed_from_source",
        "resolution_used_by_ir": True,
        "recommended_action": "transcript_amendment",
        "rationale": (
            "Targeted source evidence supports 518 feet and the repaired "
            "mapping is the intended scoped handoff."
        ),
    }


def _dependency_decision_include() -> dict:
    return {
        "candidate_id": "parcel_2_continuation_scope",
        "disposition": "include",
        "status": "blocked",
    }


def _load_latest_preview(*, tmp: str, ctx: dict) -> dict:
    preview_dir = (
        Path(tmp)
        / "artifacts"
        / "deed_to_ir"
        / "d-preview"
        / ctx["transcription_id"]
        / ctx["workspace_id"]
        / "final_package_preview"
    )
    revs = sorted(preview_dir.glob("rev_*.json"))
    assert revs, f"expected preview revisions under {preview_dir}"
    import json

    return json.loads(revs[-1].read_text(encoding="utf-8"))


def _submit_with_lineage(tmp: str, *, leg2_distance: float, monkeypatch):
    _patch_deed_root(monkeypatch, tmp)
    from tooling.mapping.deed_to_ir.test_final_package_preview import _services

    ctx = _context()
    persistence = _services(tmp)
    saved = save_ir_artifact(
        dossier_id="d-preview",
        feature_graph=_source_repair_graph(leg2_distance=leg2_distance).model_dump(mode="json"),
        artifact_id="ir_source_repair",
        draft_workspace_id=ctx["workspace_id"],
        draft_run_id=ctx["run_id"],
        transcription_id=ctx["transcription_id"],
        persistence=persistence,
    )
    assert saved["executed"] is True
    ir_ref = saved["outputs"]["ir_artifact_ref"]
    submitted = submit_ir_for_mapping(
        dossier_id="d-preview",
        ir_artifact_ref=ir_ref,
        persistence=persistence,
        resolution_state_snapshot=_resolution_snapshot(),
        transcription_id=ctx["transcription_id"],
        workspace_id=ctx["workspace_id"],
        run_id=ctx["run_id"],
    )
    assert submitted["executed"] is True
    mapping_ref = submitted["outputs"]["mapping_artifact_ref"]
    return persistence, ir_ref, mapping_ref, submitted, ctx


def test_submit_writes_current_mapping_lineage(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref, submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        lineage = submitted["outputs"]["current_mapping_lineage"]
        assert lineage["mapping_artifact_ref"] == mapping_ref or lineage["mapping_artifact_ref"] == submitted[
            "outputs"
        ]["mapping_artifact_ref"]
        assert lineage["source_ir_artifact_ref"] == ir_ref
        assert lineage["lineage_current"] is True
        assert lineage["use_for_next_preview"] is True
        assert lineage["stale"] is False

        disk = read_current_mapping_lineage(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert disk is not None
        assert disk["mapping_artifact_ref"] == submitted["outputs"]["mapping_artifact_ref"]
        assert disk["source_ir_artifact_ref"] == ir_ref


def test_save_marks_current_mapping_lineage_stale(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref, submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        graph = _source_repair_graph(leg2_distance=520.0).model_dump(mode="json")
        saved = save_ir_artifact(
            dossier_id="d-preview",
            feature_graph=graph,
            base_draft_ref=ir_ref,
            draft_workspace_id=ctx["workspace_id"],
            draft_run_id=ctx["run_id"],
            transcription_id=ctx["transcription_id"],
            persistence=persistence,
        )
        assert saved["executed"] is True
        lineage = saved["outputs"]["current_mapping_lineage"]
        assert lineage["stale"] is True
        assert lineage["use_for_next_preview"] is False
        assert lineage["lineage_current"] is False

        refused = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            persistence=persistence,
            use_current_mapping_lineage=True,
            reuse_agent_authored_finalization_state=True,
            resolution_state_snapshot=_resolution_snapshot(),
            **ctx,
        )
        assert refused["executed"] is False
        assert refused["refusal"]["reason_code"] == "current_mapping_lineage_stale"


def test_intent_first_prepare_fresh_workspace_no_prior_preview(monkeypatch) -> None:
    """Fresh corrupted-source repair: compact dispositions + dependency include succeed."""
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref, submitted, ctx = _submit_with_lineage(
            tmp,
            leg2_distance=_PRACTICE_CORRECT_DISTANCE,
            monkeypatch=monkeypatch,
        )
        preview_dir = (
            Path(tmp)
            / "artifacts"
            / "deed_to_ir"
            / "d-preview"
            / ctx["transcription_id"]
            / ctx["workspace_id"]
            / "final_package_preview"
        )
        assert not preview_dir.exists() or not any(preview_dir.glob("rev_*.json"))

        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            persistence=persistence,
            use_current_mapping_lineage=True,
            correction_decisions=[_correction_decision()],
            dependency_decisions=[_dependency_decision_include()],
            resolution_state_snapshot=_resolution_snapshot(),
            **ctx,
            **_compact_dispositions(),
        )
        assert result["executed"] is True
        outputs = result["outputs"]
        assert outputs["finalization_status"] == "preview_ready"
        assert outputs["selected_lineage"]["expected_ir_artifact_ref"] == ir_ref
        assert outputs["selected_lineage"]["mapping_artifact_ref"] == submitted["outputs"][
            "mapping_artifact_ref"
        ]
        assert outputs["external_dependency_count"] == 1
        summary = outputs["correction_summary"]
        assert summary["active"] is True
        assert summary["rows_created"] == 1
        target = summary["targets"][0]
        assert target["target_entity_id"] == "p1_call2_distance"
        assert "618" in str(target["upstream_value"])
        assert target["selected_ir_value"] == _PRACTICE_CORRECT_DISTANCE
        assert target["resolution_used_by_ir"] is True
        assert outputs["recommended_publish_request"]["final_package_preview_ref"]
        assert any(preview_dir.glob("rev_*.json"))

        preview = _load_latest_preview(tmp=tmp, ctx=ctx)
        scopes = {row["scope_id"]: row["status"] for row in preview["scope_results"]}
        assert scopes["parcel_1"] == "handoffable"
        assert scopes["parcel_2"] == "blocked"
        deps = preview["external_dependencies"]
        assert len(deps) == 1
        assert deps[0]["dependency_id"] == "parcel_2_continuation_scope"
        assert deps[0]["affected_scope"] == "parcel_2"
        assert deps[0]["status"] == "blocked"
        assert deps[0]["description"]
        corrections = preview["upstream_corrections"]
        assert len(corrections) == 1
        assert "618" in str(corrections[0].get("upstream_value") or "")
        assert "518" in str(corrections[0].get("corrected_value") or "") or (
            corrections[0].get("selected_ir_value") == _PRACTICE_CORRECT_DISTANCE
        )


def test_intent_first_prepare_dependency_decisions_required(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref, submitted, ctx = _submit_with_lineage(
            tmp,
            leg2_distance=_PRACTICE_CORRECT_DISTANCE,
            monkeypatch=monkeypatch,
        )
        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            persistence=persistence,
            use_current_mapping_lineage=True,
            correction_decisions=[_correction_decision()],
            resolution_state_snapshot=_resolution_snapshot(),
            **ctx,
            **_compact_dispositions(),
        )
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "missing_finalization_decisions"
        assert result["refusal"]["retryable"] is True
        assert result["refusal"]["blocked_by_invariant"] is False
        card = result["outputs"]["finalization_decision_card"]
        assert card["required_lanes"] == ["dependency_decisions"]
        assert card["dependency_decisions"][0]["candidate_id"] == "parcel_2_continuation_scope"
        assert card["dependency_decisions"][0]["affected_scope"] == "parcel_2"
        template = result["outputs"]["retry_request_template"]
        assert template["correction_decisions"][0]["target_entity_id"] == "p1_call2_distance"
        assert template["scope_dispositions"]


def test_intent_first_prepare_dependency_not_applicable_produces_no_row(
    monkeypatch,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref, submitted, ctx = _submit_with_lineage(
            tmp,
            leg2_distance=_PRACTICE_CORRECT_DISTANCE,
            monkeypatch=monkeypatch,
        )
        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            persistence=persistence,
            use_current_mapping_lineage=True,
            correction_decisions=[_correction_decision()],
            dependency_decisions=[
                {
                    "candidate_id": "parcel_2_continuation_scope",
                    "disposition": "not_applicable",
                    "rationale": "Continuation is already represented elsewhere in this handoff.",
                }
            ],
            resolution_state_snapshot=_resolution_snapshot(),
            **ctx,
            **_compact_dispositions(),
        )
        assert result["executed"] is True
        assert result["outputs"]["external_dependency_count"] == 0
        preview = _load_latest_preview(tmp=tmp, ctx=ctx)
        scopes = {row["scope_id"]: row["status"] for row in preview["scope_results"]}
        assert scopes["parcel_2"] == "blocked"
        assert preview["external_dependencies"] == []


def test_intent_first_prepare_no_candidates_skips_dependency_decisions(
    monkeypatch,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref, submitted, ctx = _submit_with_lineage(
            tmp,
            leg2_distance=_PRACTICE_CORRECT_DISTANCE,
            monkeypatch=monkeypatch,
        )
        snap = _resolution_snapshot()
        # Drop continuation blocker so no known dependency candidates project.
        snap["items"] = [
            item
            for item in snap.get("items", [])
            if item.get("item_id") != "parcel_2_continuation_scope"
        ]
        snap["relations"] = [
            rel
            for rel in snap.get("relations", [])
            if rel.get("source_item_id") != "parcel_2_continuation_scope"
        ]
        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            persistence=persistence,
            use_current_mapping_lineage=True,
            correction_decisions=[_correction_decision()],
            resolution_state_snapshot=snap,
            **ctx,
            **_compact_dispositions(),
        )
        assert result["executed"] is True
        assert result.get("refusal") is None
        assert result["outputs"]["external_dependency_count"] == 0


def test_intent_first_prepare_reuse_covers_candidates_without_new_rows(
    monkeypatch,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref, submitted, ctx = _submit_with_lineage(
            tmp,
            leg2_distance=_PRACTICE_CORRECT_DISTANCE,
            monkeypatch=monkeypatch,
        )
        first = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            persistence=persistence,
            use_current_mapping_lineage=True,
            correction_decisions=[_correction_decision()],
            dependency_decisions=[_dependency_decision_include()],
            resolution_state_snapshot=_resolution_snapshot(),
            **ctx,
            **_compact_dispositions(),
        )
        assert first["executed"] is True
        assert first["outputs"]["external_dependency_count"] == 1

        reused = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            persistence=persistence,
            use_current_mapping_lineage=True,
            reuse_agent_authored_finalization_state=True,
            correction_decisions=[_correction_decision()],
            resolution_state_snapshot=_resolution_snapshot(),
            **ctx,
        )
        assert reused["executed"] is True
        assert reused["outputs"]["external_dependency_count"] == 1
        preview = _load_latest_preview(tmp=tmp, ctx=ctx)
        deps = preview["external_dependencies"]
        assert len(deps) == 1
        assert deps[0]["dependency_id"] == "parcel_2_continuation_scope"


def test_intent_first_prepare_decline_strips_reused_dependency_row(
    monkeypatch,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref, submitted, ctx = _submit_with_lineage(
            tmp,
            leg2_distance=_PRACTICE_CORRECT_DISTANCE,
            monkeypatch=monkeypatch,
        )
        first = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            persistence=persistence,
            use_current_mapping_lineage=True,
            correction_decisions=[_correction_decision()],
            dependency_decisions=[_dependency_decision_include()],
            resolution_state_snapshot=_resolution_snapshot(),
            **ctx,
            **_compact_dispositions(),
        )
        assert first["executed"] is True
        assert first["outputs"]["external_dependency_count"] == 1

        declined = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            persistence=persistence,
            use_current_mapping_lineage=True,
            reuse_agent_authored_finalization_state=True,
            correction_decisions=[_correction_decision()],
            dependency_decisions=[
                {
                    "candidate_id": "parcel_2_continuation_scope",
                    "disposition": "not_applicable",
                    "rationale": "Agent declines the previously included continuation dependency.",
                }
            ],
            resolution_state_snapshot=_resolution_snapshot(),
            **ctx,
        )
        assert declined["executed"] is True
        assert declined["outputs"]["external_dependency_count"] == 0
        preview = _load_latest_preview(tmp=tmp, ctx=ctx)
        assert preview["external_dependencies"] == []


def test_intent_first_missing_finalization_state_returns_shell(monkeypatch) -> None:
    """Fresh lineage with only a correction decision → one unified card for remaining lanes."""
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref, submitted, ctx = _submit_with_lineage(
            tmp,
            leg2_distance=_PRACTICE_CORRECT_DISTANCE,
            monkeypatch=monkeypatch,
        )
        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            persistence=persistence,
            use_current_mapping_lineage=True,
            correction_decisions=[_correction_decision()],
            resolution_state_snapshot=_resolution_snapshot(),
            **ctx,
        )
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "missing_finalization_decisions"
        assert result["refusal"]["retryable"] is True
        assert result["refusal"]["blocked_by_invariant"] is False
        card = result["outputs"]["finalization_decision_card"]
        assert set(card["required_lanes"]) == {
            "scope_dispositions",
            "closure_dispositions",
            "dependency_decisions",
        }
        assert card["scope_dispositions"] == []
        assert len(card["closure_dispositions"]) == 4
        assert card["dependency_decisions"][0]["candidate_id"] == "parcel_2_continuation_scope"
        assert card["dependency_decisions"][0]["affected_scope"] == "parcel_2"
        template = result["outputs"]["retry_request_template"]
        assert template["correction_decisions"][0]["target_entity_id"] == "p1_call2_distance"
        assert template["correction_decisions"][0]["rationale"]
        assert result["outputs"].get("repair_hint")


def test_intent_first_fresh_request_returns_complete_decision_card(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref, submitted, ctx = _submit_with_lineage(
            tmp,
            leg2_distance=_PRACTICE_CORRECT_DISTANCE,
            monkeypatch=monkeypatch,
        )
        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            persistence=persistence,
            use_current_mapping_lineage=True,
            resolution_state_snapshot=_resolution_snapshot(),
            **ctx,
        )
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "missing_finalization_decisions"
        assert result["refusal"]["retryable"] is True
        card = result["outputs"]["finalization_decision_card"]
        assert set(card["required_lanes"]) == {
            "scope_dispositions",
            "closure_dispositions",
            "correction_decisions",
            "dependency_decisions",
        }
        assert card["scope_dispositions"] == []
        assert len(card["closure_dispositions"]) == 4
        assert card["correction_decisions"][0]["target_entity_id"] == "p1_call2_distance"
        assert "status" not in card["correction_decisions"][0]
        assert card["dependency_decisions"][0]["candidate_id"] == "parcel_2_continuation_scope"
        assert card["dependency_decisions"][0]["dependency_id"] == "parcel_2_continuation_scope"


def test_intent_first_resubmit_from_decision_card_succeeds_directly(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref, submitted, ctx = _submit_with_lineage(
            tmp,
            leg2_distance=_PRACTICE_CORRECT_DISTANCE,
            monkeypatch=monkeypatch,
        )
        first = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            persistence=persistence,
            use_current_mapping_lineage=True,
            correction_decisions=[_correction_decision()],
            resolution_state_snapshot=_resolution_snapshot(),
            **ctx,
        )
        assert first["executed"] is False
        template = first["outputs"]["retry_request_template"]
        retry = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            persistence=persistence,
            use_current_mapping_lineage=True,
            correction_decisions=template["correction_decisions"],
            dependency_decisions=[_dependency_decision_include()],
            resolution_state_snapshot=_resolution_snapshot(),
            **ctx,
            **_compact_dispositions(),
        )
        assert retry["executed"] is True
        assert retry["outputs"]["finalization_status"] == "preview_ready"
        assert retry["outputs"]["external_dependency_count"] == 1
        preview = _load_latest_preview(tmp=tmp, ctx=ctx)
        scopes = {row["scope_id"]: row["status"] for row in preview["scope_results"]}
        assert scopes["parcel_1"] == "handoffable"
        assert scopes["parcel_2"] == "blocked"


def test_intent_first_decision_card_timeline_is_single_section(monkeypatch) -> None:
    from harness.audit.human_timeline import _render_tool_result

    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref, submitted, ctx = _submit_with_lineage(
            tmp,
            leg2_distance=_PRACTICE_CORRECT_DISTANCE,
            monkeypatch=monkeypatch,
        )
        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            persistence=persistence,
            use_current_mapping_lineage=True,
            resolution_state_snapshot=_resolution_snapshot(),
            **ctx,
        )
        turn = {
            "tool_result_raw": {
                "execution_state": "refused",
                "refusal": result["refusal"],
                "outputs": result["outputs"],
            }
        }
        rendered = "\n".join(_render_tool_result(turn))
        assert rendered.count("finalization_decision_card:") == 1
        assert "required_lanes:" in rendered
        assert "correction_targets:" in rendered
        assert "dependency_candidates:" in rendered
        assert rendered.count("missing_finalization_decisions:") == 0


def test_intent_first_missing_scope_dispositions_are_retryable(monkeypatch) -> None:
    from tooling.mapping.deed_to_ir.intent_first_prepare import expand_compact_dispositions

    result = expand_compact_dispositions(
        scope_dispositions=[],
        closure_dispositions=_compact_dispositions()["closure_dispositions"],
    )
    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == "scope_dispositions_required"
    assert result["refusal"]["retryable"] is True
    assert result["refusal"]["blocked_by_invariant"] is False


def test_intent_first_missing_closure_dispositions_are_retryable() -> None:
    from tooling.mapping.deed_to_ir.intent_first_prepare import expand_compact_dispositions

    result = expand_compact_dispositions(
        scope_dispositions=_compact_dispositions()["scope_dispositions"],
        closure_dispositions=[],
    )
    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == "closure_dispositions_required"
    assert result["refusal"]["retryable"] is True
    assert result["refusal"]["blocked_by_invariant"] is False


def test_intent_first_incomplete_closure_dispositions_are_retryable() -> None:
    from tooling.mapping.deed_to_ir.intent_first_prepare import expand_compact_dispositions

    first_dim = sorted(ALLOWED_CLOSURE_DIMENSION_IDS)[0]
    result = expand_compact_dispositions(
        scope_dispositions=_compact_dispositions()["scope_dispositions"],
        closure_dispositions=[
            {"dimension_id": first_dim, "status": "closed"},
        ],
    )
    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == "closure_dispositions_incomplete"
    assert result["refusal"]["retryable"] is True
    assert result["refusal"]["blocked_by_invariant"] is False
    shell = result["outputs"]["missing_finalization_decisions"]["closure_dispositions"]
    missing_ids = {row["dimension_id"] for row in shell}
    assert first_dim not in missing_ids
    assert len(missing_ids) == 3


def test_intent_first_malformed_disposition_missing_status_is_retryable() -> None:
    from tooling.mapping.deed_to_ir.intent_first_prepare import expand_compact_dispositions

    result = expand_compact_dispositions(
        scope_dispositions=[{"scope_id": "parcel_1"}],
        closure_dispositions=_compact_dispositions()["closure_dispositions"],
    )
    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == "scope_disposition_status_required"
    assert result["refusal"]["retryable"] is True
    assert result["refusal"]["blocked_by_invariant"] is False


def test_intent_first_missing_correction_decision_refuses(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref, submitted, ctx = _submit_with_lineage(
            tmp,
            leg2_distance=_PRACTICE_CORRECT_DISTANCE,
            monkeypatch=monkeypatch,
        )
        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            persistence=persistence,
            use_current_mapping_lineage=True,
            correction_decisions=[],
            dependency_decisions=[_dependency_decision_include()],
            resolution_state_snapshot=_resolution_snapshot(),
            **ctx,
            **_compact_dispositions(),
        )
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "missing_finalization_decisions"
        assert result["refusal"]["retryable"] is True
        assert result["refusal"]["blocked_by_invariant"] is False
        card = result["outputs"]["finalization_decision_card"]
        assert card["required_lanes"] == ["correction_decisions"]
        assert card["correction_decisions"][0]["target_entity_id"] == "p1_call2_distance"
        assert result["outputs"].get("repair_hint")
        template = result["outputs"]["retry_request_template"]
        assert template["dependency_decisions"][0]["candidate_id"] == "parcel_2_continuation_scope"
        assert template["scope_dispositions"]


def test_intent_first_malformed_correction_decision_is_retryable() -> None:
    from tooling.mapping.deed_to_ir.intent_first_prepare import (
        assemble_upstream_corrections_from_decisions,
    )

    result = assemble_upstream_corrections_from_decisions(
        correction_decisions=[
            {
                "target_entity_id": "p1_call2_distance",
                "posture": "confirmed_from_source",
                "resolution_used_by_ir": True,
                "recommended_action": "transcript_amendment",
                # rationale omitted — malformed
            }
        ],
        correction_posture={
            "active": True,
            "candidate_deltas": [
                {
                    "target_entity_id": "p1_call2_distance",
                    "upstream_value": "618 feet",
                    "selected_ir_display_value": "518 feet",
                    "selected_ir_value": 518.0,
                }
            ],
            "reason_codes": ["ir_differs_from_inherited"],
        },
        mapping_artifact_ref="artifact:mapping:test",
        ir_artifact_ref="artifact:ir:test",
    )
    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == "correction_decision_rationale_required"
    assert result["refusal"]["retryable"] is True
    assert result["refusal"]["blocked_by_invariant"] is False


def test_intent_first_incomplete_correction_decisions_are_retryable() -> None:
    from tooling.mapping.deed_to_ir.intent_first_prepare import (
        assemble_upstream_corrections_from_decisions,
    )

    result = assemble_upstream_corrections_from_decisions(
        correction_decisions=[
            {
                "target_entity_id": "target_a",
                "posture": "confirmed_from_source",
                "resolution_used_by_ir": True,
                "recommended_action": "transcript_amendment",
                "rationale": "Accept target_a repair.",
            }
        ],
        correction_posture={
            "active": True,
            "candidate_deltas": [
                {
                    "target_entity_id": "target_a",
                    "upstream_value": "100",
                    "selected_ir_display_value": "90",
                    "selected_ir_value": 90.0,
                    "basis_refs": ["artifact:ir:test"],
                },
                {
                    "target_entity_id": "target_b",
                    "upstream_value": "200",
                    "selected_ir_display_value": "180",
                    "selected_ir_value": 180.0,
                    "basis_refs": ["artifact:ir:test"],
                },
            ],
            "reason_codes": ["ir_differs_from_inherited"],
        },
        mapping_artifact_ref="artifact:mapping:test",
        ir_artifact_ref="artifact:ir:test",
    )
    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == "correction_decisions_incomplete"
    assert result["refusal"]["retryable"] is True
    assert result["refusal"]["blocked_by_invariant"] is False
    assert result["outputs"]["missing_correction_targets"] == ["target_b"]
    assert result["outputs"].get("repair_hint")


def test_explicit_prepare_still_works(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref, submitted, ctx = _submit_with_lineage(
            tmp,
            leg2_distance=_PRACTICE_CORRECT_DISTANCE,
            monkeypatch=monkeypatch,
        )
        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            mapping_artifact_ref=submitted["outputs"]["mapping_artifact_ref"],
            expected_ir_artifact_ref=ir_ref,
            persistence=persistence,
            resolution_state_snapshot=_resolution_snapshot(),
            upstream_corrections=[
                {
                    "correction_id": "explicit_p1_call2",
                    "target_entity_id": "p1_call2_distance",
                    "target_entity_type": "resolution_unit",
                    "upstream_value": "618 feet",
                    "corrected_value": "518 feet",
                    "posture": "confirmed_from_source",
                    "resolution_used_by_ir": True,
                    "recommended_action": "transcript_amendment",
                    "basis_refs": ["image:derived:fixture", ir_ref],
                    "rationale": "Explicit path still supported.",
                }
            ],
            **ctx,
            **_valid_rows(),
        )
        assert result["executed"] is True
        assert "finalization_status" not in result["outputs"]


def test_intent_first_refuses_missing_lineage(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _patch_deed_root(monkeypatch, tmp)
        ctx = _context()
        result = prepare_deed_to_ir_final_package(
            dossier_id="d-preview",
            use_current_mapping_lineage=True,
            reuse_agent_authored_finalization_state=True,
            **ctx,
        )
        assert result["executed"] is False
        assert result["refusal"]["reason_code"] == "current_mapping_lineage_missing"


def test_hydrate_mapping_annotates_current_and_superseded(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref_v0, submitted_v0, ctx = _submit_with_lineage(
            tmp,
            leg2_distance=_PRACTICE_CORRECT_DISTANCE,
            monkeypatch=monkeypatch,
        )
        # Patch IR and remap so v0 mapping is superseded.
        patched = save_ir_artifact(
            dossier_id="d-preview",
            feature_graph=_source_repair_graph(leg2_distance=519.0).model_dump(mode="json"),
            base_draft_ref=ir_ref,
            draft_workspace_id=ctx["workspace_id"],
            draft_run_id=ctx["run_id"],
            transcription_id=ctx["transcription_id"],
            persistence=persistence,
        )
        assert patched["executed"] is True
        remapped = submit_ir_for_mapping(
            dossier_id="d-preview",
            ir_artifact_ref=patched["outputs"]["ir_artifact_ref"],
            persistence=persistence,
            resolution_state_snapshot=_resolution_snapshot(),
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert remapped["executed"] is True
        mapping_ref_current = remapped["outputs"]["mapping_artifact_ref"]
        assert mapping_ref_current != mapping_ref_v0

        hydrated = hydrate_artifact_refs(
            dossier_id="d-preview",
            ref_ids=[mapping_ref_v0, mapping_ref_current],
            persistence=persistence,
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        by_ref = {row["ref_id"]: row for row in hydrated["outputs"]["results"]}
        stale_row = by_ref[mapping_ref_v0]
        current_row = by_ref[mapping_ref_current]
        assert stale_row["lineage_status"] == "superseded"
        assert stale_row["lineage_current"] is False
        assert stale_row["current_mapping_artifact_ref"] == mapping_ref_current
        assert stale_row["mapping_review"]["lineage_status"] == "superseded"
        assert current_row["lineage_status"] == "current"
        assert current_row["lineage_current"] is True
        assert current_row["mapping_review"]["lineage_status"] == "current"
