"""Bootstrap helpers for controller run inputs."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from config.paths import agent_kernel_artifacts_root, dossiers_artifacts_root
from corpus.types import CorpusEntryKind, CorpusEntryRef, CorpusView
from corpus.virtual_provider import VirtualCorpusProvider


@dataclass(frozen=True)
class DeedTextArtifact:
    artifact_path: str
    excerpt: str


def persist_deed_text_artifact(*, request_id: str, deed_text: str, dossier_id: str | None) -> DeedTextArtifact:
    root = agent_kernel_artifacts_root() / "controller_inputs" / "deed_text" / request_id
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{uuid4().hex[:10]}.json"
    payload = {
        "artifact_type": "deed_text",
        "request_id": request_id,
        "dossier_id": dossier_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "text": deed_text,
    }
    fd, tmp_path = tempfile.mkstemp(prefix="controller_deed_", suffix=".json", dir=str(root))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.replace(tmp_path, str(path))
        except PermissionError:
            with path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
    return DeedTextArtifact(artifact_path=str(path), excerpt=deed_text[:1000])


def hydrate_and_persist_finalized_dossier_text(
    *,
    request_id: str,
    dossier_id: str,
    provider: VirtualCorpusProvider | None = None,
) -> DeedTextArtifact | None:
    promoted_text = _load_promoted_transcript_text_for_mapping(dossier_id=dossier_id)
    if promoted_text:
        return persist_deed_text_artifact(
            request_id=request_id,
            deed_text=promoted_text,
            dossier_id=dossier_id,
        )

    corpus = provider or VirtualCorpusProvider()
    ref = CorpusEntryRef(
        view=CorpusView.FINALIZED,
        entry_id=f"final:{dossier_id}",
        kind=CorpusEntryKind.FINALIZED_DOSSIER_TEXT,
        dossier_id=dossier_id,
    )
    entry = corpus.hydrate_entry(ref)
    text = (entry.text or "").strip()
    if not text:
        return None
    provenance_error = str((entry.provenance or {}).get("error") or "").strip()
    if provenance_error:
        return None
    return persist_deed_text_artifact(
        request_id=request_id,
        deed_text=text,
        dossier_id=dossier_id,
    )


def _load_promoted_transcript_text_for_mapping(*, dossier_id: str) -> str | None:
    pointer = dossiers_artifacts_root() / "transcription_edit" / str(dossier_id) / "latest_transcript_for_mapping.json"
    if not pointer.exists():
        return None
    try:
        pointer_payload = json.loads(pointer.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(pointer_payload, dict):
        return None
    transcript_ref = pointer_payload.get("transcript_ref")
    if not isinstance(transcript_ref, str) or not transcript_ref.strip():
        return None
    transcript_path = Path(transcript_ref)
    if not transcript_path.exists():
        return None
    try:
        payload = json.loads(transcript_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return _extract_transcript_text(payload)


def _extract_transcript_text(payload: Any) -> str | None:
    if isinstance(payload, str):
        text = payload.strip()
        return text or None
    if not isinstance(payload, dict):
        return None
    text = payload.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    sections = payload.get("sections")
    if isinstance(sections, list):
        parts: list[str] = []
        for section in sections:
            if not isinstance(section, dict):
                continue
            body = section.get("body")
            if isinstance(body, str) and body.strip():
                parts.append(body.strip())
        joined = "\n\n".join(parts).strip()
        if joined:
            return joined
    return None
