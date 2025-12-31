from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

from config.paths import (
    dossiers_georefs_artifacts_root,
    dossiers_schemas_artifacts_root,
    dossiers_state_root,
)


@dataclass
class ArtifactsFSAdapter:
    """
    Filesystem adapter for artifacts under dossiers_data/artifacts/.
    """

    def schemas_dir(self, dossier_id: str) -> Path:
        return dossiers_schemas_artifacts_root(str(dossier_id))

    def georefs_dir(self, dossier_id: str) -> Path:
        return dossiers_georefs_artifacts_root(str(dossier_id))

    def schemas_latest_path(self, dossier_id: str) -> Path:
        return self.schemas_dir(dossier_id) / "latest.json"

    def georefs_latest_path(self, dossier_id: str) -> Path:
        return self.georefs_dir(dossier_id) / "latest.json"

    def _schemas_index_path(self) -> Path:
        return dossiers_state_root() / "schemas_index.json"

    def _georefs_index_path(self) -> Path:
        return dossiers_state_root() / "georefs_index.json"

    def iter_schema_latest(self) -> Iterable[Tuple[str, Path]]:
        """
        Enumerate (dossier_id, latest_schema_path) pairs.

        Prefer schemas_index.json written by SchemaPersistenceService, falling
        back to scanning artifacts/schemas/*/latest.json.
        """

        idx_path = self._schemas_index_path()
        if idx_path.exists():
            try:
                import json

                with idx_path.open("r", encoding="utf-8") as f:
                    data: Dict[str, object] = json.load(f) or {}
                for entry in data.get("schemas", []) or []:
                    did = (entry or {}).get("dossier_id")  # type: ignore[union-attr]
                    latest = (entry or {}).get("latest_path")  # type: ignore[union-attr]
                    if isinstance(did, str) and isinstance(latest, str) and did.strip() and latest.strip():
                        p = Path(latest)
                        if p.exists():
                            yield (did.strip(), p)
                return
            except Exception:
                # Fall back to scan
                pass

        root = dossiers_schemas_artifacts_root()
        if not root.exists():
            return
        for ddir in root.iterdir():
            if not ddir.is_dir():
                continue
            did = ddir.name
            latest = ddir / "latest.json"
            if latest.exists():
                yield (did, latest)

    def iter_georef_latest(self) -> Iterable[Tuple[str, Path]]:
        """
        Enumerate (dossier_id, latest_georef_path) pairs.

        Prefer georefs_index.json when present, with a scan fallback.
        """

        idx_path = self._georefs_index_path()
        if idx_path.exists():
            try:
                import json

                with idx_path.open("r", encoding="utf-8") as f:
                    data: Dict[str, object] = json.load(f) or {}
                for entry in data.get("georefs", []) or []:
                    did = (entry or {}).get("dossier_id")  # type: ignore[union-attr]
                    gid = (entry or {}).get("georef_id")  # type: ignore[union-attr]
                    if isinstance(did, str) and isinstance(gid, str) and did.strip() and gid.strip():
                        latest = dossiers_georefs_artifacts_root(str(did)) / "latest.json"
                        if latest.exists():
                            yield (did.strip(), latest)
                return
            except Exception:
                # Fall back to scan
                pass

        root = dossiers_georefs_artifacts_root()
        if not root.exists():
            return
        for ddir in root.iterdir():
            if not ddir.is_dir():
                continue
            did = ddir.name
            latest = ddir / "latest.json"
            if latest.exists():
                yield (did, latest)

