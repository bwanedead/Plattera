from __future__ import annotations

from dataclasses import dataclass

from domains.mapping.transcript_edit.runtime_adapter import composition as runtime_composition
from domains.mapping.transcript_edit.execution.tool_specs import build_transcript_edit_tool_specs
from domains.mapping.transcript_edit.runtime_adapter import build_transcript_edit_runtime_adapter
from harness.execution.contracts import ExecutionStepRequest
from harness.execution.executor import ExecutionExecutor
from harness.runtime.composition import TurnSurface
from tooling.mapping.transcript_edit.draft_loading import HydrateT0DraftsResult


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
        "workspace_id": None,
    }
    assert surface.payload["transcript_edit"]["tool_ids"] == [
        "load_transcript_edit_startup_inventory",
        "hydrate_t0_draft_refs",
        "hydrate_transcript_edit_working_draft",
        "load_source_image_context",
        "save_transcript_edit",
        "publish_transcript_edit_output",
    ]
    tool_specs = surface.payload["transcript_edit"]["tool_specs"]
    assert len(tool_specs) == len(build_transcript_edit_tool_specs())
    assert tool_specs[0] == {
        "tool_id": "load_transcript_edit_startup_inventory",
        "category": "observation",
        "purpose": "First-contact ref inventory: dossier scope, peer T0 draft refs, source image refs, transcript-edit draft refs, lightweight metadata only.",
        "expected_request_shape": "dossier_id, transcription_id; optional segment_id, run_id, workspace_id (workspace_id or run_id scopes transcript_edit artifacts under artifacts/transcript_edit/).",
        "expected_request_json_shape": {
            "type": "object",
            "required": ["dossier_id", "transcription_id"],
            "properties": {
                "dossier_id": {"type": "string"},
                "transcription_id": {"type": "string"},
                "segment_id": {"type": ["string", "null"]},
                "run_id": {"type": ["string", "null"]},
                "workspace_id": {"type": ["string", "null"]},
            },
            "additionalProperties": False,
        },
        "expected_result_shape": "TranscriptEditStartupInventory: refs + descriptors; no full draft bodies; structured missing_resource entries if gaps.",
    }
    hydrate_spec = next(spec for spec in tool_specs if spec["tool_id"] == "hydrate_t0_draft_refs")
    assert hydrate_spec["expected_request_json_shape"] == {
        "type": "object",
        "required": ["dossier_id", "transcription_id"],
        "properties": {
            "dossier_id": {"type": "string"},
            "transcription_id": {"type": "string"},
            "ref_ids": {"type": ["array", "null"], "items": {"type": "string"}},
            "t0_raw_ref_ids": {"type": ["array", "null"], "items": {"type": "string"}},
            "max_refs": {"type": "integer"},
        },
        "additionalProperties": False,
    }
    assert [binding.tool_id for binding in surface.tool_bindings] == [
        "load_transcript_edit_startup_inventory",
        "hydrate_t0_draft_refs",
        "hydrate_transcript_edit_working_draft",
        "load_source_image_context",
        "save_transcript_edit",
        "publish_transcript_edit_output",
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


def test_hydrate_t0_binding_accepts_t0_raw_ref_ids_alias(monkeypatch) -> None:
    """Regression: model-shaped payload uses t0_raw_ref_ids (live loop iteration 2)."""
    captured: dict[str, object] = {}

    def fake_hydrate(**kwargs):
        captured["kwargs"] = dict(kwargs)
        return HydrateT0DraftsResult(drafts=tuple(), errors=tuple())

    monkeypatch.setattr(runtime_composition, "hydrate_t0_draft_refs", fake_hydrate)
    binding = next(b for b in runtime_composition.build_transcript_edit_tool_bindings() if b.tool_id == "hydrate_t0_draft_refs")
    executor = ExecutionExecutor()
    executor.register(binding.tool_id, binding.handler)

    dossier_id = "9f5eecb6-cd7e-483c-b691-b76aa7132e8e"
    refs = [
        "t0:raw:draft_legal_text_image_v1",
        "t0:raw:draft_legal_text_image_v2",
        "t0:raw:draft_legal_text_image_v3",
    ]
    result = executor.execute(
        ExecutionStepRequest(
            session_id="session-1",
            action_id="hydrate_t0_draft_refs",
            inputs={
                "dossier_id": dossier_id,
                "transcription_id": "draft_legal_text_image",
                "t0_raw_ref_ids": refs,
            },
        )
    )

    assert result.executed is True
    assert captured["kwargs"] == {
        "dossier_id": dossier_id,
        "transcription_id": "draft_legal_text_image",
        "ref_ids": refs,
    }


def test_hydrate_t0_binding_both_keys_same_multiset_succeeds(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_hydrate(**kwargs):
        captured["kwargs"] = dict(kwargs)
        return HydrateT0DraftsResult(drafts=tuple(), errors=tuple())

    monkeypatch.setattr(runtime_composition, "hydrate_t0_draft_refs", fake_hydrate)
    binding = next(b for b in runtime_composition.build_transcript_edit_tool_bindings() if b.tool_id == "hydrate_t0_draft_refs")
    executor = ExecutionExecutor()
    executor.register(binding.tool_id, binding.handler)

    result = executor.execute(
        ExecutionStepRequest(
            session_id="session-1",
            action_id="hydrate_t0_draft_refs",
            inputs={
                "dossier_id": "d1",
                "transcription_id": "t1",
                "ref_ids": ["t0:raw:a", "t0:raw:b"],
                "t0_raw_ref_ids": ["t0:raw:b", "t0:raw:a"],
            },
        )
    )

    assert result.executed is True
    assert captured["kwargs"]["ref_ids"] == ["t0:raw:a", "t0:raw:b"]


def test_hydrate_t0_binding_both_keys_conflict_refuses() -> None:
    binding = next(b for b in runtime_composition.build_transcript_edit_tool_bindings() if b.tool_id == "hydrate_t0_draft_refs")
    executor = ExecutionExecutor()
    executor.register(binding.tool_id, binding.handler)

    result = executor.execute(
        ExecutionStepRequest(
            session_id="session-1",
            action_id="hydrate_t0_draft_refs",
            inputs={
                "dossier_id": "d1",
                "transcription_id": "t1",
                "ref_ids": ["t0:raw:a"],
                "t0_raw_ref_ids": ["t0:raw:b"],
            },
        )
    )

    assert result.executed is False
    assert result.refusal is not None
    assert result.refusal.reason_code == "transcript_edit_input_conflict"
    assert result.refusal.blocked_by_invariant is True
    err = result.outputs.get("error")
    assert isinstance(err, dict)
    assert err.get("code") == "ref_ids_t0_raw_ref_ids_conflict"
    assert err.get("ref_ids") == ["t0:raw:a"]
    assert err.get("t0_raw_ref_ids") == ["t0:raw:b"]


def test_hydrate_t0_binding_rejects_string_t0_raw_ref_ids_container() -> None:
    binding = next(b for b in runtime_composition.build_transcript_edit_tool_bindings() if b.tool_id == "hydrate_t0_draft_refs")
    executor = ExecutionExecutor()
    executor.register(binding.tool_id, binding.handler)

    result = executor.execute(
        ExecutionStepRequest(
            session_id="session-1",
            action_id="hydrate_t0_draft_refs",
            inputs={
                "dossier_id": "d1",
                "transcription_id": "t1",
                "t0_raw_ref_ids": "t0:raw:draft_legal_text_image_v1",
            },
        )
    )

    assert result.executed is False
    assert result.refusal is not None
    assert result.refusal.reason_code == "transcript_edit_input_conflict"
    err = result.outputs.get("error")
    assert isinstance(err, dict)
    assert err.get("code") == "invalid_ref_container_type"
    assert err.get("field") == "t0_raw_ref_ids"
    assert err.get("got_type") == "str"


def test_hydrate_t0_binding_rejects_non_string_ref_id_elements() -> None:
    binding = next(b for b in runtime_composition.build_transcript_edit_tool_bindings() if b.tool_id == "hydrate_t0_draft_refs")
    executor = ExecutionExecutor()
    executor.register(binding.tool_id, binding.handler)

    result = executor.execute(
        ExecutionStepRequest(
            session_id="session-1",
            action_id="hydrate_t0_draft_refs",
            inputs={
                "dossier_id": "d1",
                "transcription_id": "t1",
                "ref_ids": [123],
            },
        )
    )
    assert result.executed is False
    err = result.outputs.get("error")
    assert isinstance(err, dict)
    assert err.get("code") == "invalid_ref_id_element_type"
    assert err.get("field") == "ref_ids"
    assert err.get("index") == 0
    assert err.get("got_type") == "int"

    result2 = executor.execute(
        ExecutionStepRequest(
            session_id="session-1",
            action_id="hydrate_t0_draft_refs",
            inputs={
                "dossier_id": "d1",
                "transcription_id": "t1",
                "t0_raw_ref_ids": [{"x": 1}],
            },
        )
    )
    assert result2.executed is False
    err2 = result2.outputs.get("error")
    assert isinstance(err2, dict)
    assert err2.get("code") == "invalid_ref_id_element_type"
    assert err2.get("got_type") == "dict"

    result3 = executor.execute(
        ExecutionStepRequest(
            session_id="session-1",
            action_id="hydrate_t0_draft_refs",
            inputs={
                "dossier_id": "d1",
                "transcription_id": "t1",
                "ref_ids": ["t0:raw:ok", 1],
            },
        )
    )
    assert result3.executed is False
    err3 = result3.outputs.get("error")
    assert isinstance(err3, dict)
    assert err3.get("index") == 1


def test_hydrate_t0_binding_rejects_non_array_ref_ids() -> None:
    binding = next(b for b in runtime_composition.build_transcript_edit_tool_bindings() if b.tool_id == "hydrate_t0_draft_refs")
    executor = ExecutionExecutor()
    executor.register(binding.tool_id, binding.handler)

    for bad in (123, {"x": 1}, 1.5):
        result = executor.execute(
            ExecutionStepRequest(
                session_id="session-1",
                action_id="hydrate_t0_draft_refs",
                inputs={
                    "dossier_id": "d1",
                    "transcription_id": "t1",
                    "ref_ids": bad,
                },
            )
        )
        assert result.executed is False, bad
        err = result.outputs.get("error")
        assert isinstance(err, dict)
        assert err.get("code") == "invalid_ref_container_type"
        assert err.get("field") == "ref_ids"


def test_hydrate_t0_binding_ref_ids_only_still_succeeds(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_hydrate(**kwargs):
        captured["kwargs"] = dict(kwargs)
        return HydrateT0DraftsResult(drafts=tuple(), errors=tuple())

    monkeypatch.setattr(runtime_composition, "hydrate_t0_draft_refs", fake_hydrate)
    binding = next(b for b in runtime_composition.build_transcript_edit_tool_bindings() if b.tool_id == "hydrate_t0_draft_refs")
    executor = ExecutionExecutor()
    executor.register(binding.tool_id, binding.handler)

    result = executor.execute(
        ExecutionStepRequest(
            session_id="session-1",
            action_id="hydrate_t0_draft_refs",
            inputs={
                "dossier_id": "d1",
                "transcription_id": "t1",
                "ref_ids": ["t0:raw:x"],
                "max_refs": 3,
            },
        )
    )

    assert result.executed is True
    assert captured["kwargs"] == {
        "dossier_id": "d1",
        "transcription_id": "t1",
        "ref_ids": ["t0:raw:x"],
        "max_refs": 3,
    }
