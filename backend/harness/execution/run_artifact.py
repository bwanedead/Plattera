"""Generic run artifact for harness execution."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from time import time
from typing import Any, Mapping

from .action_ids import ActionId, normalize_action_id
from .contracts import ExecutionRefusal
from .latest_refs import merge_latest_refs, normalize_latest_refs


@dataclass(frozen=True)
class ActionHistoryEntry:
    sequence_index: int
    action_id: ActionId
    idempotency_key: str
    executed: bool
    reason_codes: tuple[str, ...] = ()
    artifact_refs: tuple[str, ...] = ()
    timestamp_epoch_seconds: float = 0.0
    refusal: ExecutionRefusal | None = None


@dataclass
class RunArtifact:
    run_id: str
    session_id: str
    created_at_epoch_seconds: float = field(default_factory=time)
    updated_at_epoch_seconds: float = field(default_factory=time)
    status: str = "running"
    reason_code: str | None = None
    latest_refs: dict[str, Any] = field(default_factory=dict)
    action_history: list[ActionHistoryEntry] = field(default_factory=list)

    def append_history_entry(self, entry: ActionHistoryEntry) -> None:
        self.action_history.append(entry)
        self.updated_at_epoch_seconds = max(self.updated_at_epoch_seconds, entry.timestamp_epoch_seconds)

    def merge_latest_refs(self, refs: Mapping[str, Any] | None) -> None:
        self.latest_refs = merge_latest_refs(self.latest_refs, refs)
        self.updated_at_epoch_seconds = max(self.updated_at_epoch_seconds, time())

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "created_at_epoch_seconds": self.created_at_epoch_seconds,
            "updated_at_epoch_seconds": self.updated_at_epoch_seconds,
            "status": self.status,
            "reason_code": self.reason_code,
            "latest_refs": normalize_latest_refs(self.latest_refs),
            "action_history": [asdict(entry) for entry in self.action_history],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RunArtifact":
        history: list[ActionHistoryEntry] = []
        for row in list(payload.get("action_history") or []):
            if not isinstance(row, Mapping):
                continue
            history.append(
                ActionHistoryEntry(
                    sequence_index=int(row.get("sequence_index") or 0),
                    action_id=normalize_action_id(row.get("action_id") or ""),
                    idempotency_key=str(row.get("idempotency_key") or ""),
                    executed=bool(row.get("executed", False)),
                    reason_codes=tuple(str(item) for item in list(row.get("reason_codes") or []) if str(item).strip()),
                    artifact_refs=tuple(str(item) for item in list(row.get("artifact_refs") or []) if str(item).strip()),
                    timestamp_epoch_seconds=float(row.get("timestamp_epoch_seconds") or 0.0),
                    refusal=ExecutionRefusal(
                        reason_code=str(row["refusal"].get("reason_code") or "refused"),
                        retryable=bool(row["refusal"].get("retryable", False)),
                        blocked_by_budget=bool(row["refusal"].get("blocked_by_budget", False)),
                        blocked_by_invariant=bool(row["refusal"].get("blocked_by_invariant", False)),
                        missing_inputs=tuple(
                            str(item) for item in list(row["refusal"].get("missing_inputs") or []) if str(item).strip()
                        ),
                    )
                    if isinstance(row.get("refusal"), Mapping)
                    else None,
                )
            )
        return cls(
            run_id=str(payload.get("run_id") or "unknown_run"),
            session_id=str(payload.get("session_id") or "unknown_session"),
            created_at_epoch_seconds=float(payload.get("created_at_epoch_seconds") or time()),
            updated_at_epoch_seconds=float(payload.get("updated_at_epoch_seconds") or time()),
            status=str(payload.get("status") or "running"),
            reason_code=str(payload.get("reason_code") or "").strip() or None,
            latest_refs=normalize_latest_refs(payload.get("latest_refs") if isinstance(payload.get("latest_refs"), Mapping) else {}),
            action_history=history,
        )
