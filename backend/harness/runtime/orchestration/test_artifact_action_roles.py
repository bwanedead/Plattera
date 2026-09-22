"""Closure-policy artifact action roles and the observability that consumes them."""

from __future__ import annotations

from pathlib import Path

import pytest

from domains.mapping.transcript_edit.semantics.closure import (
    build_transcript_edit_closure_policy,
)
from harness.runtime.orchestration.artifact_action_roles import (
    ArtifactActionRoleConfigError,
    resolve_artifact_action_roles,
)
from harness.runtime.orchestration.loop_health_summary import build_prompt_observability_summary
from harness.runtime.orchestration.test_loop_health_summary import (
    _hitl_turn,
    _hydrate_record,
    _mem,
    _read_record,
    _step_record,
)

_DEFAULT_WORKING = frozenset(
    {"save_workspace_artifact", "copy_forward_save_workspace_artifact"}
)
_DEFAULT_PUBLISH = frozenset({"publish_workspace_artifact"})
_SYNTHETIC_POLICY = {
    "save_action_ids": ("persist_draft", "patch_exact_claims"),
    "publish_action_ids": ("release_output",),
}
_REPO_ROOT = Path(__file__).resolve().parents[4]


class _DeceptiveActionId:
    def __str__(self) -> str:
        return "persist_draft"


def test_absent_closure_policy_uses_existing_defaults() -> None:
    roles = resolve_artifact_action_roles(None)
    assert roles.working_write_action_ids == _DEFAULT_WORKING
    assert roles.publish_action_ids == _DEFAULT_PUBLISH


def test_absent_role_field_uses_its_existing_default() -> None:
    working_only = resolve_artifact_action_roles({"save_action_ids": ["persist_draft"]})
    assert working_only.working_write_action_ids == frozenset({"persist_draft"})
    assert working_only.publish_action_ids == _DEFAULT_PUBLISH

    publish_only = resolve_artifact_action_roles({"publish_action_ids": ["release_output"]})
    assert publish_only.working_write_action_ids == _DEFAULT_WORKING
    assert publish_only.publish_action_ids == frozenset({"release_output"})

    assert resolve_artifact_action_roles({}).working_write_action_ids == _DEFAULT_WORKING
    assert resolve_artifact_action_roles({}).publish_action_ids == _DEFAULT_PUBLISH


def test_present_empty_role_lane_stays_empty() -> None:
    roles = resolve_artifact_action_roles(
        {"save_action_ids": [], "publish_action_ids": ()}
    )
    assert roles.working_write_action_ids == frozenset()
    assert roles.publish_action_ids == frozenset()
    assert roles.materialize_action_ids == frozenset()

    save_only_empty = resolve_artifact_action_roles({"save_action_ids": ()})
    assert save_only_empty.working_write_action_ids == frozenset()
    assert save_only_empty.publish_action_ids == _DEFAULT_PUBLISH


def test_valid_custom_save_action_ids_replace_the_default_working_write_set() -> None:
    roles = resolve_artifact_action_roles(_SYNTHETIC_POLICY)
    assert roles.working_write_action_ids == frozenset({"persist_draft", "patch_exact_claims"})
    assert "save_workspace_artifact" not in roles.working_write_action_ids


def test_valid_custom_publish_action_ids_replace_the_default_publish_set() -> None:
    roles = resolve_artifact_action_roles(_SYNTHETIC_POLICY)
    assert roles.publish_action_ids == frozenset({"release_output"})
    assert "publish_workspace_artifact" not in roles.publish_action_ids


def test_duplicate_valid_strings_deduplicate_and_trim() -> None:
    roles = resolve_artifact_action_roles(
        {
            "save_action_ids": [" persist_draft ", "persist_draft", "patch_exact_claims"],
            "publish_action_ids": ("release_output", " release_output "),
        }
    )
    assert roles.working_write_action_ids == frozenset({"persist_draft", "patch_exact_claims"})
    assert roles.publish_action_ids == frozenset({"release_output"})


def test_blank_strings_refuse_the_present_lane() -> None:
    with pytest.raises(ArtifactActionRoleConfigError):
        resolve_artifact_action_roles({"save_action_ids": ["persist_draft", "  "]})
    with pytest.raises(ArtifactActionRoleConfigError):
        resolve_artifact_action_roles({"publish_action_ids": [""]})


@pytest.mark.parametrize(
    "member",
    [
        True,
        False,
        1,
        1.5,
        {"action": "persist_draft"},
        ["persist_draft"],
        _DeceptiveActionId(),
    ],
)
def test_non_strings_never_become_action_ids(member: object) -> None:
    with pytest.raises(ArtifactActionRoleConfigError) as caught:
        resolve_artifact_action_roles({"save_action_ids": ["persist_draft", member]})
    assert "persist_draft" not in str(caught.value)
    with pytest.raises(ArtifactActionRoleConfigError):
        resolve_artifact_action_roles({"publish_action_ids": (member,)})


def test_malformed_present_lane_is_not_replaced_with_defaults() -> None:
    with pytest.raises(ArtifactActionRoleConfigError):
        resolve_artifact_action_roles({"save_action_ids": "persist_draft"})
    with pytest.raises(ArtifactActionRoleConfigError):
        resolve_artifact_action_roles({"publish_action_ids": {"release_output"}})
    with pytest.raises(ArtifactActionRoleConfigError):
        resolve_artifact_action_roles(["not-a-mapping"])


def test_save_and_publish_roles_stay_distinct_and_materialize_is_their_union() -> None:
    roles = resolve_artifact_action_roles(_SYNTHETIC_POLICY)
    assert roles.working_write_action_ids.isdisjoint(roles.publish_action_ids)
    assert roles.materialize_action_ids == (
        roles.working_write_action_ids | roles.publish_action_ids
    )
    assert roles.materialize_action_ids == frozenset(
        {"persist_draft", "patch_exact_claims", "release_output"}
    )


def _summary(records: list[dict], policy: dict | None = None):
    return build_prompt_observability_summary(
        _mem(step_records=records),
        closure_policy=policy,
    )


def test_successful_custom_working_write_establishes_baseline_and_later_state_is_dirty() -> None:
    dirty = _summary(
        [
            _step_record(1, action_type="persist_draft", work_state_signature="saved"),
            _step_record(2, action_type="no_dispatch", work_state_signature="changed"),
        ],
        _SYNTHETIC_POLICY,
    )
    assert dirty["artifact_state_dirty_since_write_count"] == 1
    assert "artifact_state_dirty_since_write:1" in dirty["mechanical_flags"]


def test_another_successful_custom_working_write_clears_dirty_since_write() -> None:
    cleared = _summary(
        [
            _step_record(1, action_type="persist_draft", work_state_signature="saved"),
            _step_record(2, action_type="no_dispatch", work_state_signature="changed"),
            _step_record(3, action_type="patch_exact_claims", work_state_signature="changed"),
        ],
        _SYNTHETIC_POLICY,
    )
    assert cleared["artifact_state_dirty_since_write_count"] == 0


def test_failed_or_refused_custom_working_write_does_not_clear_dirty_since_write() -> None:
    refused = _summary(
        [
            _step_record(1, action_type="persist_draft", work_state_signature="saved"),
            _step_record(2, action_type="no_dispatch", work_state_signature="changed"),
            _step_record(
                3,
                action_type="patch_exact_claims",
                work_state_signature="changed",
                execution_state="refused",
            ),
        ],
        _SYNTHETIC_POLICY,
    )
    assert refused["artifact_state_dirty_since_write_count"] == 2
    assert refused["post_write_artifact_consistency_check_count"] == 0


def test_custom_publish_counts_as_materialization_but_not_as_working_write() -> None:
    materialized = _summary(
        [
            _step_record(1, action_type="persist_draft", work_state_signature="saved"),
            _step_record(2, action_type="no_dispatch", work_state_signature="changed"),
            _step_record(3, action_type="release_output", work_state_signature="changed"),
        ],
        _SYNTHETIC_POLICY,
    )
    assert materialized["artifact_state_dirty_since_write_count"] == 0
    assert materialized["post_write_artifact_consistency_check_count"] == 0


def test_similarly_named_undeclared_action_does_not_count_as_a_write() -> None:
    still_dirty = _summary(
        [
            _step_record(1, action_type="persist_draft", work_state_signature="saved"),
            _step_record(2, action_type="no_dispatch", work_state_signature="changed"),
            _step_record(
                3,
                action_type="persist_draft_snapshot",
                work_state_signature="changed",
            ),
        ],
        _SYNTHETIC_POLICY,
    )
    assert still_dirty["artifact_state_dirty_since_write_count"] == 2
    generic_save = _summary(
        [
            _step_record(1, action_type="persist_draft", work_state_signature="saved"),
            _step_record(2, action_type="no_dispatch", work_state_signature="changed"),
            _step_record(
                3,
                action_type="save_workspace_artifact",
                work_state_signature="changed",
            ),
        ],
        _SYNTHETIC_POLICY,
    )
    assert generic_save["artifact_state_dirty_since_write_count"] == 2


def test_post_write_consistency_recognizes_the_custom_working_write() -> None:
    result = _summary(
        [_step_record(1, action_type="patch_exact_claims", work_state_signature="saved")],
        _SYNTHETIC_POLICY,
    )
    assert result["post_write_artifact_consistency_check_count"] == 1
    assert "post_write_artifact_consistency_check:1" in result["mechanical_flags"]


def test_repair_ready_cadence_recognizes_the_custom_working_write() -> None:
    feedback = {"semantic_repair_debt": ["determined_value"]}
    recognized = build_prompt_observability_summary(
        _mem(
            step_records=[
                _read_record(1),
                _read_record(2),
                _step_record(3, action_type="persist_draft", work_state_signature="saved"),
            ],
            state_patch_feedback=feedback,
        ),
        closure_policy=_SYNTHETIC_POLICY,
    )
    assert recognized["repair_ready_without_artifact_write_count"] == 0


def test_post_hitl_progress_recognizes_the_custom_working_write() -> None:
    refs = {"r": "v"}
    result = _summary(
        [
            _hitl_turn(1, refs=refs, state_sig="sig-a"),
            _step_record(
                2,
                action_type="hydrate_artifact_refs",
                latest_refs_snapshot=refs,
                work_state_signature="sig-a",
            ),
            _step_record(
                3,
                action_type="hydrate_artifact_refs",
                latest_refs_snapshot=refs,
                work_state_signature="sig-a",
            ),
            _step_record(
                4,
                action_type="persist_draft",
                latest_refs_snapshot=refs,
                work_state_signature="sig-a",
            ),
        ],
        _SYNTHETIC_POLICY,
    )
    assert result["post_hitl_spin_count"] == 0


def test_artifact_refresh_lookback_recognizes_the_custom_working_write() -> None:
    refs = {"working": "artifact://working:rev:0001"}
    result = _summary(
        [
            _step_record(
                1,
                action_type="persist_draft",
                latest_refs_snapshot=refs,
                work_state_signature="state-constant",
            ),
            _hydrate_record(2, refs=refs),
            _hydrate_record(3, refs=refs),
            _hydrate_record(4, refs=refs),
        ],
        _SYNTHETIC_POLICY,
    )
    assert result["artifact_refresh_trap_risk_count"] == 3


def _transcript_edit_closure_policy() -> dict:
    policy = build_transcript_edit_closure_policy()
    return {
        "save_action_ids": policy.save_action_ids,
        "publish_action_ids": policy.publish_action_ids,
    }


def test_transcript_edit_closure_policy_classifies_working_writes_and_publication() -> None:
    roles = resolve_artifact_action_roles(_transcript_edit_closure_policy())
    assert "initialize_working_transcript" in roles.working_write_action_ids
    assert "apply_transcript_edits" in roles.working_write_action_ids
    assert "save_workspace_artifact" in roles.working_write_action_ids
    assert "copy_forward_save_workspace_artifact" in roles.working_write_action_ids
    assert roles.publish_action_ids == frozenset({"publish_workspace_artifact"})
    assert "publish_workspace_artifact" not in roles.working_write_action_ids
    assert "apply_transcript_edits" not in roles.publish_action_ids
    assert "initialize_working_transcript" not in roles.publish_action_ids


def test_initialized_revision_then_state_change_is_dirty_until_successful_apply() -> None:
    policy = _transcript_edit_closure_policy()
    dirty = _summary(
        [
            _step_record(
                1,
                action_type="initialize_working_transcript",
                work_state_signature="rev-0001",
            ),
            _step_record(2, action_type="no_dispatch", work_state_signature="determinations"),
        ],
        policy,
    )
    assert dirty["artifact_state_dirty_since_write_count"] == 1

    applied = _summary(
        [
            _step_record(
                1,
                action_type="initialize_working_transcript",
                work_state_signature="rev-0001",
            ),
            _step_record(2, action_type="no_dispatch", work_state_signature="determinations"),
            _step_record(
                3,
                action_type="apply_transcript_edits",
                work_state_signature="determinations",
            ),
        ],
        policy,
    )
    assert applied["artifact_state_dirty_since_write_count"] == 0
    assert applied["post_write_artifact_consistency_check_count"] == 1


def test_refused_apply_does_not_clear_drift_or_count_as_publication() -> None:
    policy = _transcript_edit_closure_policy()
    refused = _summary(
        [
            _step_record(
                1,
                action_type="initialize_working_transcript",
                work_state_signature="rev-0001",
            ),
            _step_record(2, action_type="no_dispatch", work_state_signature="determinations"),
            _step_record(
                3,
                action_type="apply_transcript_edits",
                work_state_signature="determinations",
                execution_state="refused",
            ),
        ],
        policy,
    )
    assert refused["artifact_state_dirty_since_write_count"] == 2
    assert refused["post_write_artifact_consistency_check_count"] == 0

    published = _summary(
        [
            _step_record(
                1,
                action_type="apply_transcript_edits",
                work_state_signature="determinations",
            ),
            _step_record(
                2,
                action_type="publish_workspace_artifact",
                work_state_signature="determinations",
            ),
        ],
        policy,
    )
    assert published["artifact_state_dirty_since_write_count"] == 0
    assert published["post_write_artifact_consistency_check_count"] == 0


def test_observability_modules_do_not_import_transcript_edit() -> None:
    forbidden = (
        "apply_transcript_edits",
        "initialize_working_transcript",
        "domains.mapping.transcript_edit",
        "tooling.mapping.transcript_edit",
    )
    paths = (
        _REPO_ROOT / "backend/harness/runtime/orchestration/artifact_action_roles.py",
        _REPO_ROOT / "backend/harness/runtime/orchestration/loop_health_summary.py",
        _REPO_ROOT / "backend/harness/runtime/orchestration/choose_action_instruction.py",
    )
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"{path.name} contains {token}"


def test_changelog_keeps_artifact_role_row_separate() -> None:
    changelog = (
        _REPO_ROOT / "docs/architecture/harness/doctrine-changelog.md"
    ).read_text(encoding="utf-8")
    rows = [line for line in changelog.splitlines() if line.startswith("| 20")]
    role_row = next(row for row in rows if "v45 to v46" in row)
    cells = [cell.strip() for cell in role_row.strip("|").split("|")]
    assert len(cells) == 5
    assert "No semantic readiness classifier" in role_row
    assert "no trunk-body rewrite" in role_row
    assert "no automatic write" in role_row
    window_row = next(row for row in rows if "procedural v48→v49" in row)
    assert "v45 to v46" not in window_row
    assert "small_plus" not in role_row
