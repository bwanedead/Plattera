from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from config.paths import dossiers_georefs_artifacts_root, dossiers_schemas_artifacts_root


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


