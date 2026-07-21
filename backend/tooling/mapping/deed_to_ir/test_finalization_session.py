"""Deterministic tests for lineage-bound deed-to-IR finalization sessions (D2IR-BR-011)."""

from __future__ import annotations

import tempfile

from domains.mapping.deed_to_ir.state.prompt_runtime_projection import (
    build_prompt_runtime_projection,
)
from tooling.mapping.deed_to_ir.finalization_scope_inventory import (
    project_finalization_scope_inventory,
)
from tooling.mapping.deed_to_ir.finalization_session import (
    CANONICAL_CLOSURE_DIMENSION_IDS,
    SCHEMA_VERSION,
    SCOPE_INVENTORY_UNAVAILABLE,
    STATUS_PENDING_DECISIONS,
    STATUS_STALE,
    build_pending_finalization_session,
    compact_finalization_session_for_prompt,
    empty_finalization_decisions,
)
from tooling.mapping.deed_to_ir.finalization_session_persistence import (
    read_finalization_session,
    replace_finalization_session_for_mapping_submission,
    write_finalization_session,
)
from tooling.mapping.deed_to_ir.ir_mapping_submission import submit_ir_for_mapping
from tooling.mapping.deed_to_ir.ir_persistence import save_ir_artifact
from tooling.mapping.deed_to_ir.test_correction_posture import (
    _PRACTICE_CORRECT_DISTANCE,
    _resolution_snapshot,
    _source_repair_graph,
)
from tooling.mapping.deed_to_ir.test_final_package_preview import (
    _context,
    _patch_deed_root,
    _services,
)
from tooling.mapping.deed_to_ir.test_mapping_lineage_intent_first import _submit_with_lineage


def test_multi_scope_extraction_from_ir_and_resolution() -> None:
    inventory = project_finalization_scope_inventory(
        ir_graph={
            "nodes": [
                {"id": "parcel_1_traverse"},
                {"id": "parcel_2_scope"},
                {"id": "pob"},
            ]
        },
        mapping_artifact={
            "rendered_feature_ids": ["parcel_1_traverse"],
            "skipped_features": [{"node_id": "parcel_2_blocker"}],
        },
        resolution_state_snapshot=_resolution_snapshot(),
    )
    assert inventory["scope_ids"] == ["parcel_1", "parcel_2"]
    assert inventory["diagnostics"] == []


def test_scope_extraction_from_dependency_and_correction_identifiers() -> None:
    inventory = project_finalization_scope_inventory(
        correction_candidates=[
            {"target_entity_id": "p1_call2_distance"},
            {"target_entity_id": "p3_call1_bearing"},
        ],
        dependency_candidates=[
            {
                "candidate_id": "parcel_2_continuation_scope",
                "affected_scope": "parcel_2",
            }
        ],
    )
    assert inventory["scope_ids"] == ["parcel_1", "parcel_2", "parcel_3"]
    assert inventory["diagnostics"] == []


def test_no_prose_based_scope_inference() -> None:
    inventory = project_finalization_scope_inventory(
        resolution_state_snapshot={
            "items": [
                {
                    "item_id": "opaque_blocker",
                    "summary": "Parcel 9 continuation is blocked pending external source.",
                    "title": "Blocked on Parcel 7 handoff",
                    "notes": "See Parcel 4 rationale.",
                }
            ]
        },
    )
    assert inventory["scope_ids"] == []
    assert inventory["diagnostics"][0]["code"] == SCOPE_INVENTORY_UNAVAILABLE


def test_empty_inventory_diagnostic() -> None:
    inventory = project_finalization_scope_inventory(
        ir_graph={"nodes": [{"id": "pob"}, {"id": "anchor"}]},
        mapping_artifact={
            "rendered_feature_ids": ["pob"],
            "skipped_features": [{"node_id": "group1"}],
        },
        correction_candidates=[{"target_entity_id": "unknown_atom"}],
        dependency_candidates=[{"candidate_id": "x", "affected_scope": ""}],
    )
    assert inventory["scope_ids"] == []
    assert len(inventory["diagnostics"]) == 1
    assert inventory["diagnostics"][0]["code"] == SCOPE_INVENTORY_UNAVAILABLE

    session = build_pending_finalization_session(
        mapping_artifact_ref="feature_graph:mapping:m1",
        source_ir_artifact_ref="feature_graph:ir:i1",
        scope_ids=inventory["scope_ids"],
        diagnostics=inventory["diagnostics"],
    )
    assert session["requirements"]["scope_ids"] == []
    assert session["diagnostics"][0]["code"] == SCOPE_INVENTORY_UNAVAILABLE
    assert session["decisions"] == empty_finalization_decisions()


def test_session_creation_after_successful_remap(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref, submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        assert submitted["executed"] is True
        compact = submitted["outputs"].get("active_finalization_session")
        assert compact is not None
        assert compact["status"] == STATUS_PENDING_DECISIONS
        assert compact["lineage"]["mapping_artifact_ref"] == mapping_ref
        assert compact["lineage"]["source_ir_artifact_ref"] == ir_ref
        assert "parcel_1" in compact["requirements"]["scope_ids"]
        assert "parcel_2" in compact["requirements"]["scope_ids"]
        assert "parcel_2_continuation_scope" in compact["requirements"]["dependency_ids"]
        assert "decisions" not in compact or not compact.get("decisions")

        disk = read_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert disk is not None
        assert disk["schema_version"] == SCHEMA_VERSION
        assert disk["status"] == STATUS_PENDING_DECISIONS
        assert disk["lineage"]["mapping_artifact_ref"] == mapping_ref
        assert disk["lineage"]["source_ir_artifact_ref"] == ir_ref
        assert disk["decisions"] == empty_finalization_decisions()
        assert disk["preview_ref"] is None
        assert disk["output_revision_ref"] is None
        _ = persistence


def test_session_replacement_on_another_remap(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, mapping_ref, submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        first_session = read_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert first_session is not None
        # Simulate accepted decisions on the prior lineage (must not migrate).
        mutated = dict(first_session)
        mutated["decisions"] = {
            "scope_statuses": {"parcel_1": "handoffable"},
            "correction_dispositions": {},
            "dependency_dispositions": {"parcel_2_continuation_scope": "include"},
            "closure_statuses": {
                dimension_id: "closed" for dimension_id in CANONICAL_CLOSURE_DIMENSION_IDS
            },
            "rationales": {"parcel_1": "prior lineage decision"},
        }
        write_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
            session=mutated,
        )

        remapped = submit_ir_for_mapping(
            dossier_id="d-preview",
            ir_artifact_ref=ir_ref,
            persistence=persistence,
            resolution_state_snapshot=_resolution_snapshot(),
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert remapped["executed"] is True
        second_mapping = remapped["outputs"]["mapping_artifact_ref"]
        assert submitted["outputs"]["mapping_artifact_ref"] == mapping_ref

        second = read_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert second is not None
        assert second["status"] == STATUS_PENDING_DECISIONS
        assert second["lineage"]["mapping_artifact_ref"] == second_mapping
        assert second["lineage"]["source_ir_artifact_ref"] == ir_ref
        assert second["decisions"] == empty_finalization_decisions()
        assert second["decisions"]["closure_statuses"] == {}
        assert second["decisions"]["rationales"] == {}
        assert second["requirements"]["closure_ids"] == list(CANONICAL_CLOSURE_DIMENSION_IDS)


def test_session_staleness_after_newer_ir_write(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        persistence, ir_ref, _mapping_ref, _submitted, ctx = _submit_with_lineage(
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
        new_ir = saved["outputs"]["ir_artifact_ref"]
        assert new_ir != ir_ref
        assert saved["outputs"].get("finalization_session_status") == STATUS_STALE

        disk = read_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert disk is not None
        assert disk["status"] == STATUS_STALE
        assert disk["stale"] is True
        assert disk["superseded_by_ir_artifact_ref"] == new_ir
        # Stale sessions must not project into the prompt.
        assert compact_finalization_session_for_prompt(disk) is None


def test_no_decision_migration_across_lineages(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _patch_deed_root(monkeypatch, tmp)
        ctx = _context()
        persistence = _services(tmp)
        saved = save_ir_artifact(
            dossier_id="d-preview",
            feature_graph=_source_repair_graph(
                leg2_distance=_PRACTICE_CORRECT_DISTANCE
            ).model_dump(mode="json"),
            artifact_id="ir_source_repair",
            draft_workspace_id=ctx["workspace_id"],
            draft_run_id=ctx["run_id"],
            transcription_id=ctx["transcription_id"],
            persistence=persistence,
        )
        ir_ref = saved["outputs"]["ir_artifact_ref"]
        replace_finalization_session_for_mapping_submission(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
            mapping_artifact_ref="feature_graph:mapping:old",
            source_ir_artifact_ref=ir_ref,
            ir_graph=_source_repair_graph(leg2_distance=_PRACTICE_CORRECT_DISTANCE),
            resolution_state_snapshot=_resolution_snapshot(),
        )
        prior = read_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
        )
        assert prior is not None
        prior["decisions"] = {
            "scope_statuses": {"parcel_1": "blocked"},
            "correction_dispositions": {"p1_call2_distance": "needs_hitl"},
            "dependency_dispositions": {},
            "rationales": {"parcel_1": "do-not-migrate"},
        }
        write_finalization_session(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
            session=prior,
        )

        fresh = replace_finalization_session_for_mapping_submission(
            dossier_id="d-preview",
            transcription_id=ctx["transcription_id"],
            workspace_id=ctx["workspace_id"],
            run_id=ctx["run_id"],
            mapping_artifact_ref="feature_graph:mapping:new",
            source_ir_artifact_ref=ir_ref,
            ir_graph=_source_repair_graph(leg2_distance=_PRACTICE_CORRECT_DISTANCE),
            resolution_state_snapshot=_resolution_snapshot(),
        )
        assert fresh is not None
        assert fresh["lineage"]["mapping_artifact_ref"] == "feature_graph:mapping:new"
        assert fresh["decisions"] == empty_finalization_decisions()
        assert fresh["decisions"]["rationales"] == {}


def test_per_turn_prompt_projection(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        _persistence, ir_ref, mapping_ref, _submitted, ctx = _submit_with_lineage(
            tmp, leg2_distance=_PRACTICE_CORRECT_DISTANCE, monkeypatch=monkeypatch
        )
        projected = build_prompt_runtime_projection(
            launch_context={
                "dossier_id": "d-preview",
                "transcription_id": ctx["transcription_id"],
                "workspace_id": ctx["workspace_id"],
                "run_id": ctx["run_id"],
            },
            resolution_items=[],
        )
        assert projected is not None
        session = projected["active_finalization_session"]
        assert session["status"] == STATUS_PENDING_DECISIONS
        assert session["lineage"]["mapping_artifact_ref"] == mapping_ref
        assert session["lineage"]["source_ir_artifact_ref"] == ir_ref
        assert "parcel_1" in session["missing"]["scope_ids"]
        assert "parcel_2" in session["missing"]["scope_ids"]
        assert session["missing"]["closure_ids"] == list(CANONICAL_CLOSURE_DIMENSION_IDS)
        assert "allowed_values" in session
        assert "handoffable" in session["allowed_values"]["scope_statuses"]
        assert "include" in session["allowed_values"]["dependency_dispositions"]
        assert "confirmed_source_repair" in session["allowed_values"]["correction_dispositions"]
        assert "ir_only_exception" in session["allowed_values"]["correction_dispositions"]
        assert session["allowed_values"]["closure_statuses"] == [
            "closed",
            "partial",
            "blocked",
        ]
        assert "confirmed_from_source" not in session["allowed_values"]["correction_dispositions"]
        assert "suspected" not in session["allowed_values"]["correction_dispositions"]
        # Bounded: no full candidate evidence blobs.
        assert "candidate_deltas" not in session
        assert "correction_candidates" not in session
        assert session["requirements"]["closure_ids"] == list(CANONICAL_CLOSURE_DIMENSION_IDS)


def test_persistence_read_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    session = build_pending_finalization_session(
        mapping_artifact_ref="feature_graph:mapping:m_rt",
        source_ir_artifact_ref="feature_graph:ir:i_rt",
        scope_ids=["parcel_1", "parcel_2"],
        correction_candidates=[{"target_entity_id": "p1_call2_distance", "value_kind": "distance"}],
        dependency_candidates=[
            {
                "candidate_id": "parcel_2_continuation_scope",
                "affected_scope": "parcel_2",
                "description": "Continuation unavailable.",
            }
        ],
    )
    written = write_finalization_session(
        dossier_id="dossier-rt",
        transcription_id="draft_legal_text_image",
        workspace_id="ws-rt",
        run_id=None,
        session=session,
    )
    assert written is not None
    assert written.get("updated_at")

    loaded = read_finalization_session(
        dossier_id="dossier-rt",
        transcription_id="draft_legal_text_image",
        workspace_id="ws-rt",
        run_id=None,
    )
    assert loaded is not None
    assert loaded["schema_version"] == SCHEMA_VERSION
    assert loaded["lineage"] == session["lineage"]
    assert loaded["requirements"]["scope_ids"] == ["parcel_1", "parcel_2"]
    assert loaded["requirements"]["correction_candidates"][0]["target_entity_id"] == (
        "p1_call2_distance"
    )
    assert loaded["requirements"]["dependency_candidates"][0]["candidate_id"] == (
        "parcel_2_continuation_scope"
    )
    assert loaded["decisions"] == empty_finalization_decisions()

    compact = compact_finalization_session_for_prompt(loaded)
    assert compact is not None
    assert compact["missing"]["scope_ids"] == ["parcel_1", "parcel_2"]
    assert compact["missing"]["correction_ids"] == ["p1_call2_distance"]
    assert compact["missing"]["dependency_ids"] == ["parcel_2_continuation_scope"]
    assert compact["missing"]["closure_ids"] == list(CANONICAL_CLOSURE_DIMENSION_IDS)
    assert loaded["requirements"]["closure_ids"] == list(CANONICAL_CLOSURE_DIMENSION_IDS)


def test_dependency_candidate_via_mapping_blocking_issue() -> None:
    from tooling.mapping.deed_to_ir.dependency_candidates_projection import (
        project_known_dependency_candidates,
    )
    from tooling.mapping.deed_to_ir.finalization_session_persistence import (
        build_finalization_session_for_mapping_submission,
    )
    from tooling.mapping.deed_to_ir.resolution_scope import SCOPE_SIGNALS_CONFLICT_CODE

    snapshot = {
        "items": [
            {
                "item_id": "parcel_4_external_blocker",
                "kind": "open_question",
                "status": "blocked",
                "blocking": True,
                "summary": "External survey required to continue Parcel 4.",
                "affected_scope": "parcel_4",
            },
            {
                "item_id": "conflicted_blocker",
                "kind": "open_question",
                "status": "blocked",
                "blocking": True,
                "summary": "Conflicting scope signals.",
                "scope_id": "parcel_5",
                "parcel_id": "parcel_6",
            },
        ],
        "relations": [],
    }
    issues = [
        {
            "issue_id": "parcel_4_external_blocker",
            "mapping_blocking": True,
            "summary": "External survey required to continue Parcel 4.",
        },
        {
            "issue_id": "conflicted_blocker",
            "mapping_blocking": True,
            "summary": "Conflicting scope signals.",
        },
    ]
    without_issues = project_known_dependency_candidates(
        resolution_state_snapshot=snapshot,
        issues=None,
    )
    assert without_issues["candidates"] == []

    with_issues = project_known_dependency_candidates(
        resolution_state_snapshot=snapshot,
        issues=issues,
    )
    assert [row["candidate_id"] for row in with_issues["candidates"]] == [
        "parcel_4_external_blocker"
    ]
    assert with_issues["candidates"][0]["affected_scope"] == "parcel_4"
    assert any(
        row.get("code") == SCOPE_SIGNALS_CONFLICT_CODE for row in with_issues["diagnostics"]
    )

    session = build_finalization_session_for_mapping_submission(
        mapping_artifact_ref="feature_graph:mapping:m_issue",
        source_ir_artifact_ref="feature_graph:ir:i_issue",
        ir_graph={"nodes": [{"id": "pob"}]},
        mapping_artifact={"rendered_feature_ids": [], "skipped_features": []},
        resolution_state_snapshot=snapshot,
        issues=issues,
    )
    dep_ids = [
        row["candidate_id"] for row in session["requirements"]["dependency_candidates"]
    ]
    assert "parcel_4_external_blocker" in dep_ids
    assert any(
        row.get("code") == SCOPE_SIGNALS_CONFLICT_CODE for row in session.get("diagnostics") or []
    )


def test_scope_from_real_mapping_artifact_rendered_ids_only() -> None:
    inventory = project_finalization_scope_inventory(
        ir_graph={"nodes": [{"id": "pob"}, {"id": "anchor"}]},
        mapping_artifact={
            "rendered_feature_ids": ["parcel_9_region"],
            "skipped_features": [{"node_id": "parcel_11_blocker"}],
        },
        correction_candidates=[],
        dependency_candidates=[],
        resolution_state_snapshot={"items": []},
    )
    assert inventory["scope_ids"] == ["parcel_11", "parcel_9"]

    # Submission wrappers expose rendered/skipped on .artifact — inventory unwraps.
    class _Wrapper:
        artifact = {
            "rendered_feature_ids": ["parcel_8_traverse"],
            "skipped_features": [],
        }

    wrapped = project_finalization_scope_inventory(
        ir_graph={"nodes": [{"id": "pob"}]},
        mapping_artifact=_Wrapper(),
        correction_candidates=[],
        dependency_candidates=[],
        resolution_state_snapshot={"items": []},
    )
    assert wrapped["scope_ids"] == ["parcel_8"]


def test_requirements_capacity_exceeded_diagnostic() -> None:
    from tooling.mapping.deed_to_ir.finalization_session import (
        MAX_CORRECTION_REQUIREMENTS,
        MAX_SCOPE_REQUIREMENTS,
        REQUIREMENTS_CAPACITY_EXCEEDED,
    )

    too_many_scopes = [f"parcel_{i}" for i in range(1, MAX_SCOPE_REQUIREMENTS + 2)]
    too_many_corrections = [
        {"target_entity_id": f"p1_call{i}_distance"} for i in range(1, MAX_CORRECTION_REQUIREMENTS + 2)
    ]
    session = build_pending_finalization_session(
        mapping_artifact_ref="feature_graph:mapping:m_cap",
        source_ir_artifact_ref="feature_graph:ir:i_cap",
        scope_ids=too_many_scopes,
        correction_candidates=too_many_corrections,
    )
    assert len(session["requirements"]["scope_ids"]) == MAX_SCOPE_REQUIREMENTS
    assert len(session["requirements"]["correction_candidates"]) == MAX_CORRECTION_REQUIREMENTS
    capacity_rows = [
        row
        for row in session.get("diagnostics") or []
        if row.get("code") == REQUIREMENTS_CAPACITY_EXCEEDED
    ]
    lanes = {row["lane"] for row in capacity_rows}
    assert "scope_ids" in lanes
    assert "correction_candidates" in lanes
    scope_diag = next(row for row in capacity_rows if row["lane"] == "scope_ids")
    assert scope_diag["observed_count"] == MAX_SCOPE_REQUIREMENTS + 1
    assert scope_diag["maximum_count"] == MAX_SCOPE_REQUIREMENTS


def test_prompt_compaction_rejects_invalid_and_unknown_decisions() -> None:
    from tooling.mapping.deed_to_ir.finalization_session import MAX_RATIONALE_CHARS

    session = build_pending_finalization_session(
        mapping_artifact_ref="feature_graph:mapping:m_dec",
        source_ir_artifact_ref="feature_graph:ir:i_dec",
        scope_ids=["parcel_1", "parcel_2"],
        correction_candidates=[{"target_entity_id": "p1_call2_distance"}],
        dependency_candidates=[
            {
                "candidate_id": "parcel_2_continuation_scope",
                "affected_scope": "parcel_2",
                "description": "Continuation unavailable.",
            }
        ],
    )
    oversized = "x" * (MAX_RATIONALE_CHARS + 50)
    session["decisions"] = {
        "scope_statuses": {
            "parcel_1": "handoffable",
            "parcel_2": "",  # blank — remains missing
            "parcel_99": "handoffable",  # unknown id — not projected
        },
        "correction_dispositions": {
            "p1_call2_distance": "confirmed_from_source",  # legacy — invalid
        },
        "dependency_dispositions": {
            "parcel_2_continuation_scope": "include",
            "unknown_dep": "include",
        },
        "closure_statuses": {},
        "rationales": {
            "parcel_1": oversized,
            "parcel_99": "unknown id rationale",
            "parcel_2": "  ",
        },
    }
    compact = compact_finalization_session_for_prompt(session)
    assert compact is not None
    decisions = compact["decisions"]
    assert decisions["scope_statuses"] == {"parcel_1": "handoffable"}
    assert "correction_dispositions" not in decisions
    assert decisions["dependency_dispositions"] == {
        "parcel_2_continuation_scope": "include"
    }
    # Oversized / unknown / blank rationales are excluded; bodies are never projected.
    assert "rationales" not in decisions
    assert "rationale_ids" not in decisions
    assert compact["missing"]["scope_ids"] == ["parcel_2"]
    assert compact["missing"]["correction_ids"] == ["p1_call2_distance"]
    assert compact["missing"]["dependency_ids"] == []
    assert compact["missing"]["closure_ids"] == list(CANONICAL_CLOSURE_DIMENSION_IDS)
    assert "confirmed_source_repair" in compact["allowed_values"]["correction_dispositions"]
    assert "confirmed_from_source" not in compact["allowed_values"]["correction_dispositions"]


def test_prompt_compaction_projects_rationale_ids_not_bodies() -> None:
    from tooling.mapping.deed_to_ir.finalization_session import MAX_RATIONALE_CHARS

    full = "y" * MAX_RATIONALE_CHARS
    session = build_pending_finalization_session(
        mapping_artifact_ref="feature_graph:mapping:m_rat",
        source_ir_artifact_ref="feature_graph:ir:i_rat",
        scope_ids=["parcel_1"],
        correction_candidates=[{"target_entity_id": "p1_call2_distance"}],
        dependency_candidates=[],
    )
    session["decisions"] = {
        "scope_statuses": {"parcel_1": "handoffable"},
        "correction_dispositions": {"p1_call2_distance": "ir_only_exception"},
        "dependency_dispositions": {},
        "closure_statuses": {
            dimension_id: "closed" for dimension_id in CANONICAL_CLOSURE_DIMENSION_IDS
        },
        "rationales": {"p1_call2_distance": full},
    }
    compact = compact_finalization_session_for_prompt(session)
    assert compact is not None
    assert session["decisions"]["rationales"]["p1_call2_distance"] == full
    assert "rationales" not in compact["decisions"]
    assert compact["decisions"]["rationale_ids"] == ["p1_call2_distance"]
    assert compact["decisions"]["closure_statuses"] == {
        dimension_id: "closed" for dimension_id in CANONICAL_CLOSURE_DIMENSION_IDS
    }
    assert compact["missing"]["rationale_ids"] == []
    assert compact["missing"]["closure_ids"] == []
    assert full not in str(compact)

def test_capacity_diagnostic_survives_full_incoming_diagnostic_budget() -> None:
    from tooling.mapping.deed_to_ir.finalization_session import (
        MAX_SCOPE_REQUIREMENTS,
        REQUIREMENTS_CAPACITY_EXCEEDED,
        _MAX_DIAGNOSTICS,
    )

    incoming = [{"code": f"other_diag_{i}", "message": f"noise {i}"} for i in range(_MAX_DIAGNOSTICS)]
    too_many_scopes = [f"parcel_{i}" for i in range(1, MAX_SCOPE_REQUIREMENTS + 2)]
    session = build_pending_finalization_session(
        mapping_artifact_ref="feature_graph:mapping:m_cap_priority",
        source_ir_artifact_ref="feature_graph:ir:i_cap_priority",
        scope_ids=too_many_scopes,
        diagnostics=incoming,
    )
    diagnostics = session.get("diagnostics") or []
    capacity_rows = [
        row for row in diagnostics if row.get("code") == REQUIREMENTS_CAPACITY_EXCEEDED
    ]
    assert len(capacity_rows) == 1
    assert capacity_rows[0]["lane"] == "scope_ids"
    assert capacity_rows[0]["observed_count"] == MAX_SCOPE_REQUIREMENTS + 1
    assert capacity_rows[0]["maximum_count"] == MAX_SCOPE_REQUIREMENTS
    assert len(diagnostics) <= _MAX_DIAGNOSTICS
    # Capacity retained first — not all 16 incoming rows can remain.
    other_codes = {
        row.get("code")
        for row in diagnostics
        if row.get("code") != REQUIREMENTS_CAPACITY_EXCEEDED
    }
    assert len(other_codes) == _MAX_DIAGNOSTICS - 1

    compact = compact_finalization_session_for_prompt(session)
    assert compact is not None
    compact_capacity = [
        row
        for row in (compact.get("diagnostics") or [])
        if row.get("code") == REQUIREMENTS_CAPACITY_EXCEEDED
    ]
    assert len(compact_capacity) == 1
    assert compact_capacity[0]["lane"] == "scope_ids"


def test_observed_scope_ids_bounded_in_compact_projection() -> None:
    from tooling.mapping.deed_to_ir.finalization_session import (
        REQUIREMENTS_CAPACITY_EXCEEDED,
        _MAX_OBSERVED_SCOPE_IDS,
    )
    from tooling.mapping.deed_to_ir.resolution_scope import SCOPE_SIGNALS_CONFLICT_CODE

    oversized_observed = [f"parcel_{i}" for i in range(1, _MAX_OBSERVED_SCOPE_IDS + 25)]
    session = build_pending_finalization_session(
        mapping_artifact_ref="feature_graph:mapping:m_obs",
        source_ir_artifact_ref="feature_graph:ir:i_obs",
        scope_ids=["parcel_1"],
        diagnostics=[
            {
                "code": SCOPE_SIGNALS_CONFLICT_CODE,
                "candidate_id": "conflicted_blocker",
                "observed_scope_ids": oversized_observed,
            }
        ],
    )
    persisted = session.get("diagnostics") or []
    conflict = next(row for row in persisted if row.get("code") == SCOPE_SIGNALS_CONFLICT_CODE)
    assert len(conflict["observed_scope_ids"]) == _MAX_OBSERVED_SCOPE_IDS

    compact = compact_finalization_session_for_prompt(session)
    assert compact is not None
    compact_conflict = next(
        row
        for row in (compact.get("diagnostics") or [])
        if row.get("code") == SCOPE_SIGNALS_CONFLICT_CODE
    )
    assert len(compact_conflict["observed_scope_ids"]) == _MAX_OBSERVED_SCOPE_IDS
    assert REQUIREMENTS_CAPACITY_EXCEEDED not in {
        row.get("code") for row in (compact.get("diagnostics") or [])
    }
