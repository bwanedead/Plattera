from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api import agent_loop_cli


def test_cli_runs_endpoint_path_and_prints_final_snapshot(monkeypatch, tmp_path) -> None:
    text_path = tmp_path / "deed.txt"
    text_path.write_text("Example deed text body.", encoding="utf-8")
    captured: dict[str, Any] = {}

    async def _fake_start(request):
        captured["request"] = request
        return {"run_id": "run_cli_1", "status": "running", "dossier_id": "D123"}

    async def _fake_get(run_id: str):
        assert run_id == "run_cli_1"
        return {
            "run_id": run_id,
            "status": "completed",
            "session_id": "s1",
            "terminal": {"success": True, "terminal_outcome": "SUCCESS"},
        }

    monkeypatch.setattr(agent_loop_cli.agent_loop, "start_agent_loop_run", _fake_start)
    monkeypatch.setattr(agent_loop_cli.agent_loop, "get_agent_loop_run", _fake_get)

    code = agent_loop_cli.run_cli(
        [
            "--text-file",
            str(text_path),
            "--model",
            "gpt-5.2",
            "--max-iterations",
            "7",
            "--json-only",
        ]
    )

    assert code == 0
    req = captured["request"]
    assert req.background is True
    assert req.model == "gpt-5.2"
    assert req.max_iterations == 7
    assert req.text == "Example deed text body."
    assert req.requires_global_placement is True
    assert req.render_required is True


def test_cli_returns_nonzero_for_failed_run(monkeypatch, capsys) -> None:
    async def _fake_start(request):
        del request
        return {"run_id": "run_cli_2", "status": "running"}

    async def _fake_get(run_id: str):
        return {"run_id": run_id, "status": "failed", "error": "boom"}

    monkeypatch.setattr(agent_loop_cli.agent_loop, "start_agent_loop_run", _fake_start)
    monkeypatch.setattr(agent_loop_cli.agent_loop, "get_agent_loop_run", _fake_get)

    code = agent_loop_cli.run_cli(["--text", "x", "--json-only"])
    assert code == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"


def test_cli_selects_right_of_way_from_canonical_finalized_index(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        agent_loop_cli,
        "_load_finalized_index_entries",
        lambda: [
            {
                "dossier_id": "6a3a833c-e055-493d-8dd4-06b0f615a151",
                "title": "Right of Way Deed",
                "latest_generated_at": "2025-11-06T22:48:43.906439",
                "has_errors": False,
            }
        ],
    )

    async def _fake_start(request):
        captured["request"] = request
        return {"run_id": "run_cli_row", "status": "running"}

    async def _fake_get(run_id: str):
        return {"run_id": run_id, "status": "completed", "terminal": {"success": True}}

    monkeypatch.setattr(agent_loop_cli.agent_loop, "start_agent_loop_run", _fake_start)
    monkeypatch.setattr(agent_loop_cli.agent_loop, "get_agent_loop_run", _fake_get)

    code = agent_loop_cli.run_cli(["--right-of-way", "--json-only"])
    assert code == 0
    assert captured["request"].dossier_id == "6a3a833c-e055-493d-8dd4-06b0f615a151"
    assert captured["request"].requires_global_placement is True
    assert captured["request"].render_required is True


def test_cli_can_explicitly_disable_mapping_requirements(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def _fake_start(request):
        captured["request"] = request
        return {"run_id": "run_cli_flags", "status": "running"}

    async def _fake_get(run_id: str):
        return {"run_id": run_id, "status": "completed", "terminal": {"success": True}}

    monkeypatch.setattr(agent_loop_cli.agent_loop, "start_agent_loop_run", _fake_start)
    monkeypatch.setattr(agent_loop_cli.agent_loop, "get_agent_loop_run", _fake_get)

    code = agent_loop_cli.run_cli(
        ["--text", "deed body", "--no-global-placement", "--no-render-required", "--json-only"]
    )
    assert code == 0
    assert captured["request"].requires_global_placement is False
    assert captured["request"].render_required is False


def test_cli_lists_canonical_finalized_dossiers(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        agent_loop_cli,
        "_load_finalized_index_entries",
        lambda: [
            {
                "dossier_id": "D1",
                "title": "Right of Way Deed",
                "latest_generated_at": "2025-11-06T22:48:43.906439",
                "has_errors": False,
            },
            {
                "dossier_id": "D2",
                "title": "Other Finalized Deed",
                "latest_generated_at": "2025-10-17T23:00:15.386466",
                "has_errors": False,
            },
        ],
    )

    code = agent_loop_cli.run_cli(["--list-finalized"])
    assert code == 0

    out = capsys.readouterr().out
    assert "Canonical finalized dossiers:" in out
    assert "Right of Way Deed" in out
    assert "dossier_id=D1" in out
