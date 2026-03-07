from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api import transcript_edit_agent_cli


def test_cli_runs_and_prints_snapshot(monkeypatch, tmp_path, capsys) -> None:
    text_path = tmp_path / "tx.txt"
    text_path.write_text("Beginning at a point ...", encoding="utf-8")
    captured: dict[str, Any] = {}

    async def _fake_start(request):
        captured["request"] = request
        return {"run_id": "tx_run_1", "status": "running"}

    async def _fake_get(run_id: str):
        return {"run_id": run_id, "status": "completed", "snapshot": {"status": "completed", "reason_code": "ok"}}

    monkeypatch.setattr(transcript_edit_agent_cli.transcript_edit_agent, "start_run", _fake_start)
    monkeypatch.setattr(transcript_edit_agent_cli.transcript_edit_agent, "get_run", _fake_get)

    code = transcript_edit_agent_cli.run_cli(["--text-file", str(text_path), "--json-only"])
    assert code == 0
    assert captured["request"].source_text.startswith("Beginning at")
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "completed"


def test_cli_nonzero_for_failed(monkeypatch) -> None:
    async def _fake_start(request):
        del request
        return {"run_id": "tx_run_2", "status": "running"}

    async def _fake_get(run_id: str):
        return {"run_id": run_id, "status": "failed", "error": "boom"}

    monkeypatch.setattr(transcript_edit_agent_cli.transcript_edit_agent, "start_run", _fake_start)
    monkeypatch.setattr(transcript_edit_agent_cli.transcript_edit_agent, "get_run", _fake_get)

    code = transcript_edit_agent_cli.run_cli(["--text", "x", "--json-only"])
    assert code == 1


def test_cli_exits_for_waiting_feedback_with_distinct_code_and_pause_message(monkeypatch, capsys) -> None:
    async def _fake_start(request):
        del request
        return {"run_id": "tx_run_wait", "status": "running"}

    async def _fake_get(run_id: str):
        return {
            "run_id": run_id,
            "status": "waiting_feedback",
            "snapshot": {
                "status": "waiting_feedback",
                "live_status": {
                    "phase": "human_feedback_needed",
                    "iteration": 2,
                    "message": "Waiting for human feedback while continuing other checks.",
                    "elapsed_ms": 12345,
                },
            },
        }

    monkeypatch.setattr(transcript_edit_agent_cli.transcript_edit_agent, "start_run", _fake_start)
    monkeypatch.setattr(transcript_edit_agent_cli.transcript_edit_agent, "get_run", _fake_get)

    code = transcript_edit_agent_cli.run_cli(["--text", "x"])
    out = capsys.readouterr().out
    assert code == 3
    assert "phase=human_feedback_needed" in out
    assert "paused: waiting for human feedback" in out


def test_cli_waiting_feedback_unicode_output_does_not_crash(monkeypatch, capsys) -> None:
    async def _fake_start(request):
        del request
        return {"run_id": "tx_run_wait_unicode", "status": "running"}

    async def _fake_get(run_id: str):
        return {
            "run_id": run_id,
            "status": "waiting_feedback",
            "snapshot": {
                "status": "waiting_feedback",
                "live_status": {
                    "phase": "human_feedback_needed",
                    "iteration": 1,
                    "message": "Bearing token includes 4° 00′ W.",
                    "elapsed_ms": 1200,
                },
            },
        }

    monkeypatch.setattr(transcript_edit_agent_cli.transcript_edit_agent, "start_run", _fake_start)
    monkeypatch.setattr(transcript_edit_agent_cli.transcript_edit_agent, "get_run", _fake_get)
    code = transcript_edit_agent_cli.run_cli(["--text", "x"])
    out = capsys.readouterr().out
    assert code == 3
    assert "waiting for human feedback" in out
