from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from .adapters.artifacts_fs import ArtifactsFSAdapter
from .adapters.dossiers_fs import DossiersFSAdapter
from .types import CorpusEntry, CorpusEntryKind, CorpusEntryRef, CorpusView


@dataclass
class CorpusHydrator:
    """
    Hydrate a `CorpusEntryRef` into a `CorpusEntry` (text + metadata).

    v0: implements finalized dossier text hydration; expands over time.
    """

    dossiers: DossiersFSAdapter = DossiersFSAdapter()
    artifacts: ArtifactsFSAdapter = ArtifactsFSAdapter()

    def _read_text_file(self, p: Path) -> str:
        return p.read_text(encoding="utf-8")

    def _read_json(self, p: Path) -> Dict[str, Any]:
        return json.loads(self._read_text_file(p))

    def _compute_content_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def hydrate(self, ref: CorpusEntryRef) -> CorpusEntry:
        if (
            ref.view == CorpusView.FINALIZED
            and ref.dossier_id
            and ref.kind == CorpusEntryKind.FINALIZED_DOSSIER_TEXT
        ):
            p = self.dossiers.latest_finalized_snapshot_path(ref.dossier_id)
            if not p:
                return CorpusEntry(
                    ref=ref,
                    text="",
                    provenance={"error": "finalized_snapshot_not_found"},
                )
            payload = self._read_json(p)
            # finalized snapshots store stitched_text (string) plus sections metadata
            text = str(payload.get("stitched_text") or "")
            content_hash = payload.get("sha256") or self._compute_content_hash(text)
            return CorpusEntry(
                ref=ref,
                text=text,
                mime_type="application/json",
                title=payload.get("title"),
                created_at=payload.get("generated_at"),
                content_hash=content_hash,
                structured_json=payload,
                provenance={
                    "source": "dossier_final",
                    "path": str(p),
                    "dossier_id": ref.dossier_id,
                },
            )

        # v0 fallback: empty entry, but keep reference/provenance for debugging
        return CorpusEntry(
            ref=ref,
            text="",
            provenance={"warning": "unimplemented_hydration"},
        )

