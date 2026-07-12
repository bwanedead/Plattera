"""Focused tests for compact dependency-decision identifier aliases and retryability."""

from __future__ import annotations

from tooling.mapping.deed_to_ir.dependency_decisions import (
    assemble_external_dependencies_from_decisions,
)


def _candidate(
    *,
    candidate_id: str = "parcel_2_continuation_scope",
    dependency_id: str | None = None,
) -> dict:
    return {
        "candidate_id": candidate_id,
        "dependency_id": dependency_id or candidate_id,
        "affected_scope": "parcel_2",
        "description": "Missing continuation source for Parcel 2.",
        "available_refs": ["transcript_edit:working:rev:0001"],
    }


def _include_decision(**overrides) -> dict:
    base = {
        "candidate_id": "parcel_2_continuation_scope",
        "disposition": "include",
        "status": "missing_source",
    }
    base.update(overrides)
    return base


def _assert_retryable(result: dict, *, reason_code: str) -> None:
    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == reason_code
    assert result["refusal"]["retryable"] is True
    assert result["refusal"]["blocked_by_invariant"] is False


def test_dependency_id_alone_resolves_known_candidate() -> None:
    result = assemble_external_dependencies_from_decisions(
        dependency_decisions=[
            {
                "dependency_id": "parcel_2_continuation_scope",
                "disposition": "include",
                "status": "missing_source",
            }
        ],
        candidates=[_candidate()],
    )
    assert result["executed"] is True
    assert len(result["rows"]) == 1
    assert result["rows"][0]["dependency_id"] == "parcel_2_continuation_scope"
    assert result["rows"][0]["status"] == "missing_source"


def test_candidate_id_alone_continues_to_work() -> None:
    result = assemble_external_dependencies_from_decisions(
        dependency_decisions=[_include_decision(status="blocked")],
        candidates=[_candidate()],
    )
    assert result["executed"] is True
    assert result["rows"][0]["status"] == "blocked"


def test_agreeing_candidate_id_and_dependency_id_resolve() -> None:
    result = assemble_external_dependencies_from_decisions(
        dependency_decisions=[
            _include_decision(
                candidate_id="parcel_2_continuation_scope",
                dependency_id="parcel_2_continuation_scope",
            )
        ],
        candidates=[_candidate()],
    )
    assert result["executed"] is True
    assert result["rows"][0]["dependency_id"] == "parcel_2_continuation_scope"


def test_conflicting_identifiers_return_retryable_conflict() -> None:
    result = assemble_external_dependencies_from_decisions(
        dependency_decisions=[
            {
                "candidate_id": "parcel_2_continuation_scope",
                "dependency_id": "other_dependency",
                "disposition": "include",
                "status": "missing_source",
            }
        ],
        candidates=[
            _candidate(),
            _candidate(
                candidate_id="other_scope",
                dependency_id="other_dependency",
            ),
        ],
    )
    _assert_retryable(result, reason_code="dependency_decision_identifier_conflict")
    assert "rows" not in result


def test_missing_identifier_returns_retryable_candidate_id_required() -> None:
    result = assemble_external_dependencies_from_decisions(
        dependency_decisions=[{"disposition": "include", "status": "missing_source"}],
        candidates=[_candidate()],
    )
    _assert_retryable(result, reason_code="dependency_decision_candidate_id_required")


def test_unknown_identifier_returns_retryable_refusal_and_no_row() -> None:
    result = assemble_external_dependencies_from_decisions(
        dependency_decisions=[
            {
                "dependency_id": "unknown_dependency",
                "disposition": "include",
                "status": "missing_source",
            }
        ],
        candidates=[_candidate()],
    )
    _assert_retryable(result, reason_code="dependency_decision_candidate_unknown")
    assert "rows" not in result


def test_r00000034_turn_13_dependency_id_shape_succeeds() -> None:
    """Exact replay shape from deed-to-ir-live-r00000034 turn 13."""
    result = assemble_external_dependencies_from_decisions(
        dependency_decisions=[
            {
                "dependency_id": "parcel_2_continuation_scope",
                "disposition": "include",
                "status": "missing_source",
            }
        ],
        candidates=[_candidate()],
    )
    assert result["executed"] is True
    assert result["rows"][0]["dependency_id"] == "parcel_2_continuation_scope"
    assert result["rows"][0]["affected_scope"] == "parcel_2"
