"""Atomic writer for canonical finalized dossier snapshots."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.paths import dossiers_views_root


class FinalizedSnapshotService:
    """Persist dossier_final.json snapshots in the corpus-hydratable canonical location."""

    def write_finalized_snapshot(
        self,
        *,
        dossier_id: str,
        stitched_text: str,
        dossier_title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Path:
        if not dossier_id:
            raise ValueError("dossier_id is required")
        final_dir = dossiers_views_root() / str(dossier_id) / "final"
        final_dir.mkdir(parents=True, exist_ok=True)
        path = final_dir / "dossier_final.json"
        now = datetime.now(timezone.utc).isoformat()
        text = stitched_text or ""
        payload = {
            "dossier_id": str(dossier_id),
            "dossier_title": dossier_title or f"Direct Text {str(dossier_id)[:8]}",
            "generated_at": now,
            "stitched_text": text,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "metadata": metadata or {},
        }
        _atomic_write_json(path, payload)
        return path


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    fd, tmp_path = tempfile.mkstemp(prefix="finalized_", suffix=".json", dir=str(path.parent))
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
