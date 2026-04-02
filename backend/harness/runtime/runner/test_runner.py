from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from harness.runtime.composition import ToolBinding, TurnBlock, TurnSurface
from harness.runtime.runner import RuntimeArtifactTargets, RuntimeRunner, RuntimeRunnerError


@dataclass
class FakeSurfaceAdapter:
    calls: list[dict[str, object]]
    return_value: TurnSurface

    def build_turn_surface(self, launch_context: dict[str, object]) -> TurnSurface:
        self.calls.append(dict(launch_context))
        return self.return_value


def _targets(tmp_path: Path) -> RuntimeArtifactTargets:
    return RuntimeArtifactTargets(done_file=tmp_path / "done.json", result_file=tmp_path / "result.json")


def _surface() -> TurnSurface:
    return TurnSurface(
        surface_id="transcript_edit",
        blocks=(TurnBlock(content="block-1", metadata={"kind": "prompt"}),),
        payload={"transcript_edit": {"startup_inventory": {"scope": {"dossier_id": "d-1"}}}},
        tool_bindings=(ToolBinding(tool_id="load_transcript_edit_startup_inventory", handler=lambda request: request),),
    )


def test_runner_writes_done_and_result_from_surface_only_adapter(tmp_path: Path) -> None:
    adapter = FakeSurfaceAdapter(calls=[], return_value=_surface())
    runner = RuntimeRunner(adapter=adapter, targets=_targets(tmp_path))

    result = runner.run(launch_context={"opaque": True})

    assert result.status == "completed"
    assert result.reason_code == "turn_surface_composed"
    assert adapter.calls == [{"opaque": True}]
    assert json.loads((tmp_path / "result.json").read_text(encoding="utf-8")) == {
        "mechanical_surface": {
            "blocks": [{"content": "block-1", "metadata": {"kind": "prompt"}}],
            "payload": {"transcript_edit": {"startup_inventory": {"scope": {"dossier_id": "d-1"}}}},
            "surface_id": "transcript_edit",
            "tool_ids": ["load_transcript_edit_startup_inventory"],
        },
        "mechanical_turn_input": {
            "block_count": 1,
            "blocks": [{"content": "block-1", "metadata": {"kind": "prompt"}}],
            "surface_payloads": {
                "transcript_edit": {"transcript_edit": {"startup_inventory": {"scope": {"dossier_id": "d-1"}}}}
            },
            "tool_ids": ["load_transcript_edit_startup_inventory"],
        },
        "reason_code": "turn_surface_composed",
        "status": "completed",
    }
    assert json.loads((tmp_path / "done.json").read_text(encoding="utf-8")) == {
        "mechanical_surface": {
            "blocks": [{"content": "block-1", "metadata": {"kind": "prompt"}}],
            "payload": {"transcript_edit": {"startup_inventory": {"scope": {"dossier_id": "d-1"}}}},
            "surface_id": "transcript_edit",
            "tool_ids": ["load_transcript_edit_startup_inventory"],
        },
        "mechanical_turn_input": {
            "block_count": 1,
            "surface_ids": ["transcript_edit"],
            "tool_ids": ["load_transcript_edit_startup_inventory"],
        },
        "reason_code": "turn_surface_composed",
        "status": "completed",
    }


def test_runner_uses_factory_before_loader_and_resolves_launch_context(tmp_path: Path) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def factory(launch_context: dict[str, object]) -> FakeSurfaceAdapter:
        calls.append(("factory", dict(launch_context)))
        return FakeSurfaceAdapter(calls=[], return_value=_surface())

    def loader(_: dict[str, object]) -> object:
        calls.append(("loader", {}))
        raise AssertionError("loader should not run when factory is provided")

    runner = RuntimeRunner(adapter_factory=factory, adapter_loader=loader, targets=_targets(tmp_path))

    result = runner.run(launch_context={"seed": "x"})

    assert result.status == "completed"
    assert calls == [("factory", {"seed": "x"})]
    assert json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))["mechanical_surface"]["surface_id"] == "transcript_edit"


def test_runner_writes_failure_artifacts_when_adapter_raises(tmp_path: Path) -> None:
    class ExplodingAdapter:
        def build_turn_surface(self, launch_context: dict[str, object]) -> TurnSurface:
            raise ValueError("boom")

    runner = RuntimeRunner(adapter=ExplodingAdapter(), targets=_targets(tmp_path))

    with pytest.raises(RuntimeRunnerError):
        runner.run(launch_context={"opaque": "context"})

    assert json.loads((tmp_path / "result.json").read_text(encoding="utf-8")) == {
        "error": "boom",
        "reason_code": "runner_exception",
        "status": "failed",
    }
    assert json.loads((tmp_path / "done.json").read_text(encoding="utf-8")) == {
        "error": "boom",
        "reason_code": "runner_exception",
        "status": "failed",
    }


def test_runner_reads_targets_from_env_when_not_explicitly_provided(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HARNESS_CLI_DONE_FILE", str(tmp_path / "env-done.json"))
    monkeypatch.setenv("HARNESS_CLI_RESULT_FILE", str(tmp_path / "env-result.json"))

    adapter = FakeSurfaceAdapter(calls=[], return_value=_surface())
    runner = RuntimeRunner(adapter=adapter)

    result = runner.run(launch_context={"opaque": "yes"})

    assert result.status == "completed"
    assert json.loads((tmp_path / "env-result.json").read_text(encoding="utf-8"))["mechanical_surface"]["surface_id"] == "transcript_edit"
    assert json.loads((tmp_path / "env-done.json").read_text(encoding="utf-8"))["mechanical_turn_input"]["surface_ids"] == ["transcript_edit"]
