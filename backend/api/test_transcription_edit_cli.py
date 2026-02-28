from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api import transcription_edit_cli


def test_cli_runs_with_text_file_and_plan(monkeypatch, tmp_path: Path) -> None:
    text_path = tmp_path / "input.txt"
    text_path.write_text("Section one text.", encoding="utf-8")
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "plan_version": "edit_plan_v0",
                "source_transcript_ref": "inline://source_text",
                "source_transcript_hash": "sha256:8f6ca0f35e93f2f3fcfbe07eadaeb2e8f6ed9ba9252f4f5aa07aab4e30dd901f",
                "plan_id": "p1",
                "summary": "s",
                "ops": [],
            }
        ),
        encoding="utf-8",
    )

    captured = {}

    async def _fake_start(req):  # type: ignore[no-untyped-def]
        captured["request"] = req
        return {"run_id": "r1", "status": "running"}

    async def _fake_get(run_id: str):  # type: ignore[no-untyped-def]
        assert run_id == "r1"
        return {"run_id": "r1", "status": "completed", "snapshot": {"status": "completed"}}

    monkeypatch.setattr(transcription_edit_cli.transcription_edit, "start_run", _fake_start)
    monkeypatch.setattr(transcription_edit_cli.transcription_edit, "get_run", _fake_get)

    code = transcription_edit_cli.run_cli(
        [
            "--dossier-id",
            "D1",
            "--text-file",
            str(text_path),
            "--plan-json",
            str(plan_path),
            "--json-only",
        ]
    )
    assert code == 0
    req = captured["request"]
    assert req.start.dossier_id == "D1"
    assert req.start.source_text == "Section one text."
    assert req.plan is not None


def test_cli_returns_nonzero_on_failed_status(monkeypatch) -> None:
    async def _fake_start(req):  # type: ignore[no-untyped-def]
        return {"run_id": "r2", "status": "running"}

    async def _fake_get(run_id: str):  # type: ignore[no-untyped-def]
        return {"run_id": "r2", "status": "failed", "error": "x"}

    monkeypatch.setattr(transcription_edit_cli.transcription_edit, "start_run", _fake_start)
    monkeypatch.setattr(transcription_edit_cli.transcription_edit, "get_run", _fake_get)
    code = transcription_edit_cli.run_cli(["--text", "inline text", "--json-only"])
    assert code == 1


def test_cli_requires_exactly_one_input_source() -> None:
    try:
        transcription_edit_cli.run_cli(["--text", "inline", "--transcript-ref", "a.json"])
        assert False, "Expected SystemExit"
    except SystemExit as exc:
        assert "Provide exactly one source" in str(exc)

