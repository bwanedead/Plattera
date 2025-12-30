from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class CompileStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    NEEDS_USER_INPUT = "needs_user_input"
    FAILED = "failed"


@dataclass
class CompileReport:
    """
    Normalized output from deterministic judge steps.

    v0: minimal scaffold; expanded later to include structured diagnostics.
    """

    status: CompileStatus
    diagnostics: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Gap:
    """
    Typed "need" derived from a CompileReport + schema attempt.
    """

    kind: str
    message: str
    severity: str = "error"
    metadata: Dict[str, Any] = field(default_factory=dict)


