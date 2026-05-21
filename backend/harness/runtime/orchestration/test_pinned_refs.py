"""Unit tests for generic pinned-ref mechanics."""

from __future__ import annotations

from typing import Any

import pytest

from harness.runtime.orchestration.pinned_refs import (
    DEFAULT_PIN_TTL_TURNS,
    MAX_EXPIRED_PIN_TAIL,
    MAX_PIN_UNPIN_LIST_REFS,
    MAX_PINNED_REFS,
    PinnedRefsValidationError,
    active_pinned_rows,
    apply_pin_updates,
    build_pinned_refs_projection,
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
