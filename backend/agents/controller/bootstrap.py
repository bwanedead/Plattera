"""Bootstrap helpers for controller run inputs."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from config.paths import agent_kernel_artifacts_root
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
