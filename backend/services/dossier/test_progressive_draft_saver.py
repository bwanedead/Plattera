from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.services.dossier.progressive_draft_saver import ProgressiveDraftSaver


def test_prepare_draft_content_prefers_explicit_mode_and_model() -> None:
    saver = ProgressiveDraftSaver()
    content = saver._prepare_draft_content(  # type: ignore[attr-defined]
        result={
            "success": True,
            "extracted_text": '{"documentId":"d1","sections":[{"id":1,"body":"text"}]}',
            "model_used": "from_result",
            "metadata": {
                "json_extraction": {"mode": "relaxed"},
            },
        },
        draft_index=0,
        extraction_mode_used="legal_document_json_relaxed",
        model_used="from_callback",
    )
    assert content["_extraction_mode_used"] == "legal_document_json_relaxed"
    assert content["_model_used"] == "from_callback"

