from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.endpoints import processing


def test_relaxed_json_metrics_rollup_filters_and_rates(tmp_path: Path, monkeypatch) -> None:
    artifacts_root = tmp_path / "dossiers_data" / "artifacts"
    tx_root = artifacts_root / "transcription_edit" / "D1"
    tx_root.mkdir(parents=True, exist_ok=True)
    (tx_root / "json_extraction_metric_1.json").write_text(
        json.dumps(
            {
                "mode": "relaxed",
                "model": "gpt-4o",
                "validation_passed": True,
                "repair_invoked": False,
                "recovered": True,
                "created_at": "2026-02-27T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (tx_root / "json_extraction_metric_2.json").write_text(
        json.dumps(
            {
                "mode": "relaxed",
                "model": "gpt-4o",
                "validation_passed": False,
                "repair_invoked": True,
                "recovered": False,
                "created_at": "2026-02-27T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (tx_root / "json_extraction_metric_3.json").write_text(
        json.dumps(
            {
                "mode": "strict",
                "model": "gpt-4o",
                "validation_passed": True,
                "repair_invoked": False,
                "recovered": True,
                "created_at": "2026-02-27T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(processing, "dossiers_artifacts_root", lambda: artifacts_root)

    out = __import__("asyncio").run(processing.get_relaxed_json_metrics(days=365, model="gpt-4o"))
    assert out["status"] == "success"
    assert out["sample_count"] == 2
    assert out["validation_pass_rate"] == 0.5
    assert out["repair_invocation_rate"] == 0.5
    assert out["unrecoverable_failure_rate"] == 0.5
    assert "gpt-4o" in out["by_model"]

