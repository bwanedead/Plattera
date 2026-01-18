from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class IndexMaintenanceJobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class IndexMaintenanceJobRequest:
    pool_identifier: str
    mode: str
    limit: int
    dossier_id: Optional[str]
    dry_run: bool


@dataclass(frozen=True)
class IndexMaintenanceRuntimeIdentity:
    embedding_model_fingerprint: str
    chunking_policy_id: str


@dataclass
class IndexMaintenanceProgress:
    total: int = 0
    done: int = 0
    ok: int = 0
    failed: int = 0


@dataclass(frozen=True)
class IndexMaintenanceSliceResult:
    dossier_id: str
    entry_id: str
    status: str
    reason_code: Optional[str] = None
    detail: Optional[str] = None


@dataclass
class IndexMaintenanceJob:
    id: str
    request: IndexMaintenanceJobRequest
    identity: Optional[IndexMaintenanceRuntimeIdentity]
    status: IndexMaintenanceJobStatus = IndexMaintenanceJobStatus.QUEUED
    progress: IndexMaintenanceProgress = field(default_factory=IndexMaintenanceProgress)
    results: List[IndexMaintenanceSliceResult] = field(default_factory=list)
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    @staticmethod
    def new(
        *,
        request: IndexMaintenanceJobRequest,
        identity: Optional[IndexMaintenanceRuntimeIdentity],
    ) -> "IndexMaintenanceJob":
        return IndexMaintenanceJob(
            id=str(uuid.uuid4()),
            request=request,
            identity=identity,
        )

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        if self.identity is None:
            data["identity"] = None
        return data
