from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .adapters.artifacts_fs import ArtifactsFSAdapter
from .adapters.dossiers_fs import DossiersFSAdapter
from .models import CorpusDoc, CorpusDocRef, CorpusView


@dataclass
class CorpusHydrator:
    """
    Hydrate a `CorpusDocRef` into a `CorpusDoc` (text + provenance).

    v0: implements only minimal finalized hydration; expands over time.
    """

    dossiers: DossiersFSAdapter = DossiersFSAdapter()
    artifacts: ArtifactsFSAdapter = ArtifactsFSAdapter()

    def _read_text_file(self, p: Path) -> str:
        return p.read_text(encoding="utf-8")

    def _read_json(self, p: Path) -> Dict[str, Any]:
        return json.loads(self._read_text_file(p))

    def hydrate(self, ref: CorpusDocRef) -> CorpusDoc:
        if ref.view == CorpusView.FINALIZED and ref.dossier_id:
            p = self.dossiers.latest_finalized_snapshot_path(ref.dossier_id)
            if not p:
                return CorpusDoc(ref=ref, text="", provenance={"error": "finalized_snapshot_not_found"})
            payload = self._read_json(p)
            # finalized snapshots store stitched_text (string) plus sections metadata
            text = str(payload.get("stitched_text") or "")
            return CorpusDoc(
                ref=ref,
                text=text,
                mime_type="application/json",
                provenance={
                    "source": "dossier_final",
                    "path": str(p),
                    "dossier_id": ref.dossier_id,
                    "sha256": payload.get("sha256"),
                    "generated_at": payload.get("generated_at"),
                },
                extra={"payload": payload},
            )

        # v0 fallback: empty doc, but keep reference/provenance for debugging
        return CorpusDoc(ref=ref, text="", provenance={"warning": "unimplemented_hydration"})


