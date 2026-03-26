from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

MISSION_STATE_VERSION = "mission_state.v1"
RESOLUTION_STATE_VERSION = "resolution_state.v1"


class ResolutionItemHistoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_kind: str = Field(min_length=1, max_length=64)
    summary: str | None = Field(default=None, max_length=400)
    outcome: str | None = Field(default=None, max_length=128)
    timestamp_epoch_seconds: float | None = None
    domain_payload: dict[str, Any] = Field(default_factory=dict)


class ResolutionRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_item_id: str = Field(min_length=1, max_length=128)
    target_item_id: str = Field(min_length=1, max_length=128)
    relation_type: str = Field(min_length=1, max_length=64)
    summary: str | None = Field(default=None, max_length=240)
    domain_payload: dict[str, Any] = Field(default_factory=dict)


class ResolutionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=240)
    kind: str = Field(min_length=1, max_length=128)
    status: str = Field(min_length=1, max_length=64)
    summary: str | None = Field(default=None, max_length=500)
    dependencies: list[str] = Field(default_factory=list, max_length=16)
    evidence_refs: list[str] = Field(default_factory=list, max_length=24)
    notes: str | None = Field(default=None, max_length=500)
    context_notes: list[dict[str, Any]] = Field(default_factory=list, max_length=3)
    history: list[ResolutionItemHistoryEntry] = Field(default_factory=list, max_length=8)
    materiality: str | None = Field(default=None, max_length=32)
    scope: dict[str, Any] = Field(default_factory=dict)
    provenance: str | None = Field(default=None, max_length=128)
    domain_payload: dict[str, Any] = Field(default_factory=dict)


class ResolutionState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default=RESOLUTION_STATE_VERSION, min_length=1, max_length=64)
    updated_at_epoch_seconds: float = Field(default=0.0, ge=0.0)
    active_item_id: str | None = Field(default=None, max_length=128)
    items: list[ResolutionItem] = Field(default_factory=list)
    relations: list[ResolutionRelation] = Field(default_factory=list)
    domain_payload: dict[str, Any] = Field(default_factory=dict)


class MissionState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default=MISSION_STATE_VERSION, min_length=1, max_length=64)
    mission_id: str = Field(min_length=1, max_length=128)
    session_id: str | None = Field(default=None, max_length=256)
    request_id: str | None = Field(default=None, max_length=256)
    loop_family: str = Field(min_length=1, max_length=64)
    objective: str | None = Field(default=None, max_length=240)
    active_mode: str | None = Field(default=None, max_length=64)
    updated_at_epoch_seconds: float = Field(default=0.0, ge=0.0)
    latest_refs_summary: dict[str, Any] = Field(default_factory=dict)
    high_signal_artifact_refs: list[str] = Field(default_factory=list, max_length=16)
    family_coordination: dict[str, Any] = Field(default_factory=dict)
    blocker_summary: dict[str, Any] = Field(default_factory=dict)
    verification_summary: dict[str, Any] = Field(default_factory=dict)
    waiting_summary: dict[str, Any] = Field(default_factory=dict)
    terminal_summary: dict[str, Any] = Field(default_factory=dict)
    continuity_summary: dict[str, Any] = Field(default_factory=dict)
    mission_mode_summary: dict[str, Any] = Field(default_factory=dict)
    prompt_observability_summary: dict[str, Any] = Field(default_factory=dict)
    resolution_state: ResolutionState = Field(default_factory=ResolutionState)
    domain_payload: dict[str, Any] = Field(default_factory=dict)


def new_resolution_state(
    *,
    active_item_id: str | None = None,
    items: list[ResolutionItem | dict[str, Any]] | None = None,
    relations: list[ResolutionRelation | dict[str, Any]] | None = None,
    updated_at_epoch_seconds: float = 0.0,
    domain_payload: Mapping[str, Any] | None = None,
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
        domain_payload=dict(domain_payload) if isinstance(domain_payload, Mapping) else {},
    )


def new_mission_state(
    *,
    mission_id: str,
    loop_family: str,
    session_id: str | None = None,
    request_id: str | None = None,
    objective: str | None = None,
    active_mode: str | None = None,
    updated_at_epoch_seconds: float = 0.0,
    latest_refs_summary: Mapping[str, Any] | None = None,
    high_signal_artifact_refs: list[str] | None = None,
    family_coordination: Mapping[str, Any] | None = None,
    blocker_summary: Mapping[str, Any] | None = None,
    verification_summary: Mapping[str, Any] | None = None,
    waiting_summary: Mapping[str, Any] | None = None,
    terminal_summary: Mapping[str, Any] | None = None,
    continuity_summary: Mapping[str, Any] | None = None,
    mission_mode_summary: Mapping[str, Any] | None = None,
    prompt_observability_summary: Mapping[str, Any] | None = None,
    resolution_state: ResolutionState | dict[str, Any] | None = None,
    domain_payload: Mapping[str, Any] | None = None,
) -> MissionState:
    return MissionState(
        mission_id=_clean_text(mission_id, limit=128) or "unknown_mission",
        session_id=_clean_text(session_id, limit=256),
        request_id=_clean_text(request_id, limit=256),
        loop_family=_clean_text(loop_family, limit=64) or "unknown",
        objective=_clean_text(objective, limit=240),
        active_mode=_clean_text(active_mode, limit=64),
        updated_at_epoch_seconds=float(updated_at_epoch_seconds or 0.0),
        latest_refs_summary=dict(latest_refs_summary) if isinstance(latest_refs_summary, Mapping) else {},
        high_signal_artifact_refs=_clean_str_list(high_signal_artifact_refs, limit=16),
        family_coordination=dict(family_coordination) if isinstance(family_coordination, Mapping) else {},
        blocker_summary=dict(blocker_summary) if isinstance(blocker_summary, Mapping) else {},
        verification_summary=dict(verification_summary) if isinstance(verification_summary, Mapping) else {},
        waiting_summary=dict(waiting_summary) if isinstance(waiting_summary, Mapping) else {},
        terminal_summary=dict(terminal_summary) if isinstance(terminal_summary, Mapping) else {},
        continuity_summary=dict(continuity_summary) if isinstance(continuity_summary, Mapping) else {},
        mission_mode_summary=dict(mission_mode_summary) if isinstance(mission_mode_summary, Mapping) else {},
        prompt_observability_summary=(
            dict(prompt_observability_summary) if isinstance(prompt_observability_summary, Mapping) else {}
        ),
        resolution_state=(
            resolution_state if isinstance(resolution_state, ResolutionState) else ResolutionState(**resolution_state)
            if isinstance(resolution_state, dict)
            else ResolutionState()
        ),
        domain_payload=dict(domain_payload) if isinstance(domain_payload, Mapping) else {},
    )


def resolution_state_from_legacy_items(
    *,
    items: list[Mapping[str, Any]] | None,
    active_item_id: str | None = None,
    relations: list[ResolutionRelation | dict[str, Any]] | None = None,
    updated_at_epoch_seconds: float = 0.0,
    domain_payload: Mapping[str, Any] | None = None,
) -> ResolutionState:
    items_out: list[ResolutionItem] = []
    for row in items or []:
        item = resolution_item_from_legacy_row(row)
        if item is not None:
            items_out.append(item)
    return new_resolution_state(
        active_item_id=active_item_id,
        items=items_out,
        relations=relations,
        updated_at_epoch_seconds=updated_at_epoch_seconds,
        domain_payload=domain_payload,
    )


def resolution_item_from_legacy_row(row: Mapping[str, Any] | ResolutionItem | dict[str, Any]) -> ResolutionItem | None:
    if isinstance(row, ResolutionItem):
        return row
    if not isinstance(row, Mapping):
        return None
    item_id = _clean_text(row.get("item_id"), limit=128)
    title = _clean_text(row.get("title"), limit=240)
    kind = _clean_text(row.get("kind"), limit=128)
    status = _clean_text(row.get("status"), limit=64) or _clean_text(row.get("state"), limit=64)
    if not item_id or not title or not kind or not status:
        return None
    return ResolutionItem(
        item_id=item_id,
        title=title,
        kind=kind,
        status=status,
        summary=_clean_text(row.get("summary"), limit=500),
        dependencies=_clean_str_list(row.get("dependencies"), limit=16),
        evidence_refs=_clean_str_list(row.get("evidence_refs"), limit=24),
        notes=_clean_text(row.get("notes"), limit=500),
        context_notes=_clean_dict_list(row.get("context_notes"), limit=3),
        history=[
            entry
            for entry in (_coerce_resolution_history_entry(item) for item in _maybe_iterable(row.get("history")))
            if entry is not None
        ],
        materiality=_clean_text(row.get("materiality"), limit=32),
        scope=dict(row.get("scope")) if isinstance(row.get("scope"), Mapping) else {},
        provenance=_clean_text(row.get("provenance"), limit=128),
        domain_payload=dict(row.get("domain_payload")) if isinstance(row.get("domain_payload"), Mapping) else {},
    )


def resolution_relation_from_legacy_row(
    row: Mapping[str, Any] | ResolutionRelation | dict[str, Any],
) -> ResolutionRelation | None:
    if isinstance(row, ResolutionRelation):
        return row
    if not isinstance(row, Mapping):
        return None
    source_item_id = _clean_text(row.get("source_item_id"), limit=128)
    target_item_id = _clean_text(row.get("target_item_id"), limit=128)
    relation_type = _clean_text(row.get("relation_type"), limit=64)
    if not source_item_id or not target_item_id or not relation_type:
        return None
    return ResolutionRelation(
        source_item_id=source_item_id,
        target_item_id=target_item_id,
        relation_type=relation_type,
        summary=_clean_text(row.get("summary"), limit=240),
        domain_payload=dict(row.get("domain_payload")) if isinstance(row.get("domain_payload"), Mapping) else {},
    )


def _coerce_resolution_item(row: ResolutionItem | dict[str, Any]) -> ResolutionItem | None:
    return resolution_item_from_legacy_row(row)


def _coerce_resolution_relation(
    row: ResolutionRelation | dict[str, Any],
) -> ResolutionRelation | None:
    return resolution_relation_from_legacy_row(row)


def _coerce_resolution_history_entry(
    row: Mapping[str, Any] | dict[str, Any] | ResolutionItemHistoryEntry,
) -> ResolutionItemHistoryEntry | None:
    if isinstance(row, ResolutionItemHistoryEntry):
        return row
    if not isinstance(row, Mapping):
        return None
    event_kind = _clean_text(row.get("event_kind"), limit=64)
    summary = _clean_text(row.get("summary"), limit=400)
    if not event_kind and not summary:
        return None
    return ResolutionItemHistoryEntry(
        event_kind=event_kind or "update",
        summary=summary,
        outcome=_clean_text(row.get("outcome"), limit=128),
        timestamp_epoch_seconds=_coerce_float(row.get("timestamp_epoch_seconds")),
        domain_payload=dict(row.get("domain_payload")) if isinstance(row.get("domain_payload"), Mapping) else {},
    )


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


def _clean_dict_list(values: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    out: list[dict[str, Any]] = []
    for value in values:
        if not isinstance(value, Mapping):
            continue
        out.append(dict(value))
        if len(out) >= limit:
            break
    return out


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _maybe_iterable(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, Mapping)]
