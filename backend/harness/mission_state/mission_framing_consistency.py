"""Pure mission-framing completeness predicate.

Mechanical only: does not author objective, success conditions, inventory,
or a semantic plan. Inspects already-merged typed mission state.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from .contracts import MissionState, MissionSuccessCondition

REASON_MISSION_FRAMING_REQUIRED = "mission_framing_required"
MISSING_FIELD_OBJECTIVE = "objective"
MISSING_FIELD_SUCCESS_CONDITIONS = "success_conditions"
MISSING_FIELD_ORDER = (MISSING_FIELD_OBJECTIVE, MISSING_FIELD_SUCCESS_CONDITIONS)
GATED_WORK_UNIVERSE_POSTURES = frozenset({"believed_adequate", "audited"})
GATED_MOTION_POSTURES = frozenset({"resolution"})
HONEST_INVENTORY_WORK_UNIVERSE_POSTURES = frozenset({"initial", "partial"})
INVENTORY_MOTION_POSTURE = "inventory"


@dataclass(frozen=True)
class MissionFramingConsistencyResult:
    reason_code: str
    missing_fields: tuple[str, ...]
    effective_work_universe_posture: str
    effective_motion_posture: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "reason_code": self.reason_code,
            "missing_fields": list(self.missing_fields),
            "effective_work_universe_posture": self.effective_work_universe_posture,
            "effective_motion_posture": self.effective_motion_posture,
        }

    def framing_identity(self) -> str:
        return "|".join(
            (
                ",".join(self.missing_fields),
                self.effective_work_universe_posture,
                self.effective_motion_posture,
            )
        )


def objective_is_present(objective: Any) -> bool:
    """True only for an actual nonblank string. No ``str(...)`` coercion."""
    return type(objective) is str and bool(objective.strip())


def success_conditions_are_present(rows: Sequence[Any] | None) -> bool:
    """True when at least one already-valid typed success-condition row exists."""
    if not rows:
        return False
    return any(isinstance(row, MissionSuccessCondition) for row in rows)


def missing_framing_fields(mission_state: MissionState) -> tuple[str, ...]:
    missing: list[str] = []
    if not objective_is_present(mission_state.objective):
        missing.append(MISSING_FIELD_OBJECTIVE)
    if not success_conditions_are_present(mission_state.success_conditions):
        missing.append(MISSING_FIELD_SUCCESS_CONDITIONS)
    return tuple(field for field in MISSING_FIELD_ORDER if field in missing)


def mission_framing_is_present(mission_state: MissionState) -> bool:
    return not missing_framing_fields(mission_state)


def posture_requires_framing(
    *,
    work_universe_posture: str,
    motion_posture: str,
) -> bool:
    return (
        work_universe_posture in GATED_WORK_UNIVERSE_POSTURES
        or motion_posture in GATED_MOTION_POSTURES
    )


def is_honest_inventory_downgrade(mission_state: MissionState) -> bool:
    return (
        mission_state.work_universe_posture in HONEST_INVENTORY_WORK_UNIVERSE_POSTURES
        and mission_state.motion_posture == INVENTORY_MOTION_POSTURE
    )


def newly_enters_framing_gated_posture(
    *,
    persisted: MissionState,
    effective: MissionState,
) -> bool:
    entered_work_universe = (
        persisted.work_universe_posture not in GATED_WORK_UNIVERSE_POSTURES
        and effective.work_universe_posture in GATED_WORK_UNIVERSE_POSTURES
    )
    entered_motion = (
        persisted.motion_posture not in GATED_MOTION_POSTURES
        and effective.motion_posture in GATED_MOTION_POSTURES
    )
    return entered_work_universe or entered_motion


def evaluate_mission_framing_consistency(
    *,
    persisted: MissionState,
    effective: MissionState,
    attempts_tool_dispatch_publish_or_completion: bool,
) -> MissionFramingConsistencyResult | None:
    """Return a bounded result when effective framing is incomplete and the plan is gated.

    Same-plan honest framing or an honest return to inventory is not a contradiction.
    The predicate does not prefer either repair path.
    """
    if mission_framing_is_present(effective):
        return None
    if is_honest_inventory_downgrade(effective):
        return None

    persisted_gated = posture_requires_framing(
        work_universe_posture=persisted.work_universe_posture,
        motion_posture=persisted.motion_posture,
    )
    newly_gated = newly_enters_framing_gated_posture(
        persisted=persisted,
        effective=effective,
    )
    if not newly_gated and not (
        persisted_gated and attempts_tool_dispatch_publish_or_completion
    ):
        return None

    return MissionFramingConsistencyResult(
        reason_code=REASON_MISSION_FRAMING_REQUIRED,
        missing_fields=missing_framing_fields(effective),
        effective_work_universe_posture=effective.work_universe_posture,
        effective_motion_posture=effective.motion_posture,
    )
