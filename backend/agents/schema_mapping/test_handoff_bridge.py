from __future__ import annotations

import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.schema_mapping.handoff_bridge import (
    handoff_bootstrap_metadata,
    maybe_build_upstream_correction_request,
    persist_upstream_correction_requests,
)


def test_handoff_bootstrap_metadata_maps_readiness_and_watchlist() -> None:
    packet = {
        "terminal": {"mapping_ready": False, "readiness_blocker": "range_mismatch"},
        "resume_recommendation": "proceed_with_caution",
        "handoff_summary": "Not mapping-ready.",
        "mapping_watchlist": ["range", "tie_bearing"],
        "transcript_edit_run_id": "tx_run_1",
    }
    out = handoff_bootstrap_metadata(packet)
    assert out["transcript_mapping_ready"] is False
    assert out["transcript_resume_recommendation"] == "proceed_with_caution"
    assert out["transcript_mapping_watchlist"] == ["range", "tie_bearing"]


def test_maybe_build_upstream_correction_request_from_mapping_failure() -> None:
    req = maybe_build_upstream_correction_request(
        run_id="run_1",
        handoff_packet={"mapping_watchlist": ["range"]},
        event={
            "payload": {
                "action_type": "georeference",
                "execution_state": "refused",
                "refusal": {"reason_code": "georef_range_bearing_mismatch"},
                "latest_refs": {"judge_ref": "artifacts/feature_graphs/D1/judge.json"},
            },
            "timestamp_epoch_seconds": 123,
        },
    )
    assert isinstance(req, dict)
    assert req["source"] == "mapping"
    assert "range" in req["decision_keys"]
    assert req["severity"] == "blocking"


def test_persist_upstream_correction_requests_writes_artifact() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "artifacts"
        import backend.agents.schema_mapping.handoff_bridge as hb

        original = hb.dossiers_artifacts_root
        try:
            hb.dossiers_artifacts_root = lambda: root  # type: ignore[assignment]
            ref = persist_upstream_correction_requests(
                run_id="run_1",
                dossier_id="D1",
                requests=[{"request_id": "r1"}],
            )
            assert ref is not None
            path = Path(ref)
            assert path.exists()
            assert "mapping_upstream_requests" in str(path)
        finally:
            hb.dossiers_artifacts_root = original  # type: ignore[assignment]
