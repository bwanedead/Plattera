from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .adapters.artifacts_fs import ArtifactsFSAdapter
from .adapters.dossiers_fs import DossiersFSAdapter
from .types import CorpusEntry, CorpusEntryKind, CorpusEntryRef, CorpusView


@dataclass
class CorpusHydrator:
    """
    Hydrate a `CorpusEntryRef` into a `CorpusEntry` (text + metadata).

    v0: implements finalized dossier text hydration and conservative transcript
    / artifact hydration; expands over time.
    """

    dossiers: DossiersFSAdapter = DossiersFSAdapter()
    artifacts: ArtifactsFSAdapter = ArtifactsFSAdapter()

    def _read_text_file(self, p: Path) -> str:
        return p.read_text(encoding="utf-8")

    def _read_json(self, p: Path) -> Dict[str, Any]:
        return json.loads(self._read_text_file(p))

    def _compute_content_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _mtime_iso(self, p: Path) -> Optional[str]:
        try:
            ts = p.stat().st_mtime
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        except Exception:
            return None

    def _empty_with_error(self, ref: CorpusEntryRef, *, error: str, path: Optional[Path] = None) -> CorpusEntry:
        prov: Dict[str, Any] = {"error": error}
        if path is not None:
            prov["path"] = str(path)
        return CorpusEntry(ref=ref, text="", provenance=prov)

    def hydrate(self, ref: CorpusEntryRef) -> CorpusEntry:
        try:
            if (
                ref.view == CorpusView.FINALIZED
                and ref.dossier_id
                and ref.kind == CorpusEntryKind.FINALIZED_DOSSIER_TEXT
            ):
                return self._hydrate_finalized(ref)

            if ref.kind == CorpusEntryKind.TRANSCRIPT and ref.dossier_id and ref.transcription_id:
                return self._hydrate_transcript(ref)

            if ref.kind == CorpusEntryKind.SCHEMA_JSON and ref.dossier_id:
                return self._hydrate_schema(ref)

            if ref.kind == CorpusEntryKind.GEOREF_JSON and ref.dossier_id:
                return self._hydrate_georef(ref)

            # v0 fallback: empty entry, but keep reference/provenance for debugging
            return CorpusEntry(
                ref=ref,
                text="",
                provenance={"warning": "unimplemented_hydration"},
            )
        except Exception as exc:
            # Never throw; return an error-marked entry instead.
            return CorpusEntry(
                ref=ref,
                text="",
                provenance={"error": f"exception_during_hydration: {exc!r}"},
            )

    # ----- Kind-specific helpers -----

    def _hydrate_finalized(self, ref: CorpusEntryRef) -> CorpusEntry:
        assert ref.dossier_id is not None
        p = self.dossiers.latest_finalized_snapshot_path(ref.dossier_id)
        if not p:
            return self._empty_with_error(ref, error="finalized_snapshot_not_found")

        try:
            payload = self._read_json(p)
        except Exception:
            return self._empty_with_error(ref, error="finalized_snapshot_corrupt", path=p)

        text = str(payload.get("stitched_text") or "")
        content_hash = payload.get("sha256") or self._compute_content_hash(text)
        created_at = payload.get("generated_at") or self._mtime_iso(p)
        title = payload.get("dossier_title") or payload.get("title")

        return CorpusEntry(
            ref=ref,
            text=text,
            mime_type="application/json",
            title=title,
            created_at=created_at,
            content_hash=content_hash,
            structured_json=payload,
            provenance={
                "source": "dossier_final",
                "path": str(p),
                "dossier_id": ref.dossier_id,
            },
        )

    def _hydrate_transcript(self, ref: CorpusEntryRef) -> CorpusEntry:
        assert ref.dossier_id is not None and ref.transcription_id is not None
        p = self.dossiers.transcript_raw_path(ref.dossier_id, ref.transcription_id)
        if not p.exists():
            return self._empty_with_error(ref, error="transcript_raw_not_found", path=p)

        try:
            payload = self._read_json(p)
        except Exception:
            return self._empty_with_error(ref, error="transcript_raw_corrupt", path=p)

        text = ""
        if isinstance(payload, dict):
            if "text" in payload:
                text = str(payload.get("text") or "").strip()
            elif "sections" in payload:
                sections = payload.get("sections") or []
                parts = []
                for s in sections:
                    if isinstance(s, dict):
                        body = s.get("body")
                        if isinstance(body, str):
                            parts.append(body)
                text = "\n\n".join(parts).strip()

        content_hash = (
            payload.get("original_text_sha256")
            if isinstance(payload, dict)
            else None
        ) or self._compute_content_hash(text)
        created_at = None
        if isinstance(payload, dict):
            created_at = (
                payload.get("saved_at")
                or payload.get("created_at")
                or payload.get("createdAt")
            )
        if not created_at:
            created_at = self._mtime_iso(p)

        return CorpusEntry(
            ref=ref,
            text=text,
            mime_type="application/json",
            title=(payload.get("title") if isinstance(payload, dict) else None),
            created_at=created_at,
            content_hash=content_hash,
            structured_json=payload if isinstance(payload, dict) else None,
            provenance={
                "source": "transcript_raw",
                "path": str(p),
                "dossier_id": ref.dossier_id,
                "transcription_id": ref.transcription_id,
            },
        )

    def _hydrate_schema(self, ref: CorpusEntryRef) -> CorpusEntry:
        assert ref.dossier_id is not None
        p = self.artifacts.schemas_latest_path(ref.dossier_id)
        if not p.exists():
            return self._empty_with_error(ref, error="schema_latest_not_found", path=p)

        try:
            payload = self._read_json(p)
        except Exception:
            return self._empty_with_error(ref, error="schema_latest_corrupt", path=p)

        text = json.dumps(payload, ensure_ascii=False)
        content_hash = None
        if isinstance(payload, dict):
            content_hash = (
                payload.get("original_text_sha256")
                or payload.get("schema_sha256")
                or payload.get("sha256")
            )
        if not content_hash:
            content_hash = self._compute_content_hash(text)

        created_at = None
        if isinstance(payload, dict):
            created_at = payload.get("saved_at") or payload.get("createdAt")
        if not created_at:
            created_at = self._mtime_iso(p)

        title = None
        if isinstance(payload, dict):
            meta = payload.get("metadata") or {}
            if isinstance(meta, dict):
                title = meta.get("schema_label") or meta.get("label")

        return CorpusEntry(
            ref=ref,
            text=text,
            mime_type="application/json",
            title=title,
            created_at=created_at,
            content_hash=content_hash,
            structured_json=payload if isinstance(payload, dict) else None,
            provenance={
                "source": "schema_latest",
                "path": str(p),
                "dossier_id": ref.dossier_id,
            },
        )

    def _hydrate_georef(self, ref: CorpusEntryRef) -> CorpusEntry:
        assert ref.dossier_id is not None
        p = self.artifacts.georefs_latest_path(ref.dossier_id)
        if not p.exists():
            return self._empty_with_error(ref, error="georef_latest_not_found", path=p)

        try:
            payload = self._read_json(p)
        except Exception:
            return self._empty_with_error(ref, error="georef_latest_corrupt", path=p)

        text = json.dumps(payload, ensure_ascii=False)
        content_hash = None
        if isinstance(payload, dict):
            content_hash = payload.get("sha256")
        if not content_hash:
            content_hash = self._compute_content_hash(text)

        created_at = None
        if isinstance(payload, dict):
            created_at = payload.get("saved_at") or payload.get("createdAt")
        if not created_at:
            created_at = self._mtime_iso(p)

        title = None
        if isinstance(payload, dict):
            title = payload.get("label") or payload.get("name")

        return CorpusEntry(
            ref=ref,
            text=text,
            mime_type="application/json",
            title=title,
            created_at=created_at,
            content_hash=content_hash,
            structured_json=payload if isinstance(payload, dict) else None,
            provenance={
                "source": "georef_latest",
                "path": str(p),
                "dossier_id": ref.dossier_id,
            },
        )

