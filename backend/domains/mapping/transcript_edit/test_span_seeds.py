from __future__ import annotations

from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.tooling.mapping.transcription_edit.span_seeds import (
    build_transcript_span_seeds_artifact,
    load_transcript_text_for_seeds,
)


def test_build_transcript_span_seeds_artifact_is_bounded_and_anchored() -> None:
    text = (
        "Beginning at the NW corner of Section 2.\n\n"
        "Thence east 100 feet.\n\n"
        "Excepting and reserving one acre."
    )
    artifact = build_transcript_span_seeds_artifact(
        dossier_id="D1",
        source_transcript_ref="artifacts/tx/source.json",
        source_transcript_hash="sha256:abc123",
        transcript_text=text,
        max_seeds=10,
    )
    assert artifact.artifact_type == "transcript_span_seeds_v1"
    assert len(artifact.seeds) <= 10
    assert artifact.seeds
    assert all(seed.locator.locator_type == "anchors" for seed in artifact.seeds)


def test_load_transcript_text_for_seeds_reads_sections(tmp_path: Path) -> None:
    path = tmp_path / "tx.json"
    path.write_text(
        json.dumps({"sections": [{"id": "s1", "body": "Beginning at point A."}, {"id": "s2", "body": "Thence B."}]}),
        encoding="utf-8",
    )
    text = load_transcript_text_for_seeds(str(path))
    assert text == "Beginning at point A.\n\nThence B."


