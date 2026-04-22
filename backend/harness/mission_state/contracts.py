from __future__ import annotations

from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError

MISSION_STATE_VERSION = "mission_state.v1"
RESOLUTION_STATE_VERSION = "resolution_state.v1"
CLOSURE_STATE_VERSION = "closure_state.v1"
WorkUniversePosture = Literal["initial", "partial", "believed_adequate", "audited"]
ResolutionItemStructureKind = Literal["atomic", "group"]


class ResolutionItemHistoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_kind: str = Field(min_length=1, max_length=64)
    summary: str | None = Field(default=None, max_length=400)
    outcome: str | None = Field(default=None, max_length=128)
    timestamp_epoch_seconds: float | None = None
    opaque_payload: dict[str, Any] = Field(default_factory=dict)


class ResolutionRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_item_id: str = Field(min_length=1, max_length=128)
    target_item_id: str = Field(min_length=1, max_length=128)
    relation_type: str = Field(min_length=1, max_length=64)
    summary: str | None = Field(default=None, max_length=400)
    opaque_payload: dict[str, Any] = Field(default_factory=dict)


class ResolutionCoveredUnit(BaseModel):
    """A generic, one-level sub-unit tracked inside a ``ResolutionItem``.

    ``covered_units`` make the smallest independently-reviewable sub-units of a
    group item explicit (for example, each enumerated sub-claim of a ``group``
    resolution item). They are not recursive; they carry no domain semantics.
    """

    model_config = ConfigDict(extra="forbid")

    unit_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=240)
    kind: str | None = Field(default=None, max_length=128)
    status: str | None = Field(default=None, max_length=64)
    summary: str | None = Field(default=None, max_length=500)
    determination: str | None = Field(default=None, max_length=32)
    verification_basis: str | None = Field(default=None, max_length=500)
    next_needed_step: str | None = Field(default=None, max_length=400)
    evidence_refs: list[str] = Field(default_factory=list, max_length=24)
    materiality: str | None = Field(default=None, max_length=32)
    label: str | None = Field(default=None, max_length=128)
    value_kind: str | None = Field(default=None, max_length=64)
    candidate_values: list[str] = Field(default_factory=list, max_length=16)
    determined_value: str | None = Field(default=None, max_length=400)
    opaque_payload: dict[str, Any] = Field(default_factory=dict)


class ResolutionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=240)
    kind: str = Field(min_length=1, max_length=128)
    status: str = Field(min_length=1, max_length=64)
    determination: str | None = Field(default=None, max_length=32)
    summary: str | None = Field(default=None, max_length=500)
    verification_basis: str | None = Field(default=None, max_length=500)
    next_needed_step: str | None = Field(default=None, max_length=400)
    completion_criteria: str | None = Field(default=None, max_length=400)
    structure_kind: ResolutionItemStructureKind | None = None
    sequence_scope: str | None = Field(default=None, max_length=128)
    sequence_index: int | None = Field(default=None, ge=1)
    blocking: bool | None = None
    requires_hitl: bool = False
    no_further_progress: bool = False
    dependencies: list[str] = Field(default_factory=list, max_length=16)
    evidence_refs: list[str] = Field(default_factory=list, max_length=24)
    notes: str | None = Field(default=None, max_length=500)
    context_notes: list[dict[str, Any]] = Field(default_factory=list, max_length=3)
    history: list[ResolutionItemHistoryEntry] = Field(default_factory=list, max_length=8)
    materiality: str | None = Field(default=None, max_length=32)
    scope: dict[str, Any] = Field(default_factory=dict)
    provenance: str | None = Field(default=None, max_length=128)
    covered_units: list[ResolutionCoveredUnit] = Field(default_factory=list, max_length=32)
    opaque_payload: dict[str, Any] = Field(default_factory=dict)


class ResolutionState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default=RESOLUTION_STATE_VERSION, min_length=1, max_length=64)
    updated_at_epoch_seconds: float = Field(default=0.0, ge=0.0)
    active_item_id: str | None = Field(default=None, max_length=128)
    items: list[ResolutionItem] = Field(default_factory=list)
    relations: list[ResolutionRelation] = Field(default_factory=list)
    opaque_payload: dict[str, Any] = Field(default_factory=dict)


class ClosureDimension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=240)
    status: str = Field(min_length=1, max_length=64)
    determination: str | None = Field(default=None, max_length=32)
    summary: str | None = Field(default=None, max_length=500)
    blocking: bool | None = None
    requires_hitl: bool = False
    no_further_progress: bool = False
    evidence_refs: list[str] = Field(default_factory=list, max_length=24)
    verification_basis: str | None = Field(default=None, max_length=500)
    next_needed_step: str | None = Field(default=None, max_length=400)
    opaque_payload: dict[str, Any] = Field(default_factory=dict)


class ClosureState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default=CLOSURE_STATE_VERSION, min_length=1, max_length=64)
    updated_at_epoch_seconds: float = Field(default=0.0, ge=0.0)
    overall_status: str | None = Field(default=None, max_length=64)
    summary: str | None = Field(default=None, max_length=500)
    ready_to_publish: bool = False
    ready_to_close: bool = False
    requires_hitl: bool = False
    no_further_progress: bool = False
    dimensions: list[ClosureDimension] = Field(default_factory=list)
    opaque_payload: dict[str, Any] = Field(default_factory=dict)


class MissionSuccessCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    condition_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=240)
    status: str = Field(min_length=1, max_length=64)
    determination: str | None = Field(default=None, max_length=32)
    summary: str | None = Field(default=None, max_length=500)
    completion_criteria: str | None = Field(default=None, max_length=400)
    verification_basis: str | None = Field(default=None, max_length=500)
    next_needed_step: str | None = Field(default=None, max_length=400)
    dependencies: list[str] = Field(default_factory=list, max_length=16)
    evidence_refs: list[str] = Field(default_factory=list, max_length=24)
    opaque_payload: dict[str, Any] = Field(default_factory=dict)


class MissionState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default=MISSION_STATE_VERSION, min_length=1, max_length=64)
    mission_id: str = Field(min_length=1, max_length=128)
    session_id: str | None = Field(default=None, max_length=256)
    request_id: str | None = Field(default=None, max_length=256)
    loop_family: str = Field(min_length=1, max_length=64)
    objective: str | None = Field(default=None, max_length=240)
    active_mode: str | None = Field(default=None, max_length=64)
    work_universe_posture: WorkUniversePosture = "initial"
    updated_at_epoch_seconds: float = Field(default=0.0, ge=0.0)
    latest_refs_summary: dict[str, Any] = Field(default_factory=dict)
    high_signal_artifact_refs: list[str] = Field(default_factory=list, max_length=16)
    blocker_summary: dict[str, Any] = Field(default_factory=dict)
    verification_summary: dict[str, Any] = Field(default_factory=dict)
    waiting_summary: dict[str, Any] = Field(default_factory=dict)
    terminal_summary: dict[str, Any] = Field(default_factory=dict)
    continuity_summary: dict[str, Any] = Field(default_factory=dict)
    mission_mode_summary: dict[str, Any] = Field(default_factory=dict)
    success_conditions: list[MissionSuccessCondition] = Field(default_factory=list)
    prompt_observability_summary: dict[str, Any] = Field(default_factory=dict)
    closure_state: ClosureState = Field(default_factory=ClosureState)
    resolution_state: ResolutionState = Field(default_factory=ResolutionState)
    opaque_payload: dict[str, Any] = Field(default_factory=dict)


def new_resolution_state(
    *,
    active_item_id: str | None = None,
    items: list[ResolutionItem | dict[str, Any]] | None = None,
    relations: list[ResolutionRelation | dict[str, Any]] | None = None,
    updated_at_epoch_seconds: float = 0.0,
    opaque_payload: Mapping[str, Any] | None = None,
) -> ResolutionState:
    items_out: list[ResolutionItem] = []
    for row in items or []:
        item = _coerce_resolution_item(row)
        if item is not None:
            items_out.append(item)
    relations_out: list[ResolutionRelation] = []
    for row in relations or []:
        relation = _coerce_resolution_relation(row)
        if relation is not None:
            relations_out.append(relation)
    return ResolutionState(
        active_item_id=_clean_text(active_item_id, limit=128),
        items=items_out,
        relations=relations_out,
        updated_at_epoch_seconds=float(updated_at_epoch_seconds or 0.0),
        opaque_payload=dict(opaque_payload) if isinstance(opaque_payload, Mapping) else {},
    )


def new_closure_state(
    *,
    overall_status: str | None = None,
    summary: str | None = None,
    ready_to_publish: bool = False,
    ready_to_close: bool = False,
    requires_hitl: bool = False,
    no_further_progress: bool = False,
    dimensions: list[ClosureDimension | dict[str, Any]] | None = None,
    updated_at_epoch_seconds: float = 0.0,
    opaque_payload: Mapping[str, Any] | None = None,
) -> ClosureState:
    dims_out: list[ClosureDimension] = []
    for row in dimensions or []:
        dim = _coerce_closure_dimension(row)
        if dim is not None:
            dims_out.append(dim)
    return ClosureState(
        overall_status=_clean_text(overall_status, limit=64),
        summary=_clean_text(summary, limit=500),
        ready_to_publish=bool(ready_to_publish),
        ready_to_close=bool(ready_to_close),
        requires_hitl=bool(requires_hitl),
        no_further_progress=bool(no_further_progress),
        dimensions=dims_out,
        updated_at_epoch_seconds=float(updated_at_epoch_seconds or 0.0),
        opaque_payload=dict(opaque_payload) if isinstance(opaque_payload, Mapping) else {},
    )


def new_mission_state(
    *,
    mission_id: str,
    loop_family: str,
    session_id: str | None = None,
    request_id: str | None = None,
    objective: str | None = None,
    active_mode: str | None = None,
    work_universe_posture: WorkUniversePosture = "initial",
    updated_at_epoch_seconds: float = 0.0,
    latest_refs_summary: Mapping[str, Any] | None = None,
    high_signal_artifact_refs: list[str] | None = None,
    blocker_summary: Mapping[str, Any] | None = None,
    verification_summary: Mapping[str, Any] | None = None,
    waiting_summary: Mapping[str, Any] | None = None,
    terminal_summary: Mapping[str, Any] | None = None,
    continuity_summary: Mapping[str, Any] | None = None,
    mission_mode_summary: Mapping[str, Any] | None = None,
    success_conditions: list[MissionSuccessCondition | dict[str, Any]] | None = None,
    prompt_observability_summary: Mapping[str, Any] | None = None,
    closure_state: ClosureState | dict[str, Any] | None = None,
    resolution_state: ResolutionState | dict[str, Any] | None = None,
    opaque_payload: Mapping[str, Any] | None = None,
) -> MissionState:
    success_conditions_out: list[MissionSuccessCondition] = []
    for row in success_conditions or []:
        condition = _coerce_mission_success_condition(row)
        if condition is not None:
            success_conditions_out.append(condition)
    return MissionState(
        mission_id=_clean_text(mission_id, limit=128) or "unknown_mission",
        session_id=_clean_text(session_id, limit=256),
        request_id=_clean_text(request_id, limit=256),
        loop_family=_clean_text(loop_family, limit=64) or "unknown",
        objective=_clean_text(objective, limit=240),
        active_mode=_clean_text(active_mode, limit=64),
        work_universe_posture=work_universe_posture,
        updated_at_epoch_seconds=float(updated_at_epoch_seconds or 0.0),
        latest_refs_summary=dict(latest_refs_summary) if isinstance(latest_refs_summary, Mapping) else {},
        high_signal_artifact_refs=_clean_str_list(high_signal_artifact_refs, limit=16),
        blocker_summary=dict(blocker_summary) if isinstance(blocker_summary, Mapping) else {},
        verification_summary=dict(verification_summary) if isinstance(verification_summary, Mapping) else {},
        waiting_summary=dict(waiting_summary) if isinstance(waiting_summary, Mapping) else {},
        terminal_summary=dict(terminal_summary) if isinstance(terminal_summary, Mapping) else {},
        continuity_summary=dict(continuity_summary) if isinstance(continuity_summary, Mapping) else {},
        mission_mode_summary=dict(mission_mode_summary) if isinstance(mission_mode_summary, Mapping) else {},
        success_conditions=success_conditions_out,
        prompt_observability_summary=(
            dict(prompt_observability_summary) if isinstance(prompt_observability_summary, Mapping) else {}
        ),
        closure_state=(
            closure_state if isinstance(closure_state, ClosureState) else ClosureState(**closure_state)
            if isinstance(closure_state, dict)
            else ClosureState()
        ),
        resolution_state=(
            resolution_state if isinstance(resolution_state, ResolutionState) else ResolutionState(**resolution_state)
            if isinstance(resolution_state, dict)
            else ResolutionState()
        ),
        opaque_payload=dict(opaque_payload) if isinstance(opaque_payload, Mapping) else {},
    )


def _coerce_resolution_item(row: ResolutionItem | dict[str, Any]) -> ResolutionItem | None:
    if isinstance(row, ResolutionItem):
        return row
    if not isinstance(row, dict):
        return None
    try:
        return ResolutionItem.model_validate(row)
    except ValidationError:
        return None


def _coerce_resolution_relation(
    row: ResolutionRelation | dict[str, Any],
) -> ResolutionRelation | None:
    if isinstance(row, ResolutionRelation):
        return row
    if not isinstance(row, dict):
        return None
    try:
        return ResolutionRelation.model_validate(row)
    except ValidationError:
        return None


def _coerce_closure_dimension(
    row: ClosureDimension | dict[str, Any],
) -> ClosureDimension | None:
    if isinstance(row, ClosureDimension):
        return row
    if not isinstance(row, dict):
        return None
    try:
        return ClosureDimension.model_validate(row)
    except ValidationError:
        return None


def _coerce_mission_success_condition(
    row: MissionSuccessCondition | dict[str, Any],
) -> MissionSuccessCondition | None:
    if isinstance(row, MissionSuccessCondition):
        return row
    if not isinstance(row, dict):
        return None
    try:
        return MissionSuccessCondition.model_validate(row)
    except ValidationError:
        return None


def _clean_text(value: Any, *, limit: int) -> str | None:
    if not isinstance(value, str):
        if value is None:
            return None
        value = str(value)
    text = value.strip()
    return text[:limit] if text else None


def _clean_str_list(values: Any, *, limit: int) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for value in values:
        text = _clean_text(value, limit=240)
        if not text or text in out:
            continue
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None
