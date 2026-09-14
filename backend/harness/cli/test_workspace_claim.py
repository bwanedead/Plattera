"""Exclusive continuation-claim document must be exact and fail closed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.cli.workspace_claim import (
    acquire_continue_workspace_claim,
    refuse_continue_workspace_busy,
    release_continue_workspace_claim,
)


def _valid_claim(*, workspace_id: str = "source-ws", owner: str = "owner-1") -> dict:
    return {
        "workspace_id": workspace_id,
        "owner_run_id": owner,
        "status": "claimed",
    }


def _write_claim(root: Path, workspace_id: str, payload: object) -> Path:
    path = root / "workspace_claims" / f"{workspace_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if type(payload) is str:
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture
def claim_root(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "cli_runs_root"
    root.mkdir()
    import harness.cli.run_layout as layout_mod

    monkeypatch.setattr(layout_mod, "cli_runs_root", lambda: root)
    return root


def test_malformed_claims_refuse_and_are_not_stolen_or_released(claim_root: Path) -> None:
    cases = [
        {**_valid_claim(), "workspace_id": "other-ws"},
        {**_valid_claim(), "owner_run_id": ""},
        {**_valid_claim(), "owner_run_id": "../x"},
        {**_valid_claim(), "status": "held"},
        {**_valid_claim(), "note": "extra"},
        {**_valid_claim(), "owner_run_id": 12},
        {"workspace_id": "source-ws", "owner_run_id": "owner-1"},
        {"workspace_id": "source-ws", "owner_run_id": "owner-1", "status": True},
    ]
    for index, payload in enumerate(cases):
        path = _write_claim(claim_root, "source-ws", payload)
        before = path.read_bytes()
        busy = refuse_continue_workspace_busy(
            workspace_id="source-ws",
            source_run_id="source-run",
        )
        assert busy == "run_activity_unknown", payload
        assert path.read_bytes() == before
        acquire = acquire_continue_workspace_claim(
            workspace_id="source-ws",
            owner_run_id="new-child",
        )
        assert acquire == "run_activity_unknown", payload
        assert path.read_bytes() == before
        release_continue_workspace_claim(
            workspace_id="source-ws",
            owner_run_id="owner-1",
        )
        assert path.exists()
        assert path.read_bytes() == before
        path.unlink()
        del index
