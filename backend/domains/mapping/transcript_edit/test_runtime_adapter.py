from __future__ import annotations

from dataclasses import dataclass

from domains.mapping.transcript_edit.runtime_adapter import composition as runtime_composition
from domains.mapping.transcript_edit.execution.tool_specs import build_transcript_edit_tool_specs
from domains.mapping.transcript_edit.runtime_adapter import build_transcript_edit_runtime_adapter
from harness.execution.contracts import ExecutionStepRequest
from harness.execution.executor import ExecutionExecutor
from harness.runtime.composition import TurnSurface


def test_runtime_adapter_builds_turn_surface_from_opaque_launch_context() -> None:
    adapter = build_transcript_edit_runtime_adapter()

    surface = adapter.build_turn_surface(
        {
            "dossier_id": "dossier-1",
            "transcription_id": "tx-1",
            "segment_id": "seg-1",
            "run_id": "run-1",
        }
    )

    assert isinstance(surface, TurnSurface)
    assert surface.surface_id == "transcript_edit"
    assert len(surface.blocks) == 2
    assert surface.blocks[0].content.startswith("You are operating in the **transcript edit** domain")
    assert "not a hard script" in surface.blocks[1].content.lower()
    assert surface.payload["transcript_edit"]["startup_inventory"]["scope"] == {
        "dossier_id": "dossier-1",
        "transcription_id": "tx-1",
        "segment_id": "seg-1",
        "run_id": "run-1",
    }
    assert surface.payload["transcript_edit"]["tool_ids"] == [
        "load_transcript_edit_startup_inventory",
        "hydrate_t0_draft_refs",
        "hydrate_transcript_edit_working_draft",
        "load_source_image_context",
    ]
    tool_specs = surface.payload["transcript_edit"]["tool_specs"]
    assert len(tool_specs) == len(build_transcript_edit_tool_specs())
    assert tool_specs[0] == {
        "tool_id": "load_transcript_edit_startup_inventory",
        "category": "observation",
        "purpose": "First-contact ref inventory: dossier scope, peer T0 draft refs, source image refs, transcript-edit draft refs, lightweight metadata only.",
        "expected_request_shape": "dossier_id, transcription_id; optional segment_id, run_id.",
        "expected_result_shape": "TranscriptEditStartupInventory: refs + descriptors; no full draft bodies; structured missing_resource entries if gaps.",
    }
    assert [binding.tool_id for binding in surface.tool_bindings] == [
        "load_transcript_edit_startup_inventory",
        "hydrate_t0_draft_refs",
        "hydrate_transcript_edit_working_draft",
        "load_source_image_context",
    ]


def test_runtime_adapter_factory_returns_thin_domain_owned_adapter() -> None:
    adapter = build_transcript_edit_runtime_adapter()

    assert adapter.domain_id == "transcript_edit"
    assert adapter.manifest.domain_id == "transcript_edit"


def test_transcript_edit_tool_binding_accepts_execution_request_inputs(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_tool(**kwargs):
        seen["kwargs"] = dict(kwargs)
        return {
            "executed": True,
            "outputs": {"ok": True},
            "artifact_refs": ["artifact://ok"],
        }

    monkeypatch.setattr(runtime_composition, "build_transcript_edit_startup_inventory", fake_tool)

    binding = runtime_composition.build_transcript_edit_tool_bindings()[0]
    executor = ExecutionExecutor()
    executor.register(binding.tool_id, binding.handler)

    result = executor.execute(
        ExecutionStepRequest(
            session_id="session-1",
            action_id=binding.tool_id,
            inputs={
                "dossier_id": "dossier-1",
                "transcription_id": "tx-1",
                "segment_id": "seg-1",
                "run_id": "run-1",
            },
        )
    )

    assert seen["kwargs"] == {
        "dossier_id": "dossier-1",
        "transcription_id": "tx-1",
        "segment_id": "seg-1",
        "run_id": "run-1",
    }
    assert result.executed is True
    assert result.outputs == {"ok": True}
    assert result.artifact_refs == ("artifact://ok",)


def test_transcript_edit_tool_binding_wraps_dataclass_payload_through_executor() -> None:
    @dataclass
    class FakePayload:
        note: str
        count: int

    def fake_tool(**kwargs):
        assert kwargs == {"dossier_id": "dossier-1", "transcription_id": "tx-1"}
        return FakePayload(note="done", count=2)

    binding = runtime_composition._tool_handler_passthrough(fake_tool)
    executor = ExecutionExecutor()
    executor.register("hydrate_t0_draft_refs", binding)

    result = executor.execute(
        ExecutionStepRequest(
            session_id="session-1",
            action_id="hydrate_t0_draft_refs",
            inputs={"dossier_id": "dossier-1", "transcription_id": "tx-1"},
        )
    )

    assert result.executed is True
    assert result.outputs == {"result": {"note": "done", "count": 2}}


def test_transcript_edit_tool_binding_turns_exceptions_into_refusals_through_executor() -> None:
    def fake_tool(**kwargs):
        assert kwargs == {"dossier_id": "dossier-1"}
        raise RuntimeError("boom")

    binding = runtime_composition._tool_handler_passthrough(fake_tool)
    executor = ExecutionExecutor()
    executor.register("hydrate_t0_draft_refs", binding)

    result = executor.execute(
        ExecutionStepRequest(
            session_id="session-1",
            action_id="hydrate_t0_draft_refs",
            inputs={"dossier_id": "dossier-1"},
        )
    )

    assert result.executed is False
    assert result.refusal is not None
    assert result.refusal.reason_code == "transcript_edit_tool_error"
    assert result.outputs == {"error": "boom"}
