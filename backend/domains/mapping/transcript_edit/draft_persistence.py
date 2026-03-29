from __future__ import annotations

import json
from pathlib import Path

from services.dossier.edit_persistence_service import EditPersistenceService


def persist_agent_edit_draft(
    *,
    dossier_id: str | None,
    transcription_id: str | None,
    source_transcript_ref: str | None,
    run_id: str | None,
    reason_code: str | None,
) -> None:
    if not dossier_id or not transcription_id or not source_transcript_ref:
        return
    try:
        raw = json.loads(Path(source_transcript_ref).read_text(encoding="utf-8"))
    except Exception:
        return
    sections = raw.get("sections") if isinstance(raw, dict) else None
    if not isinstance(sections, list):
        text_value = ""
        if isinstance(raw, dict):
            text_value = str(raw.get("text") or raw.get("extracted_text") or "")
        elif isinstance(raw, str):
            text_value = raw
        sections = [{"id": 1, "body": text_value}]
    try:
        EditPersistenceService().save_agent_edit_draft(
            dossier_id=str(dossier_id),
            transcription_id=str(transcription_id),
            sections=sections,
            source_ref=source_transcript_ref,
            run_id=run_id,
            reason_code=reason_code,
        )
    except Exception:
        return
