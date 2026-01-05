from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AssetStatus(str, Enum):
    MISSING = "missing"
    INSTALLING = "installing"
    INSTALLED = "installed"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass(frozen=True)
class AssetDefinition:
    asset_id: str
    display_name: str
    kind: str
    source: str
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AssetProgress:
    status: AssetStatus
    stage: Optional[str] = None
    message: Optional[str] = None
    percent: Optional[float] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "stage": self.stage,
            "message": self.message,
            "percent": self.percent,
            "error": self.error,
        }


@dataclass
class AssetFileEntry:
    path: str
    bytes: int
    sha256: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {"path": self.path, "bytes": self.bytes, "sha256": self.sha256}


@dataclass
class AssetManifest:
    asset_id: str
    source: str
    revision: str
    installed_at: str
    files: List[AssetFileEntry]
    total_bytes: int
    smoke_test: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "source": self.source,
            "revision": self.revision,
            "installed_at": self.installed_at,
            "files": [f.to_dict() for f in self.files],
            "total_bytes": self.total_bytes,
            "smoke_test": self.smoke_test,
        }
