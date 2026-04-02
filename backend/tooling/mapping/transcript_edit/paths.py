"""Path helpers for dossier transcription runs (tooling-internal)."""

from __future__ import annotations

from pathlib import Path

from config.paths import dossier_run_root, dossiers_root


def transcription_run_dir(dossier_id: str, transcription_id: str) -> Path:
    return dossier_run_root(str(dossier_id).strip(), str(transcription_id).strip())


def run_json_path(dossier_id: str, transcription_id: str) -> Path:
    return transcription_run_dir(dossier_id, transcription_id) / "run.json"


def raw_drafts_dir(dossier_id: str, transcription_id: str) -> Path:
    return transcription_run_dir(dossier_id, transcription_id) / "raw"


def transcript_edit_dir(dossier_id: str, transcription_id: str) -> Path:
    """Convention: authored transcript-edit artifacts live here (not T0 raw/)."""
    return transcription_run_dir(dossier_id, transcription_id) / "transcript_edit"


def association_path(dossier_id: str) -> Path:
    return dossiers_root() / "associations" / f"assoc_{str(dossier_id).strip()}.json"
