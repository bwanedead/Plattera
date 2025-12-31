from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

from config.paths import (
    dossiers_management_root,
    dossiers_root,
    dossiers_state_root,
    dossiers_views_root,
)


@dataclass
class DossiersFSAdapter:
    """
    Filesystem adapter over `dossiers_data/` (dev) or app data (frozen).

    This remains intentionally light; it exists so corpus + retrieval code never
    hardcodes storage paths.
    """

    def dossiers_root(self) -> Path:
        return dossiers_root()

    def transcriptions_root(self) -> Path:
        return dossiers_views_root()

    # ----- Finalized snapshots -----

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

    def _finalized_index_path(self) -> Path:
        return dossiers_state_root() / "finalized_index.json"

    def iter_finalized_dossier_ids(self) -> Iterable[str]:
        """
        Enumerate dossier_ids with finalized snapshots.

        Prefer the finalized_index.json written by FinalizationService, falling
        back to scanning the views/transcriptions tree.
        """

        idx_path = self._finalized_index_path()
        if idx_path.exists():
            try:
                import json

                with idx_path.open("r", encoding="utf-8") as f:
                    data = json.load(f) or {}
                for entry in data.get("finalized", []) or []:
                    did = (entry or {}).get("dossier_id")
                    if isinstance(did, str) and did.strip():
                        yield did.strip()
                return
            except Exception:
                # Fall back to scan
                pass

        root = self.transcriptions_root()
        if not root.exists():
            return
        for child in root.iterdir():
            if child.is_dir() and (child / "final").exists():
                yield child.name

    # ----- Dossier ids (generic) -----

    def iter_dossier_ids(self) -> Iterable[str]:
        """
        Enumerate dossier_ids present in the workspace.

        Prefer management metadata files (dossier_*.json); fall back to
        transcriptions folders.
        """

        mgmt_root = dossiers_management_root()
        if mgmt_root.exists():
            for p in mgmt_root.glob("dossier_*.json"):
                name = p.stem
                # dossier_<id>
                if name.startswith("dossier_"):
                    did = name[len("dossier_") :]
                    if did:
                        yield did
            # If we found any via management, stop there
            return

        root = self.transcriptions_root()
        if not root.exists():
            return
        for child in root.iterdir():
            if child.is_dir():
                yield child.name

    # ----- Transcription runs (HEAD only) -----

    def transcript_raw_path(self, dossier_id: str, transcription_id: str) -> Path:
        """
        Canonical path for a raw transcription JSON file.
        """

        return (
            self.transcriptions_root()
            / str(dossier_id)
            / str(transcription_id)
            / "raw"
            / f"{transcription_id}.json"
        )

    def iter_transcription_heads(self, dossier_id: Optional[str] = None) -> Iterator[Tuple[str, str, Path]]:
        """
        Conservative enumeration of transcription "heads".

        For each (dossier_id, transcription_id) pair, yield a single raw JSON
        file path if it exists:
        - dossiers_data/views/transcriptions/<dossier_id>/<transcription_id>/raw/<transcription_id>.json
        """

        root = self.transcriptions_root()
        if not root.exists():
            return

        dossiers: List[Path]
        if dossier_id:
            dossiers = [root / str(dossier_id)]
        else:
            dossiers = [p for p in root.iterdir() if p.is_dir()]

        for ddir in dossiers:
            did = ddir.name
            for run_dir in ddir.iterdir():
                if not run_dir.is_dir():
                    continue
                tid = run_dir.name
                raw = run_dir / "raw" / f"{tid}.json"
                if raw.exists():
                    yield (did, tid, raw)

