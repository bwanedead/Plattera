from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class RetrievalEvent:
    query: str
    lane: str
    result_count: int
    dossier_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SchemaAttemptEvent:
    dossier_id: str
    schema_id: Optional[str] = None
    status: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OutcomeEvent:
    dossier_id: str
    outcome: str
    metadata: Dict[str, Any] = field(default_factory=dict)


