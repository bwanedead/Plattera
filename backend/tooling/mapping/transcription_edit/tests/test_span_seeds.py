from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from backend.tooling.mapping.transcription_edit.contracts import (
    Confidence,
    LocatorAnchorsV0,
    TranscriptSpanSeedLabel,
    TranscriptSpanSeedOrigin,
    TranscriptSpanSeedsArtifactV1,
    TranscriptSpanSeedV1,
)
from backend.services.workflows.mapping.transcription_edit.persistence import TranscriptionEditPersistenceService


def test_save_transcript_span_seeds_writes_artifact_and_latest_pointer(tmp_path: Path) -> None:
    svc = TranscriptionEditPersistenceService(root=tmp_path / "tx")
    artifact = TranscriptSpanSeedsArtifactV1(
        created_at="2026-01-01T00:00:00Z",
        dossier_id="D1",
        source_transcript_ref="artifacts/tx/source.json",
        source_transcript_hash="sha256:abc123",
        seeds=[
            TranscriptSpanSeedV1(
                seed_id="seed_pob_01",
                label=TranscriptSpanSeedLabel.POB,
                seed_origin=TranscriptSpanSeedOrigin.HYBRID,
                seed_confidence=Confidence.HIGH,
                locator=LocatorAnchorsV0(
                    start_anchor="Beginning at a point",
                    end_anchor="to the point of beginning",
                    occurrence=1,
                ),
            )
        ],
    )
    ref = svc.save_transcript_span_seeds(dossier_id="D1", artifact=artifact)
    ref_path = Path(ref)
    assert ref_path.exists()
    payload = json.loads(ref_path.read_text(encoding="utf-8"))
    assert payload["artifact_type"] == "transcript_span_seeds_v1"
    assert len(payload["seeds"]) == 1
    pointer = ref_path.parent / "latest_transcript_span_seeds.json"
    assert pointer.exists()
    pointer_payload = json.loads(pointer.read_text(encoding="utf-8"))
    assert pointer_payload["seeds_ref"] == str(ref_path)
    assert pointer_payload["source_transcript_hash"] == "sha256:abc123"




