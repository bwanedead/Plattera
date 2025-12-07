"""
Centralized path configuration for backend data storage.

Responsibilities:
- Decide dev vs frozen (PyInstaller) mode.
- Provide stable roots for dossiers_data and PLSS data.
- Expose small helpers for domain-specific subtrees.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    """Detect if we are running inside a PyInstaller bundle."""
    return getattr(sys, "frozen", False) is True


def backend_root() -> Path:
    """
    Backend source root (the 'backend' directory in the repo).
    In frozen mode this resolves under the PyInstaller extraction dir, so it should
    NOT be used for user data.
    """
    if is_frozen():
        # When running from a PyInstaller one-file EXE, Python modules and bundled
        # resources are unpacked under sys._MEIPASS. Our build command places the
        # backend folder (including schema/) under that root as "backend/...".
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
        return base / "backend"

    # Dev / non-frozen: backend/config/paths.py -> backend/config -> backend
    return Path(__file__).resolve().parents[1]


def project_root() -> Path:
    """Repository root (parent of the backend directory) in dev."""
    return backend_root().parent


def app_data_root() -> Path:
    """
    Stable root for user data in frozen mode: LOCALAPPDATA\\Plattera\\Data.
    In dev this is not used for dossiers/PLSS so behavior stays as-is.
    """
    local_appdata = os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
    root = Path(local_appdata) / "Plattera" / "Data"
    root.mkdir(parents=True, exist_ok=True)
    return root


def dossiers_root() -> Path:
    """
    Root for dossiers_data.
    - Dev: backend/dossiers_data (existing layout).
    - Frozen: LOCALAPPDATA\\Plattera\\Data\\dossiers_data.
    """
    if is_frozen():
        root = app_data_root() / "dossiers_data"
    else:
        root = backend_root() / "dossiers_data"
    root.mkdir(parents=True, exist_ok=True)
    return root


def plss_root() -> Path:
    """
    Root for PLSS data.
    - Dev: <project_root>/plss (existing layout).
    - Frozen: LOCALAPPDATA\\Plattera\\Data\\plss.
    """
    if is_frozen():
        root = app_data_root() / "plss"
    else:
        root = project_root() / "plss"
    root.mkdir(parents=True, exist_ok=True)
    return root


# ----- Dossiers: images -----

def dossiers_images_root() -> Path:
    return dossiers_root() / "images"


def dossiers_original_images_root() -> Path:
    return dossiers_images_root() / "original"


def dossiers_processed_images_root() -> Path:
    return dossiers_images_root() / "processed"


# ----- Dossiers: views / runs / drafts -----

def dossiers_views_root() -> Path:
    """Root for dossiers_data/views/transcriptions."""
    return dossiers_root() / "views" / "transcriptions"


def dossier_runs_root(dossier_id: str) -> Path:
    return dossiers_views_root() / str(dossier_id)


def dossier_run_root(dossier_id: str, transcription_id: str) -> Path:
    return dossier_runs_root(dossier_id) / str(transcription_id)


# ----- Dossiers: management / associations / state / navigation -----

def dossiers_management_root() -> Path:
    return dossiers_root() / "management"


def dossiers_associations_root() -> Path:
    return dossiers_root() / "associations"


def dossiers_state_root() -> Path:
    return dossiers_root() / "state"


def dossiers_navigation_root() -> Path:
    return dossiers_root() / "navigation"


# ----- Dossiers: artifacts & processing jobs -----

def dossiers_artifacts_root() -> Path:
    return dossiers_root() / "artifacts"


def dossiers_schemas_artifacts_root(dossier_id: str | None = None) -> Path:
    base = dossiers_artifacts_root() / "schemas"
    return base if dossier_id is None else base / str(dossier_id)


def dossiers_georefs_artifacts_root(dossier_id: str | None = None) -> Path:
    base = dossiers_artifacts_root() / "georefs"
    return base if dossier_id is None else base / str(dossier_id)


def dossiers_processing_jobs_root(job_type: str) -> Path:
    """
    Root for processing jobs under dossiers_data/processing_jobs/<job_type>.
    Example job types: "image_to_text", "text_to_schema".
    """
    return dossiers_root() / "processing_jobs" / job_type


# ----- PLSS helpers -----

def plss_state_root(state: str) -> Path:
    return plss_root() / state.lower()


def plss_fgdb_root(state: str) -> Path:
    return plss_state_root(state) / "fgdb"


def plss_parquet_root(state: str) -> Path:
    return plss_state_root(state) / "parquet"


def plss_index_root(state: str) -> Path:
    return plss_state_root(state) / "index"


