from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.transcription_edit_loop.contracts import TranscriptDocumentV0, TranscriptSectionV0
from backend.transcription_edit_loop.validators import run_validators


def test_run_validators_accepts_canonical_degree_minute_bearing_format() -> None:
    doc = TranscriptDocumentV0(
        source_transcript_ref="artifact://bearing",
        sections=[
            TranscriptSectionV0(
                id="s1",
                body=(
                    "Beginning at a point; whence the northwest corner bears N. 4°00' W., 1638 feet distant; "
                    "thence N. 18°30' East 542 feet more or less to the point of beginning."
                ),
            )
        ],
    )
    report = run_validators(document=doc, source_transcript_ref="artifact://bearing")
    finding_ids = {finding.finding_id for finding in report.findings}
    assert "bearing_missing_001" not in finding_ids

