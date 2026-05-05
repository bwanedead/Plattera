from __future__ import annotations

import json
from pathlib import Path

from harness.runtime.runner import RuntimeRunResult
from harness.runtime.runner import entrypoint


def test_entrypoint_loads_fake_factory_module(tmp_path: Path, monkeypatch) -> None:
    module_path = tmp_path / "fake_factory_mod.py"
    module_path.write_text(
        """
from dataclasses import dataclass

from harness.runtime.composition import TurnBlock, TurnSurface


@dataclass
class FakeAdapter:
    domain_id: str
    calls: list[dict[str, object]]

    def build_turn_surface(self, launch_context):
        self.calls.append(dict(launch_context))
        return TurnSurface(
            surface_id=self.domain_id,
            blocks=(TurnBlock(content="fake-block", metadata={}),),
            payload={"domain_id": self.domain_id},
            tool_bindings=(),
        )


def build_fake_domain_adapter_factory(domain_id):
    def factory():
        return FakeAdapter(domain_id=domain_id, calls=[])

    return factory
""",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    captured: dict[str, object] = {}

    def fake_run_runtime_from_env(*, adapter_factory=None, adapter_loader=None, opaque_launch_context=None):
        assert adapter_loader is None
        captured["launch_context"] = dict(opaque_launch_context or {})
        adapter = adapter_factory(opaque_launch_context or {})
        surface = adapter.build_turn_surface(opaque_launch_context or {})
        captured["surface_id"] = surface.surface_id
        captured["surface_payload"] = dict(surface.payload)
        return RuntimeRunResult(status="completed", reason_code="ok")

    monkeypatch.setattr(entrypoint, "run_runtime_from_env", fake_run_runtime_from_env)

    result = entrypoint.main(
        [
            "--domain-id",
            "fake_domain",
            "--launch-context-json",
            json.dumps({"seed": "alpha"}),
            "--adapter-factory-ref",
            "fake_factory_mod:build_fake_domain_adapter_factory",
        ]
    )

    assert result.status == "completed"
    assert captured["launch_context"] == {"seed": "alpha"}
    assert captured["surface_id"] == "fake_domain"
    assert captured["surface_payload"] == {"domain_id": "fake_domain"}


def test_entrypoint_resolves_transcript_edit_through_opaque_domain_id(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_run_runtime_from_env(*, adapter_factory=None, adapter_loader=None, opaque_launch_context=None):
        assert adapter_loader is None
        launch_context = dict(opaque_launch_context or {})
        captured["launch_context"] = launch_context
        adapter = adapter_factory(launch_context)
        surface = adapter.build_turn_surface(launch_context)
        captured["surface"] = surface
        return RuntimeRunResult(status="completed", reason_code="ok")

    monkeypatch.setattr(entrypoint, "run_runtime_from_env", fake_run_runtime_from_env)

    result = entrypoint.main(
        [
            "--domain-id",
            "transcript_edit",
            "--launch-context-json",
            json.dumps(
                {
                    "dossier_id": "dossier-1",
                    "transcription_id": "tx-1",
                    "segment_id": "seg-1",
                    "run_id": "run-1",
                }
            ),
        ]
    )

    capsys.readouterr()
    assert result.status == "completed"
    surface = captured["surface"]
    assert surface.surface_id == "transcript_edit"
    assert surface.payload["transcript_edit"]["tool_ids"] == [
        "hydrate_artifact_refs",
        "transform_artifact",
        "save_workspace_artifact",
        "copy_forward_save_workspace_artifact",
        "publish_workspace_artifact",
    ]
    assert surface.payload["transcript_edit"]["tool_specs"][0]["tool_id"] == "hydrate_artifact_refs"
    assert surface.payload["transcript_edit"]["tool_specs"][0]["purpose"].startswith(
        "Load full content for one or more artifact refs."
    )
