"""MAPDEP-BR-038: production-shaped dossier prompt exposes apply grammar."""

from __future__ import annotations

from harness.execution.session import ExecutionSessionManager
from harness.mission_state import new_closure_state, new_mission_state, new_resolution_state
from harness.runtime.composition import DefaultTurnComposer, ToolBinding
from harness.runtime.memory import LoopMemoryState
from harness.runtime.orchestration.compact_tool_contracts import project_compact_tool_contracts
from harness.runtime.orchestration.contracts import OrchestratorContext, SharedStateProjection
from harness.runtime.orchestration.llm_prompt_builder import build_choose_action_prompt_document
from harness.runtime.orchestration.prompt_sanitization import prompt_visible_surface_payloads

from domains.mapping.transcript_edit.domain_pack import build_transcript_edit_domain_pack
from domains.mapping.transcript_edit.execution.dossier_tool_specs import (
    build_dossier_transcript_edit_tool_specs,
)
from domains.mapping.transcript_edit.execution.tool_specs import (
    APPLY_TRANSCRIPT_EDITS_DECISION_EDIT_SHAPE,
    APPLY_TRANSCRIPT_EDITS_DOSSIER_REQUEST_SHAPE,
    APPLY_TRANSCRIPT_EDITS_LEAF_REQUEST_SHAPE,
    build_transcript_edit_tool_specs,
)
from domains.mapping.transcript_edit.payloads import (
    DossierTranscriptEditScope,
    DossierTranscriptEditStartupInventory,
    DossierTranscriptRunInventory,
    DossierTranscriptSegmentInventory,
)
from domains.mapping.transcript_edit.runtime_adapter.composition import (
    compose_transcript_edit_turn_surface,
)


def _q(segment: str, transcription: str, leaf: str) -> str:
    return f"dossier_segment:{segment}:run:{transcription}:{leaf}"


def _dossier_inventory() -> DossierTranscriptEditStartupInventory:
    return DossierTranscriptEditStartupInventory(
        scope=DossierTranscriptEditScope(
            dossier_id="dossier-synth",
            run_id="run-synth",
            workspace_id="workspace-synth",
        ),
        topology_fingerprint="a" * 64,
        segment_count=1,
        segments=(
            DossierTranscriptSegmentInventory(
                segment_id="segment-01",
                position=0,
                previous_segment_id=None,
                next_segment_id=None,
                runs=(
                    DossierTranscriptRunInventory(
                        transcription_id="tx-01",
                        position=0,
                        source_image_refs=(
                            _q("segment-01", "tx-01", "image:assoc:tx-01:original"),
                        ),
                        t0_draft_refs=(_q("segment-01", "tx-01", "t0:raw:pass_1"),),
                        working_draft_ref=None,
                        working_latest_revision_ref=None,
                        output_draft_ref=None,
                        artifact_fingerprint="b" * 64,
                        missing_resources=(),
                    ),
                ),
            ),
        ),
        topology_diagnostics=(),
    )


def _orchestrator_context() -> OrchestratorContext:
    return OrchestratorContext(
        session_manager=ExecutionSessionManager(),
        session_id="sess-br038",
        loop_memory=LoopMemoryState(),
        request_id_prefix="req-br038",
        opaque_run_context={},
        prompt_event_observer=None,
        raw_llm_io_observer=None,
    )


def _projection() -> SharedStateProjection:
    resolution_state = new_resolution_state(
        items=[],
        updated_at_epoch_seconds=1.0,
    )
    mission_state = new_mission_state(
        mission_id="mission-br038",
        loop_family="orchestration_kernel",
        objective="Synthetic dossier transcript edit.",
        resolution_state=resolution_state,
        closure_state=new_closure_state(
            overall_status="in_review",
            updated_at_epoch_seconds=1.0,
            dimensions=[],
        ),
        updated_at_epoch_seconds=1.0,
    )
    return SharedStateProjection(
        mission_state=mission_state,
        resolution_state=resolution_state,
        latest_refs={},
        active_item_id=None,
    )


def _compose_dossier_turn():
    pack = build_transcript_edit_domain_pack()
    inventory = _dossier_inventory()
    payload = pack.build_surface_payload(startup_inventory=inventory)
    bindings = tuple(
        ToolBinding(tool_id=tool_id, handler=lambda _req: {"executed": True})
        for tool_id in payload["tool_ids"]
    )
    surface = compose_transcript_edit_turn_surface(
        domain_pack=pack,
        startup_inventory=inventory,
        tool_bindings=bindings,
    )
    return DefaultTurnComposer().compose(surface), payload


def _assert_complete_apply_grammar(text: str) -> None:
    assert "edits[]" in text
    assert "lane" in text
    assert "expected_text" in text
    assert "replacement_text" in text
    assert "decision_id" in text
    assert "determination" in text
    assert "uncertainty_reasons" in text
    assert "verification_basis" in text
    assert "evidence_refs" in text
    assert "base_revision_ref" in text
    assert "dossier_segment:" in text
    assert "transcript_edit:working:rev:NNNN" in text
    assert "same leaf" not in text.lower()
    assert "same leaf decision/edit contract" not in text.lower()


def test_br038_h_shared_shape_constants_and_no_shorthand_drift() -> None:
    leaf = next(
        s for s in build_transcript_edit_tool_specs() if s.tool_id == "apply_transcript_edits"
    )
    dossier = next(
        s
        for s in build_dossier_transcript_edit_tool_specs()
        if s.tool_id == "apply_transcript_edits"
    )
    assert leaf.expected_request_shape == APPLY_TRANSCRIPT_EDITS_LEAF_REQUEST_SHAPE
    assert dossier.expected_request_shape == APPLY_TRANSCRIPT_EDITS_DOSSIER_REQUEST_SHAPE
    assert APPLY_TRANSCRIPT_EDITS_DECISION_EDIT_SHAPE in leaf.expected_request_shape
    assert APPLY_TRANSCRIPT_EDITS_DECISION_EDIT_SHAPE in dossier.expected_request_shape
    assert "same leaf" not in dossier.expected_request_shape.lower()
    assert "edits[]" in dossier.expected_request_shape
    assert "dossier_segment:" in dossier.expected_request_shape
    example_blob = str(dossier.example_request).lower()
    assert "curve" not in example_blob
    assert "deed" not in example_blob
    shape_blob = dossier.expected_request_shape.lower()
    assert "curve" not in shape_blob
    assert "deed" not in shape_blob


def test_br038_h_production_shaped_dossier_choose_action_prompt() -> None:
    composed, _payload = _compose_dossier_turn()
    visible = prompt_visible_surface_payloads(composed.surface_payloads)
    te_payload = visible["transcript_edit"]["transcript_edit"]
    apply_row = next(
        row
        for row in te_payload["tool_specs"]
        if row["tool_id"] == "apply_transcript_edits"
    )
    shape = apply_row["expected_request_shape"]
    _assert_complete_apply_grammar(shape)
    assert "expected_request_json_shape" not in apply_row
    assert "example_request" not in apply_row

    doc = build_choose_action_prompt_document(
        composed_input=composed,
        opaque_launch_context={"transcript_edit_scope_mode": "dossier"},
        context=_orchestrator_context(),
        projection=_projection(),
        journal_verbatim_keep_n=2,
    )
    _assert_complete_apply_grammar(doc.prompt_text)
    assert APPLY_TRANSCRIPT_EDITS_DOSSIER_REQUEST_SHAPE in doc.prompt_text
    assert "apply_transcript_edits" in doc.prompt_text
    # Production examples / apply shape stay source-neutral (doctrine may mention survey terms).
    assert "curve" not in apply_row["expected_request_shape"].lower()
    assert "deed" not in apply_row["expected_request_shape"].lower()


def test_br038_h_turn_recovery_compact_contract_keeps_or_omits_explicitly() -> None:
    """Compact contracts must not silently truncate mid-shape; whole shape or omit."""
    composed, payload = _compose_dossier_turn()
    contracts = project_compact_tool_contracts(
        composed.surface_payloads,
        available_tool_ids=payload["tool_ids"],
    )
    apply_row = next(c for c in contracts if c["tool_id"] == "apply_transcript_edits")
    if "expected_request_shape" in apply_row:
        _assert_complete_apply_grammar(apply_row["expected_request_shape"])
        assert len(apply_row["expected_request_shape"]) <= 320
    else:
        assert apply_row.get("expected_request_shape_omitted") is True
        assert "expected_request_shape" not in apply_row
