from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from config.paths import dossiers_root, dossiers_views_root


@dataclass
class DossiersFSAdapter:
    """
    Filesystem adapter over `dossiers_data/` (dev) or app data (frozen).

    This is intentionally minimal in v0; it exists so corpus + retrieval code
    never hardcodes storage paths.
    """

    def dossiers_root(self) -> Path:
        return dossiers_root()

    def transcriptions_root(self) -> Path:
        return dossiers_views_root()

    def finalized_snapshot_dir(self, dossier_id: str) -> Path:
        return dossiers_views_root() / str(dossier_id) / "final"

    def finalized_pointer_path(self, dossier_id: str) -> Path:
        return self.finalized_snapshot_dir(dossier_id) / "dossier_final.json"

    def latest_finalized_snapshot_path(self, dossier_id: str) -> Optional[Path]:
        d = self.finalized_snapshot_dir(dossier_id)
        if not d.exists():
            return None
        pointer = self.finalized_pointer_path(dossier_id)
        if pointer.exists():
            return pointer
        snaps = sorted(d.glob("dossier_final_*.json"), reverse=True)
        return snaps[0] if snaps else None


