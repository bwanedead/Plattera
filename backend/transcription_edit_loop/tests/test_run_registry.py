from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.transcription_edit_loop import run_registry as run_registry_module
from backend.transcription_edit_loop.run_registry import TranscriptionEditRunRegistry


def test_atomic_write_retries_transient_replace_failures_then_succeeds(tmp_path: Path, monkeypatch) -> None:
    registry = TranscriptionEditRunRegistry(state_dir=tmp_path)
    target = tmp_path / "index.json"
    original_replace = run_registry_module.os.replace
    attempts = {"count": 0}

    def _flaky_replace(src: str, dst: str) -> None:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise PermissionError(13, "Access is denied")
        original_replace(src, dst)

    monkeypatch.setattr(run_registry_module.os, "replace", _flaky_replace)
    monkeypatch.setattr(run_registry_module.time, "sleep", lambda _seconds: None)

    registry._atomic_write(target, {"runs": [{"run_id": "r1"}]})
    assert attempts["count"] == 2
    assert target.exists()


def test_atomic_write_raises_after_retry_exhaustion(tmp_path: Path, monkeypatch) -> None:
    registry = TranscriptionEditRunRegistry(state_dir=tmp_path)
    target = tmp_path / "index.json"

    def _always_fail(_src: str, _dst: str) -> None:
        raise PermissionError(13, "Access is denied")

    monkeypatch.setattr(run_registry_module.os, "replace", _always_fail)
    monkeypatch.setattr(run_registry_module.time, "sleep", lambda _seconds: None)

    with pytest.raises(PermissionError):
        registry._atomic_write(target, {"runs": [{"run_id": "r1"}]})

