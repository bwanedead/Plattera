from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_MAX_FAILURE_HISTORY = 5


@dataclass
class TurnRecoveryState:
    """Durable mechanical context for recoverable failed model turns."""

    consecutive_failures: int = 0
    last_failure: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)

    def has_pending_recovery(self) -> bool:
        return bool(self.last_failure)

    def record_failure(self, failure: dict[str, Any]) -> None:
        row = dict(failure)
        self.consecutive_failures = int(self.consecutive_failures) + 1
        row["consecutive_failures"] = int(self.consecutive_failures)
        self.last_failure = row
        self.history.append(row)
        if len(self.history) > _MAX_FAILURE_HISTORY:
            self.history = self.history[-_MAX_FAILURE_HISTORY:]

    def clear(self) -> None:
        self.consecutive_failures = 0
        self.last_failure = {}

    def to_wire(self) -> dict[str, Any]:
        return {
            "consecutive_failures": int(self.consecutive_failures),
            "last_failure": dict(self.last_failure),
            "history": list(self.history),
        }

    @classmethod
    def from_wire(cls, payload: Any) -> "TurnRecoveryState":
        if not isinstance(payload, dict):
            return cls()
        try:
            consecutive = max(0, int(payload.get("consecutive_failures", 0)))
        except (TypeError, ValueError):
            consecutive = 0
        last = payload.get("last_failure")
        history = payload.get("history")
        return cls(
            consecutive_failures=consecutive,
            last_failure=dict(last) if isinstance(last, dict) else {},
            history=[dict(row) for row in history if isinstance(row, dict)][-_MAX_FAILURE_HISTORY:]
            if isinstance(history, list)
            else [],
        )
