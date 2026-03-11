from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.convention_situating import situate_document_convention


def test_situate_document_convention_detects_plss() -> None:
    result = situate_document_convention(
        orient_items=[
            {"key": "township", "selected_value": "Township 110 North"},
            {"key": "range", "selected_value": "Range 75 West"},
            {"key": "section", "selected_value": "Section 12"},
        ]
    )
    assert str(result.get("document_convention") or "") == "plss"
    assert float(result.get("convention_confidence") or 0) >= 0.5
    candidates = [str(v) for v in list(result.get("menu_family_candidates") or [])]
    assert "plss" in candidates


def test_situate_document_convention_detects_hybrid_when_signal_scores_tie() -> None:
    result = situate_document_convention(
        orient_items=[
            {"key": "range", "selected_value": "Range 75 West"},
            {"key": "tie_bearing", "required_information": "Thence North 45 degrees East 120 feet"},
            {"key": "closure_or_pob", "minimal_user_action": "Confirm point of beginning."},
        ]
    )
    assert str(result.get("document_convention") or "") in {"hybrid", "metes_and_bounds", "plss"}
    signals = result.get("convention_signals")
    assert isinstance(signals, list)
