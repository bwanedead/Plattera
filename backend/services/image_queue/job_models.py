from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime
import uuid


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


@dataclass
class ImageToTextJob:
    id: str
    user_id: Optional[str]
    source_filename: str
    source_path: str
    model: str
    extraction_mode: str
    enhancement_settings: Dict[str, Any] = field(default_factory=dict)
    dossier_id: Optional[str] = None
    transcription_id: Optional[str] = None
    redundancy_count: int = 1
    consensus_strategy: str = "sequential"
    auto_llm_consensus: bool = False
    llm_consensus_model: str = "gpt-5-consensus"
    auto_create_dossier_per_file: bool = False

    status: JobStatus = JobStatus.PENDING
    attempts: int = 0
    error: Optional[str] = None
    result_path: Optional[str] = None

    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    @staticmethod
    def new(
        source_filename: str,
        source_path: str,
        model: str,
        extraction_mode: str,
        enhancement_settings: Dict[str, Any],
        user_id: Optional[str] = None,
        dossier_id: Optional[str] = None,
        transcription_id: Optional[str] = None,
        redundancy_count: int = 1,
        consensus_strategy: str = "sequential",
        auto_llm_consensus: bool = False,
        llm_consensus_model: str = "gpt-5-consensus",
        auto_create_dossier_per_file: bool = False,
    ) -> "ImageToTextJob":
        return ImageToTextJob(
            id=str(uuid.uuid4()),
            user_id=user_id,
            source_filename=source_filename,
            source_path=source_path,
            model=model,
            extraction_mode=extraction_mode,
            enhancement_settings=enhancement_settings,
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            redundancy_count=redundancy_count,
            consensus_strategy=consensus_strategy,
            auto_llm_consensus=auto_llm_consensus,
            llm_consensus_model=llm_consensus_model,
            auto_create_dossier_per_file=auto_create_dossier_per_file,
        )

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


