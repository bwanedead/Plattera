"""Tests for generic stable_context memory lane."""

from __future__ import annotations

import importlib
import inspect

import pytest

from harness.runtime.memory.stable_context import (
    STABLE_CONTEXT_CAVEAT,
    StableContextValidationError,
    apply_stable_context_patch,
    build_stable_context_audit_projection,
    build_stable_context_projection,
    context_is_active_for_prompt,
    validate_stored_stable_context_row,
)


def _sample_row(**overrides):
    base = {
        "context_id": "parcel_1_t0_shape",
        "title": "Parcel 1 T0 shape",
        "role": "orientation_memory",
        "body": "Agent-authored bounded context note.",
        "basis_refs": ["t0:raw:draft_1"],
        "attached_entity_ids": ["p1_call1_distance"],
        "status": "active",
        "created_turn": 2,
        "updated_turn": 5,
        "expires_after_turns": 12,
    }
    base.update(overrides)
    return base


def test_create_active_context_via_upsert() -> None:
    rows, feedback = apply_stable_context_patch(
        [],
        {
            "upsert": [
                {
                    "context_id": "parcel_1_t0_shape",
                    "role": "orientation_memory",
                    "body": "Agent-authored note.",
                    "basis_refs": ["t0:raw:draft_1"],
                    "attached_entity_ids": ["p1_call1_distance"],
                }
            ]
        },
        current_turn=2,
    )
    assert feedback["upserted"] == ["parcel_1_t0_shape"]
    assert len(rows) == 1
    assert rows[0]["context_id"] == "parcel_1_t0_shape"
    assert rows[0]["status"] == "active"
    assert rows[0]["created_turn"] == 2
    assert rows[0]["updated_turn"] == 2


def test_upsert_replaces_same_context_id() -> None:
    rows, _ = apply_stable_context_patch(
        [],
        {"upsert": [{"context_id": "ctx_a", "body": "first"}]},
        current_turn=1,
    )
    rows, feedback = apply_stable_context_patch(
        rows,
        {"upsert": [{"context_id": "ctx_a", "body": "second", "title": "Updated"}]},
        current_turn=4,
    )
    assert feedback["upserted"] == ["ctx_a"]
    assert len(rows) == 1
    assert rows[0]["body"] == "second"
    assert rows[0]["title"] == "Updated"
    assert rows[0]["created_turn"] == 1
    assert rows[0]["updated_turn"] == 4


def test_retire_context_sets_status_without_delete() -> None:
    rows, _ = apply_stable_context_patch(
        [],
        {"upsert": [{"context_id": "ctx_a", "body": "note"}]},
        current_turn=1,
    )
    rows, feedback = apply_stable_context_patch(
        rows,
        {"retire": ["ctx_a"]},
        current_turn=3,
    )
    assert feedback["retired"] == ["ctx_a"]
    assert len(rows) == 1
    assert rows[0]["status"] == "retired"
    assert rows[0]["body"] == "note"


def test_invalid_upsert_row_skipped_without_partial_semantic_state() -> None:
    rows, feedback = apply_stable_context_patch(
        [],
        {
            "upsert": [
                {"context_id": "", "body": "bad"},
                {"context_id": "good_ctx", "body": "ok"},
            ]
        },
        current_turn=1,
    )
    assert len(rows) == 1
    assert rows[0]["context_id"] == "good_ctx"
    assert len(feedback["skipped_rows"]) == 1


def test_body_sanitization_rejects_absolute_path() -> None:
    for body in (
        "C:\\secret\\note.txt",
        "See C:\\secret\\note.txt",
        "/home/user/file.txt",
        "See /home/user/file.txt",
    ):
        rows, feedback = apply_stable_context_patch(
            [],
            {"upsert": [{"context_id": "bad_body", "body": body}]},
            current_turn=1,
        )
        assert rows == []
        assert feedback["skipped_rows"]


def test_body_sanitization_rejects_pem_marker() -> None:
    rows, feedback = apply_stable_context_patch(
        [],
        {"upsert": [{"context_id": "bad_body", "body": "prefix -----BEGIN PRIVATE KEY----- suffix"}]},
        current_turn=1,
    )
    assert rows == []
    assert feedback["skipped_rows"]


def test_body_and_ref_caps_enforced() -> None:
    rows, feedback = apply_stable_context_patch(
        [],
        {
            "upsert": [
                {
                    "context_id": "x" * 200,
                    "body": "ok",
                }
            ]
        },
        current_turn=1,
    )
    assert rows == []
    assert feedback["skipped_rows"]

    long_ref = "r" * 600
    rows, _ = apply_stable_context_patch(
        [],
        {
            "upsert": [
                {
                    "context_id": "ctx_refs",
                    "basis_refs": [long_ref, "good_ref"],
                }
            ]
        },
        current_turn=1,
    )
    assert rows[0]["basis_refs"] == ["good_ref"]


def test_prompt_projection_excludes_retired_and_expired() -> None:
    rows, _ = apply_stable_context_patch(
        [],
        {
            "upsert": [
                {"context_id": "active_ctx", "body": "active", "expires_after_turns": 5},
                {"context_id": "retired_ctx", "body": "retired"},
            ]
        },
        current_turn=10,
    )
    rows, _ = apply_stable_context_patch(rows, {"retire": ["retired_ctx"]}, current_turn=11)

    projection = build_stable_context_projection(rows, current_turn=20)
    assert projection is None

    rows, _ = apply_stable_context_patch(
        [],
        {"upsert": [{"context_id": "fresh", "body": "still valid", "expires_after_turns": 8}]},
        current_turn=10,
    )
    projection = build_stable_context_projection(rows, current_turn=12)
    assert projection is not None
    assert projection["active"][0]["context_id"] == "fresh"


def test_projection_includes_generic_caveat() -> None:
    rows, _ = apply_stable_context_patch(
        [],
        {"upsert": [{"context_id": "ctx", "body": "note"}]},
        current_turn=1,
    )
    projection = build_stable_context_projection(rows, current_turn=1)
    assert projection is not None
    assert projection["caveat"] == STABLE_CONTEXT_CAVEAT


def test_audit_projection_preserves_retired_history() -> None:
    rows, _ = apply_stable_context_patch(
        [],
        {"upsert": [{"context_id": "ctx", "body": "note"}]},
        current_turn=1,
    )
    rows, _ = apply_stable_context_patch(rows, {"retire": ["ctx"]}, current_turn=2)
    audit = build_stable_context_audit_projection(rows, current_turn=2)
    assert audit is not None
    assert audit["retired"][0]["context_id"] == "ctx"
    assert "body_excerpt" in audit["retired"][0]


def test_validate_stored_row_round_trip() -> None:
    stored = validate_stored_stable_context_row(_sample_row())
    assert stored is not None
    assert stored["context_id"] == "parcel_1_t0_shape"


def test_unknown_patch_branch_keys_raise() -> None:
    with pytest.raises(StableContextValidationError, match="unknown keys"):
        apply_stable_context_patch([], {"upsert": [], "extra": 1}, current_turn=1)


def test_generic_harness_has_no_domain_imports() -> None:
    mod = importlib.import_module("harness.runtime.memory.stable_context")
    source = inspect.getsource(mod)
    assert "transcript_edit" not in source
    assert "from domains." not in source
    assert "attached_atom_ids" not in source
