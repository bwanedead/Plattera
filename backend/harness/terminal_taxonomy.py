from __future__ import annotations

from typing import Literal

TerminalClass = Literal[
    "completed",
    "blocked",
    "waiting_human",
    "waiting_evidence",
    "exhausted",
    "failed",
    "paused",
    "stopped",
]
