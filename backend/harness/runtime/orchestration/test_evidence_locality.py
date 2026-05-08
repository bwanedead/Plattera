"""Tests for evidence_locality.py — broad image-locator advisory detection.

Structural/mechanical checks only — no domain semantics.
"""

from __future__ import annotations

import pytest

from harness.runtime.orchestration.evidence_locality import (
    BROAD_IMAGE_AREA_THRESHOLD,
    box_norm_area,
    count_earned_exact_units_with_broad_image_locator,
    is_broad_image_locator,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _locator(
    *,
    locator_kind: str = "image_region",
    box_norm: list[float] | None = None,
) -> dict:
    loc: dict = {"locator_kind": locator_kind}
    if box_norm is not None:
        loc["box_norm"] = box_norm
    return loc


def _unit(
    *,
    determined_value: str | None = "42",
    status: str = "closed",
    determination: str | None = None,
    locators: list | None = None,
) -> dict:
    return {
        "determined_value": determined_value,
        "status": status,
        "determination": determination,
        "evidence_locators": locators or [],
    }


def _item(*, units: list | None = None) -> dict:
    return {"covered_units": units or []}


# ---------------------------------------------------------------------------
# box_norm_area
# ---------------------------------------------------------------------------

def test_box_norm_area_unit_square() -> None:
    assert box_norm_area([0.0, 0.0, 1.0, 1.0]) == pytest.approx(1.0)


def test_box_norm_area_tight_cell() -> None:
    # 0.1 wide × 0.02 tall = 0.002 (0.2% — well under 5%)
    area = box_norm_area([0.10, 0.05, 0.20, 0.07])
    assert area == pytest.approx(0.002)


def test_box_norm_area_broad_region() -> None:
    # 0.4 wide × 0.3 tall = 0.12 (12% — over 5%)
    area = box_norm_area([0.1, 0.1, 0.5, 0.4])
    assert area == pytest.approx(0.12)


def test_box_norm_area_invalid_length_returns_one() -> None:
    assert box_norm_area([0.1, 0.2]) == 1.0


def test_box_norm_area_invalid_types_returns_one() -> None:
    assert box_norm_area(["a", "b", "c", "d"]) == 1.0  # type: ignore[arg-type]


def test_box_norm_area_zero_dimensions() -> None:
    assert box_norm_area([0.1, 0.1, 0.1, 0.1]) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# is_broad_image_locator
# ---------------------------------------------------------------------------

def test_is_broad_image_locator_tight_below_threshold() -> None:
    # 0.1 × 0.02 = 0.002 < 0.05
    loc = _locator(box_norm=[0.10, 0.05, 0.20, 0.07])
    assert is_broad_image_locator(loc) is False


def test_is_broad_image_locator_broad_above_threshold() -> None:
    # 0.4 × 0.3 = 0.12 > 0.05
    loc = _locator(box_norm=[0.1, 0.1, 0.5, 0.4])
    assert is_broad_image_locator(loc) is True


def test_is_broad_image_locator_exactly_at_threshold_is_not_broad() -> None:
    # Exactly 5%: not strictly greater, so not broad.
    # Area = 0.25 × 0.2 = 0.05
    loc = _locator(box_norm=[0.0, 0.0, 0.25, 0.2])
    assert is_broad_image_locator(loc) is False


def test_is_broad_image_locator_no_box_norm_is_broad() -> None:
    # image_region with no box_norm = maximally broad
    loc = _locator()  # no box_norm
    assert is_broad_image_locator(loc) is True


def test_is_broad_image_locator_non_image_kind_always_false() -> None:
    # text_span, table_cell, etc. — not evaluated here
    loc = _locator(locator_kind="text_span", box_norm=[0.0, 0.0, 1.0, 1.0])
    assert is_broad_image_locator(loc) is False


def test_is_broad_image_locator_non_image_kind_without_box_false() -> None:
    loc = _locator(locator_kind="table_cell")
    assert is_broad_image_locator(loc) is False


def test_is_broad_image_locator_custom_threshold() -> None:
    # Area ~8%, tight at 10% threshold but broad at 5%
    loc = _locator(box_norm=[0.1, 0.1, 0.38, 0.4])  # 0.28 × 0.3 ≈ 0.084
    assert is_broad_image_locator(loc, area_threshold=0.10) is False
    assert is_broad_image_locator(loc, area_threshold=0.05) is True


# ---------------------------------------------------------------------------
# count_earned_exact_units_with_broad_image_locator
# ---------------------------------------------------------------------------

def test_count_tight_locator_not_flagged() -> None:
    """Earned unit with a tight image locator is not counted."""
    items = [
        _item(units=[
            _unit(locators=[_locator(box_norm=[0.1, 0.1, 0.2, 0.15])]),  # area=0.05, not broad
        ])
    ]
    assert count_earned_exact_units_with_broad_image_locator(items) == 0


def test_count_broad_locator_flagged() -> None:
    """Earned unit with only a broad image locator (~8% area) is counted."""
    items = [
        _item(units=[
            _unit(locators=[_locator(box_norm=[0.1, 0.1, 0.38, 0.4])]),  # area≈0.084 > 5%
        ])
    ]
    assert count_earned_exact_units_with_broad_image_locator(items) == 1


def test_count_one_tight_one_broad_not_flagged() -> None:
    """Unit with mixed locators (one tight) is NOT counted — one tight suffices."""
    tight = _locator(box_norm=[0.1, 0.1, 0.2, 0.15])   # area = 0.05, not broad
    broad = _locator(box_norm=[0.1, 0.1, 0.5, 0.5])    # area = 0.16 > 5%
    items = [_item(units=[_unit(locators=[tight, broad])])]
    assert count_earned_exact_units_with_broad_image_locator(items) == 0


def test_count_no_locators_not_counted() -> None:
    """Earned unit with no locators at all is NOT counted here (different debt)."""
    items = [_item(units=[_unit(locators=[])])]
    assert count_earned_exact_units_with_broad_image_locator(items) == 0


def test_count_non_image_locators_only_not_counted() -> None:
    """Unit with only non-image locators (e.g. text_span) is not evaluated here."""
    items = [
        _item(units=[
            _unit(locators=[_locator(locator_kind="text_span", box_norm=[0.0, 0.0, 1.0, 1.0])])
        ])
    ]
    assert count_earned_exact_units_with_broad_image_locator(items) == 0


def test_count_group_unit_without_determined_value_not_flagged() -> None:
    """Units without a determined_value (broad/group rows) are excluded."""
    items = [
        _item(units=[
            _unit(
                determined_value=None,
                locators=[_locator(box_norm=[0.1, 0.1, 0.9, 0.9])],  # extremely broad
            )
        ])
    ]
    assert count_earned_exact_units_with_broad_image_locator(items) == 0


def test_count_open_status_without_earned_determination_not_flagged() -> None:
    """Open units with no earned determination are not in scope."""
    items = [
        _item(units=[
            _unit(
                status="open",
                determination=None,
                determined_value="x",
                locators=[_locator(box_norm=[0.1, 0.1, 0.9, 0.9])],
            )
        ])
    ]
    assert count_earned_exact_units_with_broad_image_locator(items) == 0


def test_count_earned_determination_in_progress_is_included() -> None:
    """Units with determination='earned' are in scope even if status != 'closed'."""
    items = [
        _item(units=[
            _unit(
                status="in_progress",
                determination="earned",
                determined_value="found it",
                locators=[_locator(box_norm=[0.1, 0.1, 0.9, 0.9])],  # broad
            )
        ])
    ]
    assert count_earned_exact_units_with_broad_image_locator(items) == 1


def test_count_multiple_items_multiple_units() -> None:
    """Aggregates correctly across multiple items and units."""
    tight = _locator(box_norm=[0.1, 0.1, 0.2, 0.15])
    broad = _locator(box_norm=[0.0, 0.0, 0.5, 0.4])  # area=0.20 > 5%
    items = [
        _item(units=[
            _unit(locators=[broad]),   # counted
            _unit(locators=[tight]),   # not counted
        ]),
        _item(units=[
            _unit(locators=[broad]),   # counted
            _unit(locators=[]),        # no locators → not counted (different debt)
        ]),
    ]
    assert count_earned_exact_units_with_broad_image_locator(items) == 2


def test_count_custom_area_threshold() -> None:
    """Custom area_threshold is respected."""
    # area ≈ 0.084 > 0.05 but < 0.10
    loc = _locator(box_norm=[0.1, 0.1, 0.38, 0.4])
    items = [_item(units=[_unit(locators=[loc])])]
    assert count_earned_exact_units_with_broad_image_locator(items, area_threshold=0.10) == 0
    assert count_earned_exact_units_with_broad_image_locator(items, area_threshold=0.05) == 1


def test_count_empty_items_list() -> None:
    assert count_earned_exact_units_with_broad_image_locator([]) == 0


def test_count_item_with_no_units() -> None:
    assert count_earned_exact_units_with_broad_image_locator([_item(units=[])]) == 0


def test_broad_image_area_threshold_constant_value() -> None:
    """Pin the constant so unintentional changes surface in CI."""
    assert BROAD_IMAGE_AREA_THRESHOLD == 0.05
