"""Agent-facing compact finalization decision vocabulary (domain-owned).

Shared by the tool schema and the tooling session/decision modules so
domains → tooling dependency direction stays one-way.
"""

from __future__ import annotations

ALLOWED_SCOPE_STATUSES: tuple[str, ...] = ("handoffable", "blocked")
ALLOWED_CORRECTION_DISPOSITIONS: tuple[str, ...] = (
    "confirmed_source_repair",
    "ir_only_exception",
    "needs_hitl",
)
ALLOWED_DEPENDENCY_DISPOSITIONS: tuple[str, ...] = ("include", "not_applicable")
ALLOWED_CLOSURE_STATUSES: tuple[str, ...] = ("closed", "partial", "blocked")
