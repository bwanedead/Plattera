"""Focused tests for resolution-scope normalization and conflict handling."""

from __future__ import annotations

from tooling.mapping.deed_to_ir.dependency_candidates_projection import (
    project_known_dependency_candidates,
)
from tooling.mapping.deed_to_ir.resolution_scope import (
    SCOPE_SIGNALS_CONFLICT_CODE,
    collect_resolution_scope_signals,
    infer_scope_id_from_identifiers,
    is_resolution_scope_blocker,
    normalize_issue_scope_prose,
    normalize_scope_signal,
    resolve_unambiguous_scope_id,
)


def test_structured_scope_id_resolves() -> None:
    signals = collect_resolution_scope_signals(item={"scope_id": "parcel_4"})
    resolved = resolve_unambiguous_scope_id(signals)
    assert resolved["scope_id"] == "parcel_4"
    assert resolved["conflict"] is False


def test_structured_affected_scope_resolves() -> None:
    signals = collect_resolution_scope_signals(item={"affected_scope": "parcel_5"})
    assert resolve_unambiguous_scope_id(signals)["scope_id"] == "parcel_5"


def test_blocks_relation_target_resolves() -> None:
    signals = collect_resolution_scope_signals(block_targets=["parcel_3_group"])
    assert resolve_unambiguous_scope_id(signals)["scope_id"] == "parcel_3"


def test_parcel_prefix_id_resolves_to_parcel_n() -> None:
    assert normalize_scope_signal("parcel_3_continuation_scope") == "parcel_3"
    assert infer_scope_id_from_identifiers("parcel_3_group") == "parcel_3"


def test_p_prefix_id_resolves_to_parcel_n() -> None:
    assert normalize_scope_signal("p3_call2_distance") == "parcel_3"
    assert infer_scope_id_from_identifiers("p17_call1_bearing") == "parcel_17"


def test_issue_scope_prose_resolves_parcel_n() -> None:
    assert normalize_issue_scope_prose("Parcel 17 continuation") == "parcel_17"
    signals = collect_resolution_scope_signals(
        issue={"scope": "Parcel 17 continuation after cutoff"}
    )
    assert resolve_unambiguous_scope_id(signals)["scope_id"] == "parcel_17"


def test_no_supported_signal_produces_no_scope() -> None:
    signals = collect_resolution_scope_signals(
        item={"item_id": "range_reference_conflict", "title": "Range conflict"},
        issue={"summary": "No parcel mentioned"},
        identifier_sources=["range_reference_conflict"],
    )
    resolved = resolve_unambiguous_scope_id(signals)
    assert resolved["scope_id"] is None
    assert resolved["observed_scope_ids"] == []
    assert resolved["conflict"] is False


def test_agreeing_signals_produce_one_canonical_scope() -> None:
    signals = collect_resolution_scope_signals(
        item={"scope_id": "parcel_2", "item_id": "parcel_2_continuation_scope"},
        issue={"scope": "Parcel 2 after the canal"},
        block_targets=["parcel_2_group"],
        identifier_sources=["parcel_2_continuation_scope"],
    )
    resolved = resolve_unambiguous_scope_id(signals)
    assert resolved["scope_id"] == "parcel_2"
    assert resolved["observed_scope_ids"] == ["parcel_2"]
    assert resolved["conflict"] is False


def test_conflicting_signals_produce_no_candidate_and_diagnostic() -> None:
    projected = project_known_dependency_candidates(
        resolution_state_snapshot={
            "items": [
                {
                    "item_id": "conflict_scope_blocker",
                    "kind": "missing_source_scope",
                    "blocking": True,
                    "scope_id": "parcel_2",
                    "summary": "Conflicting scope signals fixture.",
                    "evidence_refs": ["image:derived:fixture"],
                }
            ],
            "relations": [
                {
                    "relation_type": "blocks",
                    "source_item_id": "conflict_scope_blocker",
                    "target_item_id": "parcel_3_group",
                }
            ],
        }
    )
    assert projected["candidates"] == []
    assert len(projected["diagnostics"]) == 1
    diag = projected["diagnostics"][0]
    assert diag["code"] == SCOPE_SIGNALS_CONFLICT_CODE
    assert diag["candidate_id"] == "conflict_scope_blocker"
    assert diag["observed_scope_ids"] == ["parcel_2", "parcel_3"]


def test_no_parcel_1_or_2_special_fallback_remains() -> None:
    # Bare prose outside supported fields must not resolve via identifier normalization.
    assert normalize_scope_signal("note about parcel 1 somewhere") is None
    assert normalize_scope_signal("parcel 2") is None
    signals = collect_resolution_scope_signals(
        item={"title": "Parcel 1 and Parcel 2 mentioned only in title"},
        identifier_sources=["unscoped_blocker"],
    )
    assert resolve_unambiguous_scope_id(signals)["scope_id"] is None
    # Title/summary are not prose sources; only issue.scope is.
    title_only = collect_resolution_scope_signals(
        item={"summary": "Parcel 9 mentioned in summary only"},
    )
    assert resolve_unambiguous_scope_id(title_only)["scope_id"] is None


def test_is_resolution_scope_blocker() -> None:
    assert is_resolution_scope_blocker({"blocking": True}) is True
    assert is_resolution_scope_blocker({"status": "blocked"}) is True
    assert is_resolution_scope_blocker({"status": "open"}) is False


def test_practice_continuation_still_projects_parcel_2() -> None:
    from tooling.mapping.deed_to_ir.test_correction_posture import _resolution_snapshot

    projected = project_known_dependency_candidates(
        resolution_state_snapshot=_resolution_snapshot()
    )
    candidates = projected["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["candidate_id"] == "parcel_2_continuation_scope"
    assert candidates[0]["affected_scope"] == "parcel_2"
    assert projected["diagnostics"] == []
