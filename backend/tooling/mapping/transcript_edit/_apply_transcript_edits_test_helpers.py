"""Shared fixtures for apply_transcript_edits offline acceptance suites."""

from __future__ import annotations

import json
from pathlib import Path

import config.paths as paths_mod

from tooling.mapping.transcript_edit.draft_persistence import save_transcript_edit


def root(tmp_path: Path, monkeypatch) -> Path:
    dossiers = tmp_path / "dossiers_data"
    dossiers.mkdir(parents=True)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: dossiers)
    return dossiers


def seed_run(root_path: Path, dossier_id: str, transcription_id: str) -> None:
    run = root_path / "views" / "transcriptions" / dossier_id / transcription_id
    raw = run / "raw"
    raw.mkdir(parents=True)
    (raw / "peer_a.json").write_text(json.dumps({"sections": []}), encoding="utf-8")
    (run / "run.json").write_text(
        json.dumps({"completed_drafts": ["peer_a"]}),
        encoding="utf-8",
    )


def save_base(
    *,
    d: str,
    tx: str,
    ws: str,
    source: str,
    normalized: str | None = None,
    extra: dict | None = None,
    evidence_refs: list[str] | None = None,
) -> dict:
    payload = {
        "source_transcript_verbatim": source,
        "issues": [{"id": "keep-me"}],
        "parcel_metadata": {"parcel_count": 1},
    }
    if normalized is not None:
        payload["normalized_or_mapping_transcript"] = normalized
    if extra:
        payload.update(extra)
    return save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload=payload,
        evidence_refs=evidence_refs or [],
    )


def decision(
    *,
    decision_id: str = "d1",
    determination: str = "provisional",
    basis: str = "basis text",
    evidence_refs: list[str] | None = None,
    candidate_values: list[str] | None = None,
    uncertainty_reasons: list[str] | None = None,
    edits: list[dict] | None = None,
) -> dict:
    if uncertainty_reasons is None:
        if determination == "earned":
            uncertainty_reasons = []
        else:
            uncertainty_reasons = ["source_ambiguous"]
    body: dict = {
        "decision_id": decision_id,
        "determination": determination,
        "uncertainty_reasons": list(uncertainty_reasons),
        "verification_basis": basis,
        "evidence_refs": evidence_refs if evidence_refs is not None else [],
        "edits": edits
        or [
            {
                "lane": "source_transcript_verbatim",
                "expected_text": "Range 7 west",
                "replacement_text": "Range 77 west",
            }
        ],
    }
    if candidate_values is not None:
        body["candidate_values"] = candidate_values
    return body
