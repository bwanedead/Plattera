"""Tests for mechanical operand value parsing."""

from __future__ import annotations

import pytest

from tooling.mapping.deed_to_ir.operand_value_parsing import (
    build_course_compile_fields,
    parse_bearing_operand,
    parse_distance_operand,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("N. 68° 30' E.", 68.5),
        ("S. 87° 35' W.", 267.583333),
        ("S. 4° 00' E.", 176.0),
        ("N 45.5 E", 45.5),
        ("S 87.5 W", 267.5),
    ],
)
def test_parse_bearing_operand_examples(raw: str, expected: float) -> None:
    parsed = parse_bearing_operand(raw)
    assert parsed["parse_status"] == "parsed"
    assert parsed["bearing_raw"] == raw
    assert parsed["bearing_degrees"] == pytest.approx(expected, rel=1e-5)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("542 feet", 542.0),
        ("518 feet", 518.0),
    ],
)
def test_parse_distance_operand_examples(raw: str, expected: float) -> None:
    parsed = parse_distance_operand(raw)
    assert parsed["parse_status"] == "parsed"
    assert parsed["distance_raw"] == raw
    assert parsed["distance_feet"] == pytest.approx(expected)


def test_build_course_compile_fields_ready() -> None:
    row = build_course_compile_fields(
        bearing_raw="N. 68° 30' E.",
        distance_raw="542 feet",
    )
    assert row["course_compile_ready"] is True
    assert row["bearing"] == pytest.approx(68.5)
    assert row["distance"] == pytest.approx(542.0)


def test_build_course_compile_fields_failed_bearing() -> None:
    row = build_course_compile_fields(
        bearing_raw="North by Northeast",
        distance_raw="542 feet",
    )
    assert row["course_compile_ready"] is False
    assert "bearing_parse_failed" in row["parse_warnings"]
