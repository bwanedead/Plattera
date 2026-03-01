from __future__ import annotations

import json
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent_kernel.tooling import TranscriptSpanOpenerTool


def test_tx_open_transcript_spans_supports_offsets_and_anchors() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "transcript.json"
        payload = {
            "sections": [
                {"id": "s1", "body": "Beginning at NW corner."},
                {"id": "s2", "body": "Thence east 100 feet to point of beginning."},
            ]
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

        tool = TranscriptSpanOpenerTool()
        by_offsets = tool.open_transcript_spans(
            {
                "dossier_id": "D1",
                "source_transcript_ref": str(path),
                "spans": [{"span_id": "a", "start_char": 0, "end_char": 20}],
            }
        )
        assert by_offsets["reason_codes"] == ["tx_spans_opened"]
        artifact_ref = by_offsets.get("artifact_ref")
        assert artifact_ref is not None
        artifact_path = (
            artifact_ref.get("artifact_path")
            if isinstance(artifact_ref, dict)
            else getattr(artifact_ref, "artifact_path", None)
        )
        assert isinstance(artifact_path, str)
        assert Path(artifact_path).exists()
        spans = by_offsets["spans"]
        assert isinstance(spans, list) and spans
        assert "Beginning at" in spans[0]["text"]

        by_anchors = tool.open_transcript_spans(
            {
                "source_transcript_ref": str(path),
                "anchors": [{"span_id": "b", "start_anchor": "Beginning at", "end_anchor": "point of beginning"}],
            }
        )
        assert by_anchors["reason_codes"] == ["tx_spans_opened"]
        spans2 = by_anchors["spans"]
        assert isinstance(spans2, list) and spans2
        assert "point of beginning" in spans2[0]["text"]
