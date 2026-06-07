"""Unit tests for generic pinned-ref mechanics."""

from __future__ import annotations

from typing import Any

import pytest

from harness.runtime.orchestration.pinned_refs import (
    DEFAULT_PIN_TTL_TURNS,
    MAX_EXPIRED_PIN_TAIL,
    MAX_PIN_UNPIN_LIST_REFS,
    MAX_PINNED_REFS,
    PIN_EXPIRING_SOON_TURNS,
    PinnedRefsValidationError,
    active_pinned_rows,
    apply_pin_updates,
    build_pinned_refs_projection,
    expires_in_turns,
    normalize_pin_ref_list,
    pin_is_active,
    validate_stored_pinned_ref_row,
)


def test_normalize_pin_ref_list_dedupes_and_trims() -> None:
    refs = normalize_pin_ref_list(["  a  ", "a", "b"], field_name="pin_refs")
    assert refs == ("a", "b")


def test_normalize_pin_ref_list_rejects_empty_string() -> None:
    with pytest.raises(PinnedRefsValidationError):
        normalize_pin_ref_list([" "], field_name="pin_refs")


def test_normalize_pin_ref_list_rejects_over_cap() -> None:
    with pytest.raises(PinnedRefsValidationError, match=str(MAX_PIN_UNPIN_LIST_REFS)):
        normalize_pin_ref_list(
            [f"ref:{i}" for i in range(MAX_PIN_UNPIN_LIST_REFS + 1)],
            field_name="pin_refs",
        )


def test_pin_ttl_expiry() -> None:
    row = {
        "ref": "r1",
        "pinned_at_turn": 1,
        "last_refreshed_turn": 1,
        "ttl_turns": 2,
    }
    assert pin_is_active(row, current_turn=3)
    assert not pin_is_active(row, current_turn=4)


def test_apply_pin_updates_caps_active_pins() -> None:
    rows = apply_pin_updates(
        [],
        pin_refs=tuple(f"ref:{i}" for i in range(8)),
        unpin_refs=(),
        current_turn=5,
    )
    active = active_pinned_rows(rows, current_turn=5)
    assert len(active) <= MAX_PINNED_REFS


def test_unpin_removes_ref() -> None:
    rows = apply_pin_updates(
        [],
        pin_refs=("a", "b"),
        unpin_refs=(),
        current_turn=1,
    )
    rows = apply_pin_updates(rows, pin_refs=(), unpin_refs=("a",), current_turn=2)
    active = active_pinned_rows(rows, current_turn=2)
    assert [row["ref"] for row in active] == ["b"]


def test_refresh_pin_extends_ttl() -> None:
    rows = apply_pin_updates([], pin_refs=("a",), unpin_refs=(), current_turn=1)
    rows = apply_pin_updates(rows, pin_refs=("a",), unpin_refs=(), current_turn=10)
    row = active_pinned_rows(rows, current_turn=10 + DEFAULT_PIN_TTL_TURNS)[0]
    assert row["last_refreshed_turn"] == 10


def test_expires_in_turns_clamps_at_zero_for_active_rows() -> None:
    row = {
        "ref": "r1",
        "pinned_at_turn": 1,
        "last_refreshed_turn": 10,
        "ttl_turns": DEFAULT_PIN_TTL_TURNS,
    }
    assert expires_in_turns(row, current_turn=10 + DEFAULT_PIN_TTL_TURNS) == 0
    assert pin_is_active(row, current_turn=10 + DEFAULT_PIN_TTL_TURNS)


def test_build_projection_includes_expires_in_turns_on_active_rows() -> None:
    rows = apply_pin_updates([], pin_refs=("soon", "fresh"), unpin_refs=(), current_turn=1)
    rows = apply_pin_updates(rows, pin_refs=("fresh",), unpin_refs=(), current_turn=20)
    projection = build_pinned_refs_projection(rows, current_turn=20)
    active_by_ref = {row["ref"]: row for row in projection["active"]}
    assert "expires_in_turns" in active_by_ref["fresh"]
    assert active_by_ref["fresh"]["expires_in_turns"] == DEFAULT_PIN_TTL_TURNS


def test_build_projection_expiring_soon_lane_within_threshold() -> None:
    rows = apply_pin_updates([], pin_refs=("soon",), unpin_refs=(), current_turn=1)
    current_turn = 1 + DEFAULT_PIN_TTL_TURNS - PIN_EXPIRING_SOON_TURNS
    projection = build_pinned_refs_projection(rows, current_turn=current_turn)
    assert projection["active"][0]["expires_in_turns"] == PIN_EXPIRING_SOON_TURNS
    assert projection.get("expiring_soon")
    assert projection["expiring_soon"][0]["ref"] == "soon"
    assert projection["expiring_soon"][0]["ttl_turns"] == DEFAULT_PIN_TTL_TURNS


def test_build_projection_omits_expiring_soon_when_ttl_comfortable() -> None:
    rows = apply_pin_updates([], pin_refs=("fresh",), unpin_refs=(), current_turn=10)
    projection = build_pinned_refs_projection(rows, current_turn=10)
    assert "expiring_soon" not in projection
    assert projection["active"][0]["expires_in_turns"] > PIN_EXPIRING_SOON_TURNS


def test_expired_refs_stay_in_expired_not_expiring_soon() -> None:
    rows = apply_pin_updates([], pin_refs=("old",), unpin_refs=(), current_turn=1)
    projection = build_pinned_refs_projection(rows, current_turn=1 + DEFAULT_PIN_TTL_TURNS + 1)
    assert projection.get("expired")
    assert any(row["ref"] == "old" for row in projection["expired"])
    assert "expiring_soon" not in projection


def test_build_projection_includes_active_and_expired() -> None:
    rows = apply_pin_updates([], pin_refs=("old", "new"), unpin_refs=(), current_turn=1)
    rows = apply_pin_updates(rows, pin_refs=("new",), unpin_refs=(), current_turn=20)
    projection = build_pinned_refs_projection(rows, current_turn=20)
    assert any(row["ref"] == "new" for row in projection["active"])
    assert projection.get("expired")


def test_validate_stored_pinned_ref_row_rejects_malformed() -> None:
    assert validate_stored_pinned_ref_row({"ref": ""}) is None
    assert validate_stored_pinned_ref_row("not-a-map") is None


def test_apply_pin_updates_prunes_expired_tail() -> None:
    rows: list[dict[str, Any]] = []
    for index in range(MAX_EXPIRED_PIN_TAIL + 3):
        rows = apply_pin_updates(
            rows,
            pin_refs=(f"expired:{index}",),
            unpin_refs=(),
            current_turn=1,
        )
    rows = apply_pin_updates(rows, pin_refs=("active:keep",), unpin_refs=(), current_turn=50)
    expired = [
        row
        for row in rows
        if not pin_is_active(row, current_turn=50)
    ]
    assert len(expired) <= MAX_EXPIRED_PIN_TAIL
