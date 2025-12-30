from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class LoopOutcome(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    NEEDS_UPLOAD = "needs_upload"
    NEEDS_USER_CHOICE = "needs_user_choice"
    FAILED_BUDGET = "failed_budget"


@dataclass
class LoopBudget:
    max_iterations: int = 5
    max_retrieval_calls: int = 10


@dataclass
class LoopState:
    iteration: int = 0
    debug: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)


