"""Projection into the generic Agent Viewer snapshot shape."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from config.paths import dossiers_artifacts_root
from services.agent_viewer.event_bus import event_bus
from services.agent_viewer.identifiers import validate_viewer_identifiers
from services.agent_viewer.models import (
    SNAPSHOT_PROTOCOL,
    ActivityEvent,
    AgentRun,
    AgentViewerSnapshot,
)


def stream_key_for(loop_kind: str, run_id: str) -> str:
    safe_loop_kind, safe_run_id = validate_viewer_identifiers(loop_kind=loop_kind, run_id=run_id)
    return f"{safe_loop_kind}:{safe_run_id}"


def build_snapshot(*, loop_kind: str, run_id: str) -> AgentViewerSnapshot:
    safe_loop_kind, safe_run_id = validate_viewer_identifiers(loop_kind=loop_kind, run_id=run_id)
    persisted = _load_persisted_snapshot(loop_kind=safe_loop_kind, run_id=safe_run_id)
    if persisted is not None:
        snapshot = persisted
    else:
        snapshot = AgentViewerSnapshot(
            run=AgentRun(
                loop_kind=safe_loop_kind,
                run_id=safe_run_id,
                status="unavailable",
                reason="viewer_snapshot_not_found",
            )
        )

    history_activity = _activity_from_event_history(stream_key_for(safe_loop_kind, safe_run_id))
    if history_activity:
        seen = {item.id for item in snapshot.activity}
        merged = list(snapshot.activity)
        merged.extend(item for item in history_activity if item.id not in seen)
        snapshot.activity = sorted(
            merged,
            key=lambda item: (
                item.timestamp_epoch_seconds is None,
                item.timestamp_epoch_seconds or 0,
                item.id,
            ),
        )
        if snapshot.run.status == "unavailable":
            snapshot.run.status = "observed"
            snapshot.run.reason = "event_history_only"

    return snapshot


def _load_persisted_snapshot(*, loop_kind: str, run_id: str) -> AgentViewerSnapshot | None:
    path = _snapshot_path(loop_kind=loop_kind, run_id=run_id)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _partial_snapshot(loop_kind=loop_kind, run_id=run_id, reason="viewer_snapshot_unreadable")
    if not isinstance(raw, Mapping):
        return _partial_snapshot(loop_kind=loop_kind, run_id=run_id, reason="viewer_snapshot_invalid")
    payload = dict(raw)
    payload.setdefault("protocol", SNAPSHOT_PROTOCOL)
    try:
        return AgentViewerSnapshot.model_validate(payload)
    except Exception:
        return _partial_snapshot(loop_kind=loop_kind, run_id=run_id, reason="viewer_snapshot_invalid")


def _snapshot_path(*, loop_kind: str, run_id: str) -> Path:
    safe_loop_kind, safe_run_id = validate_viewer_identifiers(loop_kind=loop_kind, run_id=run_id)
    return dossiers_artifacts_root() / "agent_viewer" / "snapshots" / safe_loop_kind / f"{safe_run_id}.json"


def _partial_snapshot(*, loop_kind: str, run_id: str, reason: str) -> AgentViewerSnapshot:
    return AgentViewerSnapshot(
        run=AgentRun(
            loop_kind=loop_kind,
            run_id=run_id,
            status="partial",
            reason=reason,
        )
    )


def _activity_from_event_history(stream_key: str) -> list[ActivityEvent]:
    out: list[ActivityEvent] = []
    for idx, raw in enumerate(event_bus.history(stream_key), start=1):
        try:
            event = json.loads(raw)
        except Exception:
            continue
        if isinstance(event, Mapping):
            item = _activity_from_event(event, idx)
            if item is not None:
                out.append(item)
    return out


def _activity_from_event(event: Mapping[str, Any], idx: int) -> ActivityEvent | None:
    status = _coerce_mapping(event.get("status"))
    title = (
        event.get("title")
        or event.get("message")
        or status.get("line1")
        or event.get("event")
        or event.get("type")
        or event.get("event_type")
    )
    if not title:
        return None
    payload = {str(k): v for k, v in event.items() if k not in _ACTIVITY_TOP_LEVEL_KEYS}
    return ActivityEvent(
        id=str(
            event.get("id")
            or event.get("event_id")
            or event.get("seq")
            or event.get("lane_seq")
            or f"event_{idx}"
        ),
        title=str(title),
        timestamp_epoch_seconds=_coerce_int(event.get("timestamp_epoch_seconds") or event.get("ts")),
        chapter_id=_coerce_optional_str(event.get("chapter_id") or event.get("lane")),
        detail=_coerce_optional_str(event.get("detail") or event.get("summary") or status.get("line2")),
        status=str(status.get("stage") or event.get("status_text") or event.get("event_type") or "info"),
        event_type=_coerce_optional_str(event.get("event") or event.get("type") or event.get("event_type")),
        payload=payload,
    )


_ACTIVITY_TOP_LEVEL_KEYS = {
    "id",
    "event_id",
    "title",
    "message",
    "event",
    "type",
    "event_type",
    "timestamp_epoch_seconds",
    "ts",
    "chapter_id",
    "lane",
    "detail",
    "summary",
    "status",
    "status_text",
}


def _coerce_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}
