"""Pure MAPDEP-BR-035 mission-framing predicate tests."""

from __future__ import annotations

from pathlib import Path

from harness.mission_state import (
    MissionSuccessCondition,
    evaluate_mission_framing_consistency,
    mission_framing_is_present,
    missing_framing_fields,
    new_mission_state,
)
from harness.mission_state.mission_framing_consistency import (
    REASON_MISSION_FRAMING_REQUIRED,
)


def _ms(**kwargs):
    kwargs.setdefault("mission_id", "m1")
    kwargs.setdefault("loop_family", "orchestration_kernel")
    return new_mission_state(**kwargs)


def _sc() -> MissionSuccessCondition:
    return MissionSuccessCondition(
        condition_id="sc-1",
        title="Named success condition",
        status="open",
    )


def test_empty_framing_is_incomplete() -> None:
    ms = _ms()
    assert ms.objective is None
    assert ms.success_conditions == []
    assert missing_framing_fields(ms) == ("objective", "success_conditions")
    assert mission_framing_is_present(ms) is False


def test_blank_and_non_string_objective_are_not_present() -> None:
    blank = _ms(objective="   ")
    assert blank.objective is None
    assert "objective" in missing_framing_fields(blank)
    numbered = _ms(objective="real objective", success_conditions=[_sc()])
    numbered.objective = 12  # type: ignore[assignment]
    assert "objective" in missing_framing_fields(numbered)


def test_initial_inventory_without_framing_is_not_gated() -> None:
    persisted = _ms(work_universe_posture="initial", motion_posture="inventory")
    result = evaluate_mission_framing_consistency(
        persisted=persisted,
        effective=persisted,
        attempts_tool_dispatch_publish_or_completion=True,
    )
    assert result is None


def test_partial_inventory_without_framing_is_not_gated() -> None:
    persisted = _ms(work_universe_posture="partial", motion_posture="inventory")
    result = evaluate_mission_framing_consistency(
        persisted=persisted,
        effective=persisted,
        attempts_tool_dispatch_publish_or_completion=True,
    )
    assert result is None


def test_new_believed_adequate_without_framing_is_gated() -> None:
    persisted = _ms(work_universe_posture="initial", motion_posture="inventory")
    effective = _ms(work_universe_posture="believed_adequate", motion_posture="inventory")
    result = evaluate_mission_framing_consistency(
        persisted=persisted,
        effective=effective,
        attempts_tool_dispatch_publish_or_completion=False,
    )
    assert result is not None
    assert result.reason_code == REASON_MISSION_FRAMING_REQUIRED
    assert result.as_dict() == {
        "reason_code": REASON_MISSION_FRAMING_REQUIRED,
        "missing_fields": ["objective", "success_conditions"],
        "effective_work_universe_posture": "believed_adequate",
        "effective_motion_posture": "inventory",
    }


def test_new_resolution_while_partial_without_framing_is_gated() -> None:
    persisted = _ms(work_universe_posture="partial", motion_posture="inventory")
    effective = _ms(work_universe_posture="partial", motion_posture="resolution")
    result = evaluate_mission_framing_consistency(
        persisted=persisted,
        effective=effective,
        attempts_tool_dispatch_publish_or_completion=False,
    )
    assert result is not None
    assert result.missing_fields == ("objective", "success_conditions")
    assert result.effective_motion_posture == "resolution"


def test_objective_without_success_condition_is_gated() -> None:
    persisted = _ms()
    effective = _ms(
        objective="Finish the assigned mission",
        work_universe_posture="believed_adequate",
        motion_posture="resolution",
    )
    result = evaluate_mission_framing_consistency(
        persisted=persisted,
        effective=effective,
        attempts_tool_dispatch_publish_or_completion=True,
    )
    assert result is not None
    assert result.missing_fields == ("success_conditions",)


def test_success_condition_without_objective_is_gated() -> None:
    persisted = _ms()
    effective = _ms(
        success_conditions=[_sc()],
        work_universe_posture="believed_adequate",
        motion_posture="resolution",
    )
    result = evaluate_mission_framing_consistency(
        persisted=persisted,
        effective=effective,
        attempts_tool_dispatch_publish_or_completion=True,
    )
    assert result is not None
    assert result.missing_fields == ("objective",)


def test_same_plan_framing_repair_is_not_gated() -> None:
    persisted = _ms(
        work_universe_posture="believed_adequate",
        motion_posture="resolution",
    )
    effective = _ms(
        objective="Finish the assigned mission",
        success_conditions=[_sc()],
        work_universe_posture="believed_adequate",
        motion_posture="resolution",
    )
    result = evaluate_mission_framing_consistency(
        persisted=persisted,
        effective=effective,
        attempts_tool_dispatch_publish_or_completion=True,
    )
    assert result is None


def test_honest_inventory_downgrade_is_not_gated() -> None:
    persisted = _ms(
        work_universe_posture="believed_adequate",
        motion_posture="resolution",
    )
    effective = _ms(work_universe_posture="partial", motion_posture="inventory")
    result = evaluate_mission_framing_consistency(
        persisted=persisted,
        effective=effective,
        attempts_tool_dispatch_publish_or_completion=True,
    )
    assert result is None


def test_already_invalid_resolution_without_dispatch_is_not_gated() -> None:
    persisted = _ms(
        work_universe_posture="believed_adequate",
        motion_posture="resolution",
    )
    result = evaluate_mission_framing_consistency(
        persisted=persisted,
        effective=persisted,
        attempts_tool_dispatch_publish_or_completion=False,
    )
    assert result is None


def test_already_invalid_resolution_with_dispatch_is_gated() -> None:
    persisted = _ms(
        work_universe_posture="believed_adequate",
        motion_posture="resolution",
    )
    result = evaluate_mission_framing_consistency(
        persisted=persisted,
        effective=persisted,
        attempts_tool_dispatch_publish_or_completion=True,
    )
    assert result is not None
    assert result.reason_code == REASON_MISSION_FRAMING_REQUIRED


def test_identity_changes_when_missing_fields_or_posture_change() -> None:
    first = evaluate_mission_framing_consistency(
        persisted=_ms(),
        effective=_ms(work_universe_posture="believed_adequate", motion_posture="resolution"),
        attempts_tool_dispatch_publish_or_completion=True,
    )
    second = evaluate_mission_framing_consistency(
        persisted=_ms(),
        effective=_ms(
            objective="Finish the assigned mission",
            work_universe_posture="believed_adequate",
            motion_posture="resolution",
        ),
        attempts_tool_dispatch_publish_or_completion=True,
    )
    assert first is not None and second is not None
    assert first.framing_identity() != second.framing_identity()


def test_predicate_module_has_no_domain_imports() -> None:
    source = Path(__file__).with_name("mission_framing_consistency.py").read_text(encoding="utf-8")
    lowered = source.lower()
    for banned in (
        "transcript_edit",
        "deed_to_ir",
        "domains.mapping",
        "range 7",
        "curve station",
    ):
        assert banned not in lowered
