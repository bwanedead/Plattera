from __future__ import annotations

import pytest

from domains.mapping.transcript_edit import build_transcript_edit_domain_pack
from domains.mapping.transcript_edit.runtime_adapter import composition as runtime_composition
from domains.mapping.transcript_edit.execution.tool_specs import build_transcript_edit_tool_specs
from domains.mapping.prompting.family_branch import MAPPING_FAMILY_BRANCH_VERSION
from domains.mapping.transcript_edit.runtime_adapter import build_transcript_edit_runtime_adapter
from harness.execution.contracts import ExecutionStepRequest
from harness.execution.executor import ExecutionExecutor
from harness.runtime.composition import ToolBinding, TurnSurface


def test_runtime_adapter_builds_turn_surface_from_opaque_launch_context() -> None:
    adapter = build_transcript_edit_runtime_adapter()
    pack = adapter.domain_pack

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

    # Family branch + domain branch + procedural guidance + startup context block
    assert len(surface.blocks) == 4
    assert [
        block.metadata["transcript_edit.prompt_block"]["block_id"]
        for block in surface.blocks[:3]
    ] == [block.block_id for block in pack.build_semantic_prompt_blocks()]
    assert "mapping family" in surface.blocks[0].content.lower()
    assert surface.blocks[0].metadata["transcript_edit.prompt_block"]["version"] == MAPPING_FAMILY_BRANCH_VERSION
    assert "text" not in surface.blocks[0].metadata["transcript_edit.prompt_block"]
    assert surface.blocks[1].content.startswith("You are operating in the **transcript edit** domain")
    assert "not a hard script" in surface.blocks[2].content.lower()
    assert surface.blocks[3].metadata["transcript_edit.prompt_block"]["block_id"] == "transcript_edit_startup_context"
    assert "startup artifact context" in surface.blocks[3].content.lower()

    # Payload is pack-declared only — no startup_inventory leakage
    te_payload = surface.payload["transcript_edit"]
    assert "startup_inventory" not in te_payload
    assert te_payload == pack.build_surface_payload()
    tool_specs = te_payload["tool_specs"]
    assert len(tool_specs) == len(build_transcript_edit_tool_specs())

    # Bindings mirror tool_ids
    assert [b.tool_id for b in surface.tool_bindings] == te_payload["tool_ids"]


def test_runtime_adapter_factory_returns_thin_domain_owned_adapter() -> None:
    adapter = build_transcript_edit_runtime_adapter()

    assert adapter.domain_id == "transcript_edit"
    assert adapter.manifest.domain_id == "transcript_edit"
    assert adapter.domain_pack.manifest.domain_id == "transcript_edit"
    assert adapter.manifest.closure_policy.hard_enforced is True


def test_turn_surface_raises_when_bound_tools_drift_from_pack(monkeypatch) -> None:
    from domains.mapping.transcript_edit.payloads import TranscriptEditScope, TranscriptEditStartupInventory

    def fake_bindings(**_kwargs):
        return (ToolBinding(tool_id="unexpected_tool", handler=lambda _request: {}),)

    monkeypatch.setattr(runtime_composition, "build_transcript_edit_tool_bindings", fake_bindings)

    with pytest.raises(ValueError, match="transcript_edit_runtime_tool_binding_mismatch"):
        runtime_composition.build_transcript_edit_turn_surface(
            domain_pack=build_transcript_edit_domain_pack(),
            startup_inventory=TranscriptEditStartupInventory(
                scope=TranscriptEditScope(dossier_id="d1", transcription_id="tx-1"),
            ),
        )


def test_tool_specs_shape_matches_shared_capability_ids() -> None:
    specs = build_transcript_edit_tool_specs()
    ids = [s.tool_id for s in specs]
    assert ids == [
        "hydrate_artifact_refs",
        "transform_artifact",
        "save_workspace_artifact",
        "copy_forward_save_workspace_artifact",
        "publish_workspace_artifact",
    ]
    for spec in specs:
        assert spec.category
        assert spec.purpose
        assert spec.expected_request_json_shape.get("type") == "object"
        assert isinstance(spec.example_request, dict)


def test_save_handler_exception_becomes_refusal(monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(runtime_composition, "save_transcript_edit", boom)

    bindings = runtime_composition.build_transcript_edit_tool_bindings(
        dossier_id="d1",
        transcription_id="tx-1",
        workspace_key="ws-key",
    )
    save_binding = next(b for b in bindings if b.tool_id == "save_workspace_artifact")
    executor = ExecutionExecutor()
    executor.register(save_binding.tool_id, save_binding.handler)

    result = executor.execute(
        ExecutionStepRequest(
            session_id="session-1",
            action_id="save_workspace_artifact",
            inputs={"transcript_text": "test content", "rationale": "test"},
        )
    )

    assert result.executed is False
    assert result.refusal is not None
    assert result.refusal.reason_code == "transcript_edit_tool_error"
    assert result.outputs == {"error": "disk full"}


def test_publish_handler_missing_source_ref_refuses() -> None:
    bindings = runtime_composition.build_transcript_edit_tool_bindings(
        dossier_id="d1",
        transcription_id="tx-1",
        workspace_key="ws-key",
    )
    pub_binding = next(b for b in bindings if b.tool_id == "publish_workspace_artifact")
    executor = ExecutionExecutor()
    executor.register(pub_binding.tool_id, pub_binding.handler)

    result = executor.execute(
        ExecutionStepRequest(
            session_id="session-1",
            action_id="publish_workspace_artifact",
            inputs={},  # missing source_revision_ref
        )
    )

    assert result.executed is False
    assert result.refusal is not None
    assert result.refusal.reason_code == "source_revision_ref_required"
    assert result.refusal.retryable is True
    assert result.refusal.blocked_by_invariant is False


def test_publish_handler_exception_becomes_refusal(monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise RuntimeError("storage failure")

    monkeypatch.setattr(runtime_composition, "publish_transcript_edit_output", boom)

    bindings = runtime_composition.build_transcript_edit_tool_bindings(
        dossier_id="d1",
        transcription_id="tx-1",
        workspace_key="ws-key",
    )
    pub_binding = next(b for b in bindings if b.tool_id == "publish_workspace_artifact")
    executor = ExecutionExecutor()
    executor.register(pub_binding.tool_id, pub_binding.handler)

    result = executor.execute(
        ExecutionStepRequest(
            session_id="session-1",
            action_id="publish_workspace_artifact",
            inputs={"source_revision_ref": "transcript_edit:working:rev:0001"},
        )
    )

    assert result.executed is False
    assert result.refusal is not None
    assert result.refusal.reason_code == "transcript_edit_tool_error"
    assert result.outputs == {"error": "storage failure"}


def test_hydrate_refs_binding_present_with_callable_handler() -> None:
    bindings = runtime_composition.build_transcript_edit_tool_bindings(
        dossier_id="d1",
        transcription_id="tx-1",
        workspace_key=None,
    )
    hydrate_binding = next(b for b in bindings if b.tool_id == "hydrate_artifact_refs")
    assert callable(hydrate_binding.handler)

    # Missing ref_ids returns error result (retryable at boundary)
    result = hydrate_binding.handler({"max_refs": 4})
    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == "ref_ids_required"
    assert result["refusal"]["retryable"] is True
    assert result["refusal"]["blocked_by_invariant"] is False


def test_transform_binding_present_with_callable_handler() -> None:
    bindings = runtime_composition.build_transcript_edit_tool_bindings(
        dossier_id="d1",
        transcription_id="tx-1",
        workspace_key=None,
    )
    transform_binding = next(b for b in bindings if b.tool_id == "transform_artifact")
    assert callable(transform_binding.handler)

    # No workspace_key → workspace_required refusal
    result = transform_binding.handler({"ref_id": "image:assoc:tx-1:original", "sub_action": "crop", "params": {}})
    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == "workspace_required"


def test_enrich_launch_context_enables_llm_streaming_by_default() -> None:
    adapter = build_transcript_edit_runtime_adapter()
    enriched = adapter.enrich_launch_context(
        {
            "dossier_id": "dossier-1",
            "transcription_id": "tx-1",
        }
    )
    assert enriched.get("llm_streaming") is True


def test_enrich_launch_context_respects_explicit_llm_streaming_false() -> None:
    adapter = build_transcript_edit_runtime_adapter()
    enriched = adapter.enrich_launch_context(
        {
            "dossier_id": "dossier-1",
            "transcription_id": "tx-1",
            "llm_streaming": False,
        }
    )
    assert "llm_streaming" not in enriched


def test_enrich_launch_context_respects_streaming_false_key() -> None:
    adapter = build_transcript_edit_runtime_adapter()
    enriched = adapter.enrich_launch_context(
        {
            "dossier_id": "dossier-1",
            "transcription_id": "tx-1",
            "streaming": False,
        }
    )
    assert "llm_streaming" not in enriched
