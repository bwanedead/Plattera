"""Artifact persistence for transcription edit loop v0."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from config.paths import dossiers_artifacts_root

from .contracts import ApplyReportV0, EditPlanV0, TranscriptDocumentV0


class TranscriptionEditPersistenceService:
    def __init__(self, root: Path | None = None) -> None:
        self._root = root if root is not None else dossiers_artifacts_root() / "transcription_edit"
        self._root.mkdir(parents=True, exist_ok=True)

    def _atomic_write(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix="tx_edit_", suffix=".json", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, str(path))
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    def _artifact_dir(self, dossier_id: str) -> Path:
        path = self._root / str(dossier_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _new_artifact_path(self, dossier_id: str, prefix: str) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        return self._artifact_dir(dossier_id) / f"{prefix}_{stamp}_{uuid4().hex[:8]}.json"

    def save_edit_plan(self, *, dossier_id: str, plan: EditPlanV0) -> str:
        path = self._new_artifact_path(dossier_id, "edit_plan")
        self._atomic_write(path, plan.model_dump(mode="json"))
        return str(path)

    def save_apply_report(self, *, dossier_id: str, report: ApplyReportV0) -> str:
        path = self._new_artifact_path(dossier_id, "apply_report")
        self._atomic_write(path, report.model_dump(mode="json"))
        return str(path)

    def save_edited_transcript(self, *, dossier_id: str, document: TranscriptDocumentV0) -> str:
        path = self._new_artifact_path(dossier_id, "edited_transcript")
        self._atomic_write(path, document.model_dump(mode="json"))
        return str(path)

    def save_source_transcript_input(self, *, dossier_id: str, document: TranscriptDocumentV0) -> str:
        path = self._new_artifact_path(dossier_id, "transcript_input")
        self._atomic_write(path, document.model_dump(mode="json"))
        return str(path)

    def save_validator_report(self, *, dossier_id: str, report_payload: dict[str, Any]) -> str:
        path = self._new_artifact_path(dossier_id, "validator_report")
        self._atomic_write(path, report_payload)
        return str(path)

    def save_raw_model_output(self, *, dossier_id: str, payload: dict[str, Any]) -> str:
        path = self._new_artifact_path(dossier_id, "raw_model_output")
        self._atomic_write(path, payload)
        return str(path)

    def save_json_extraction_metric(self, *, dossier_id: str, payload: dict[str, Any]) -> str:
        path = self._new_artifact_path(dossier_id, "json_extraction_metric")
        self._atomic_write(path, payload)
        return str(path)

    def write_latest_transcript_for_mapping(
        self,
        *,
        dossier_id: str,
        transcript_ref: str,
        transcript_hash: str,
        run_id: str | None = None,
    ) -> str:
        pointer = self._artifact_dir(dossier_id) / "latest_transcript_for_mapping.json"
        payload = {
            "dossier_id": str(dossier_id),
            "transcript_ref": transcript_ref,
            "transcript_hash": transcript_hash,
            "run_id": run_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._atomic_write(pointer, payload)
        return str(pointer)
