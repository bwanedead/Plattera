"""Phase 25: closure/reporting vocabulary and evidence helpers (no validator taxonomy runtime)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.domains.mapping.transcript_edit.context_spans import fallback_spans_for_findings
from backend.domains.mapping.transcript_edit.decision_ledger_closure import closure_state_from_layers, derive_layer_statuses
from backend.domains.mapping.transcript_edit.focus_runtime import decision_key_for_finding


def test_derive_layer_statuses_uses_mechanical_severity_clear_not_validator_language() -> None:
    s_ok = derive_layer_statuses(
        mapping_ready=False,
        mechanical_severity_clear=True,
        readiness_blocker=None,
    )
    assert s_ok["layer1_canonical_recovery"] == "unknown"
    s_blocked = derive_layer_statuses(
        mapping_ready=False,
        mechanical_severity_clear=False,
        readiness_blocker=None,
    )
    assert s_blocked["layer1_canonical_recovery"] == "blocked"
    assert closure_state_from_layers(s_ok) == "blocked"


def test_decision_key_for_finding_prefers_explicit_keys() -> None:
    assert (
        decision_key_for_finding(
            {"message": "unrelated noise", "suggested_decision_key": "section"}
        )
        == "section"
    )


@patch(
    "backend.domains.mapping.transcript_edit.context_spans.load_transcript_text_for_seeds",
    return_value=(
        "Preamble text. Range seventy-four (74) West appears here. "
        "More deed language for window search."
    ),
)
def test_fallback_spans_do_not_require_finding_type(_mock_load: object) -> None:
    spans = fallback_spans_for_findings(
        source_transcript_ref="in-memory://fixture.txt",
        top_findings=[
            {"message": "Range contradiction between Range 75 West and Range 74 West in the description."},
        ],
    )
    assert isinstance(spans, list) and len(spans) >= 1

