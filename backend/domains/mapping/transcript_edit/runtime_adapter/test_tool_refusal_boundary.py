"""Tests for canonical transcript-edit tool refusal boundary."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from domains.mapping.transcript_edit.runtime_adapter.tool_refusal_boundary import (
    _RETRYABLE_REASON_CODES_BY_ACTION,
    apply_tool_refusal_boundary,
    retryable_reason_codes_for_action,
)


def _terminal_refusal(action_id: str, reason_code: str) -> dict[str, Any]:
    return {
        "executed": False,
        "refusal": {
            "reason_code": reason_code,
            "retryable": False,
            "blocked_by_invariant": True,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {"error": {"code": reason_code, "message": "terminal"}},
    }


def _retryable_refusal(action_id: str, reason_code: str) -> dict[str, Any]:
    return {
        "executed": False,
        "refusal": {
            "reason_code": reason_code,
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {"error": {"code": reason_code, "message": "already retryable"}},
    }


def _success(action_id: str) -> dict[str, Any]:
    return {
        "executed": True,
        "outputs": {"ok": True},
        "artifact_refs": ["transcript_edit:working:rev:0001"],
    }


@pytest.mark.parametrize(
    ("action_id", "reason_code"),
    [
        (action_id, reason_code)
        for action_id, codes in _RETRYABLE_REASON_CODES_BY_ACTION.items()
        for reason_code in sorted(codes)
    ],
)
def test_allowlisted_refusals_become_retryable(action_id: str, reason_code: str) -> None:
    original = _terminal_refusal(action_id, reason_code)
    original["outputs"]["repair_hint"] = "fix the field name"
    original["outputs"]["missing"] = ["ref_ids"]

    result = apply_tool_refusal_boundary(action_id, original)

    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == reason_code
    assert result["refusal"]["retryable"] is True
    assert result["refusal"]["blocked_by_invariant"] is False
    assert result["refusal"]["blocked_by_budget"] is False
    assert result["outputs"]["error"]["code"] == reason_code
    assert result["outputs"]["repair_hint"] == "fix the field name"
    assert result["outputs"]["missing"] == ["ref_ids"]


@pytest.mark.parametrize(
    ("action_id", "reason_code"),
    [
        ("hydrate_artifact_refs", "workspace_required"),
        ("hydrate_artifact_refs", "transcript_edit_tool_error"),
        ("hydrate_artifact_refs", "invalid_request_transport"),
        ("hydrate_artifact_refs", "unknown_reason_code"),
        ("transform_artifact", "transform_failed"),
        ("transform_artifact", "derived_persist_failed"),
        ("transform_artifact", "workspace_required"),
        ("save_workspace_artifact", "invalid_scope_path"),
        ("save_workspace_artifact", "transcript_edit_tool_error"),
        ("copy_forward_save_workspace_artifact", "invalid_scope_path"),
        ("copy_forward_save_workspace_artifact", "leaf_action_failed"),
        ("publish_workspace_artifact", "dossier_publication_storage_failed"),
        ("publish_workspace_artifact", "dossier_publication_pointer_invalid"),
        ("publish_workspace_artifact", "dossier_publication_revision_invalid"),
        ("publish_workspace_artifact", "dossier_publication_failed"),
        ("publish_workspace_artifact", "candidate_fingerprint_mismatch"),
    ],
)
def test_terminal_and_unknown_codes_remain_unchanged(action_id: str, reason_code: str) -> None:
    original = _terminal_refusal(action_id, reason_code)
    expected = copy.deepcopy(original)

    result = apply_tool_refusal_boundary(action_id, original)

    assert result == expected
    assert result["refusal"]["retryable"] is False
    assert result["refusal"]["blocked_by_invariant"] is True


def test_success_results_remain_unchanged() -> None:
    original = _success("hydrate_artifact_refs")
    expected = copy.deepcopy(original)

    result = apply_tool_refusal_boundary("hydrate_artifact_refs", original)

    assert result == expected


def test_already_retryable_transform_params_remain_unchanged() -> None:
    original = _retryable_refusal("transform_artifact", "invalid_transform_params")
    original["refusal"]["missing_inputs"] = ["params.crop_box"]
    expected = copy.deepcopy(original)

    result = apply_tool_refusal_boundary("transform_artifact", original)

    assert result == expected


def test_malformed_results_without_refusal_remain_unchanged() -> None:
    original = {"executed": False, "outputs": {"error": "nope"}}
    expected = copy.deepcopy(original)

    result = apply_tool_refusal_boundary("hydrate_artifact_refs", original)

    assert result == expected


@pytest.mark.parametrize(
    "executed_value",
    [
        pytest.param("missing", id="missing"),
        pytest.param(None, id="none"),
        pytest.param(0, id="zero"),
        pytest.param("false", id="string_false"),
    ],
)
def test_non_canonical_executed_values_remain_unchanged(executed_value: Any) -> None:
    if executed_value == "missing":
        original: dict[str, Any] = {
            "refusal": {
                "reason_code": "ref_ids_required",
                "retryable": False,
                "blocked_by_invariant": True,
            },
            "outputs": {"error": {"code": "ref_ids_required"}},
        }
    else:
        original = {
            "executed": executed_value,
            "refusal": {
                "reason_code": "ref_ids_required",
                "retryable": False,
                "blocked_by_invariant": True,
            },
            "outputs": {"error": {"code": "ref_ids_required"}},
        }
    expected = copy.deepcopy(original)

    result = apply_tool_refusal_boundary("hydrate_artifact_refs", original)

    assert result == expected
    assert result.get("refusal", {}).get("retryable") is False


@pytest.mark.parametrize(
    "reason_code",
    [
        None,
        404,
        "",
        "   ",
    ],
)
def test_malformed_reason_code_remains_unchanged(reason_code: Any) -> None:
    original = {
        "executed": False,
        "refusal": {
            "reason_code": reason_code,
            "retryable": False,
            "blocked_by_invariant": True,
        },
        "outputs": {"error": {"code": reason_code}},
    }
    expected = copy.deepcopy(original)

    result = apply_tool_refusal_boundary("hydrate_artifact_refs", original)

    assert result == expected


@pytest.mark.parametrize(
    "action_id",
    [
        None,
        123,
        "",
        "   ",
    ],
)
def test_malformed_action_id_remains_unchanged(action_id: Any) -> None:
    original = _terminal_refusal("hydrate_artifact_refs", "ref_ids_required")
    expected = copy.deepcopy(original)

    result = apply_tool_refusal_boundary(action_id, original)

    assert result == expected


def test_exact_executed_false_allowlisted_refusal_still_reclassifies() -> None:
    original = _terminal_refusal("hydrate_artifact_refs", "ref_ids_required")

    result = apply_tool_refusal_boundary("hydrate_artifact_refs", original)

    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == "ref_ids_required"
    assert result["refusal"]["retryable"] is True
    assert result["refusal"]["blocked_by_invariant"] is False
    assert result["refusal"]["blocked_by_budget"] is False


def test_non_mapping_input_passes_through() -> None:
    assert apply_tool_refusal_boundary("hydrate_artifact_refs", "not-a-mapping") == "not-a-mapping"


def test_retryable_reason_codes_for_action_unknown_returns_empty() -> None:
    assert retryable_reason_codes_for_action("unknown_action") == frozenset()


@pytest.mark.parametrize("action_id", list(_RETRYABLE_REASON_CODES_BY_ACTION))
def test_each_action_has_non_empty_allowlist(action_id: str) -> None:
    assert retryable_reason_codes_for_action(action_id)
