from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.common.identity_composer import (
    Domain,
    InheritanceMode,
    Surface,
    compose_identity_header,
)
from backend.agents.common.prompt_observability import build_prompt_event_artifact, build_prompt_event_metadata
from backend.agents.common.prompt_sources import build_shared_harness_trunk_blocks
from backend.agents.deed_to_ir.prompt_sources import build_deed_to_ir_branch_blocks
from backend.agents.transcript_edit.prompt_sources import build_transcript_edit_branch_blocks


def test_shared_harness_trunk_blocks_are_canonical_and_hash_stable() -> None:
    blocks = build_shared_harness_trunk_blocks(
        constitution_version="v2",
        inheritance_mode="full",
    )
    assert [block.block_id for block in blocks] == [
        "machine_identity",
        "generic_run_choreography",
        "generic_response_law",
    ]
    assert all(block.layer == "harness_trunk" for block in blocks)
    assert all(len(block.content_hash) == 64 for block in blocks)
    assert "stateful agent harness" in blocks[0].text


def test_compose_identity_header_exposes_source_block_refs_and_prompt_event_scaffold() -> None:
    result = compose_identity_header(
        run_link_id="run-1",
        mission_objective="test mission",
        domain=Domain.TRANSCRIPT_EDIT,
        surface=Surface.TX_PLANNER,
        inheritance_mode=InheritanceMode.LIGHT,
        model="gpt-test",
    )
    assert result.source_blocks
    assert result.source_blocks[0].block_id == "machine_identity"
    assert result.prompt_event_metadata is not None
    assert result.prompt_event_metadata.surface == "tx_planner"
    assert result.prompt_event_metadata.domain == "transcript_edit"
    assert result.prompt_event_metadata.prompt_event_id is None


def test_compose_identity_header_for_deed_branch_keeps_compatibility_source_blocks() -> None:
    result = compose_identity_header(
        run_link_id="run-2",
        mission_objective="test deed branch",
        domain=Domain.DEED_TO_IR,
        surface=Surface.DEED_CONTROLLER,
        inheritance_mode=InheritanceMode.FULL,
        model="gpt-test",
    )
    assert result.source_blocks
    assert any(block.owner == "deed_to_ir" for block in result.source_blocks)


def test_branch_prompt_sources_remain_layered_and_small() -> None:
    deed_blocks = build_deed_to_ir_branch_blocks(inheritance_mode="full")
    tx_blocks = build_transcript_edit_branch_blocks(inheritance_mode="full")
    assert len(deed_blocks) == 1
    assert deed_blocks[0].layer == "domain_branch"
    assert deed_blocks[0].owner == "deed_to_ir"
    assert len(tx_blocks) == 3
    assert {block.owner for block in tx_blocks} == {"transcript_edit"}
    assert {block.layer for block in tx_blocks} == {"domain_branch"}


def test_prompt_event_metadata_derives_event_id_when_enough_identity_is_known() -> None:
    event = build_prompt_event_metadata(
        run_link_id="run-1",
        run_id="run-1",
        iteration_index=4,
        surface="tx_focus_resolver",
        domain="transcript_edit",
        model="gpt-test",
        constitution_version="v2",
        composition_mode="full",
    )
    assert event.prompt_event_id == "prompt_event:run-1:i04:tx_focus_resolver"
    assert event.run_link_id == "run-1"
    assert event.run_id == "run-1"


def test_prompt_event_artifact_captures_prompt_snapshot_and_outcome_linkage() -> None:
    identity = compose_identity_header(
        run_link_id="run-3",
        mission_objective="prompt event",
        domain=Domain.TRANSCRIPT_EDIT,
        surface=Surface.TX_PLANNER,
        inheritance_mode=InheritanceMode.FULL,
        model="gpt-test",
    )
    artifact = build_prompt_event_artifact(
        metadata=identity.prompt_event_metadata,
        system_text=identity.header_text,
        user_text='{"foo":"bar"}',
        structured_payloads={"payload": {"foo": "bar"}},
        model_output_payload={"text": "{\"answer\": 1}"},
        model_output_text='{"answer": 1}',
        parsed_output_summary={"status": "parsed"},
        outcome_kind="plan_valid",
        outcome_ref="plan-1",
        downstream_refs_delta={"trace_event_kind": "model_proposal"},
    )
    assert artifact.metadata.prompt_event_id is None
    assert artifact.system_text.startswith("[IDENTITY constitution=v2]")
    assert artifact.user_text == '{"foo":"bar"}'
    assert artifact.structured_payloads["payload"]["foo"] == "bar"
    assert artifact.model_output_payload["text"] == '{"answer": 1}'
    assert artifact.model_output_text == '{"answer": 1}'
    assert artifact.outcome_kind == "plan_valid"
    assert artifact.outcome_ref == "plan-1"
