from __future__ import annotations

import pytest

from harness.audit.terminal_projection import (
    PROJECTION_KIND_NATIVE,
    PROJECTION_KIND_OVERRIDE,
    build_terminal_projection,
    effective_iterations,
    is_override_projection,
    render_run_level_override_section,
)


def test_native_projection_shape() -> None:
    projection = build_terminal_projection(
        projection_kind="native",
        terminal_class="failed",
        reason_code="model_call_failed",
        iterations=1,
        latest_refs={"doc": "ref://doc"},
    )
    assert projection == {
        "projection_kind": PROJECTION_KIND_NATIVE,
        "terminal_class": "failed",
        "reason_code": "model_call_failed",
        "iterations": 1,
        "latest_refs": {"doc": "ref://doc"},
        "terminal_decision": None,
    }
    assert not is_override_projection(projection)
    assert render_run_level_override_section(projection) == []


def test_override_projection_shape_and_section() -> None:
    projection = build_terminal_projection(
        projection_kind="override",
        terminal_class="paused",
        reason_code="paused_by_operator",
        iterations=1,
        latest_refs={},
        terminal_decision="paused",
    )
    assert projection["projection_kind"] == PROJECTION_KIND_OVERRIDE
    assert is_override_projection(projection)
    section = "\n".join(render_run_level_override_section(projection))
    assert "## Run-Level Terminal Override" in section
    assert "- terminal_class: paused" in section
    assert "- reason_code: paused_by_operator" in section
    assert "- terminal_decision: paused" in section


@pytest.mark.parametrize("kind", ["something_else", "overide", "NATIVE", "", " native-override "])
def test_unknown_projection_kind_is_rejected(kind: str) -> None:
    with pytest.raises(ValueError, match="projection_kind must be exactly"):
        build_terminal_projection(
            projection_kind=kind,
            terminal_class="completed",
            reason_code="complete_run",
            iterations=2,
        )


def test_effective_iterations_uses_highest_retained_turn() -> None:
    turns = [{"turn_index": 1}, {"turn_index": 3}]
    assert effective_iterations(0, turns) == 3
    assert effective_iterations(2, turns) == 3
    assert effective_iterations(5, turns) == 5
    assert effective_iterations(0, []) == 0
    assert effective_iterations(1, None) == 1
