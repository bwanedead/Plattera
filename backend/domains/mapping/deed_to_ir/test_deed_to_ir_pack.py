"""Co-located checks for deed_to_ir manifest, prompts, pack, and registry."""

from __future__ import annotations

from pathlib import Path

from domains.mapping import build_mapping_domain_adapter_registry
from domains.mapping.deed_to_ir import (
    build_deed_to_ir_branch_blocks,
    build_deed_to_ir_domain_pack,
    build_deed_to_ir_manifest,
    build_deed_to_ir_tool_specs,
    deed_to_ir_closure_semantics,
    deed_to_ir_handoff_semantics,
)
from tooling.mapping.deed_to_ir import load_transcript_edit_output_handoff


_FIXTURE = Path(__file__).resolve().parent / "test_fixtures" / "transcript_edit_output_handoff.json"


def test_manifest_tool_ids_match_tool_specs() -> None:
    manifest = build_deed_to_ir_manifest()
    specs = build_deed_to_ir_tool_specs()
    assert manifest.declared_semantic_tool_ids == tuple(s.tool_id for s in specs)
    assert manifest.declared_semantic_tool_ids == ()
    assert manifest.domain_id == "deed_to_ir"
    assert manifest.family_id == "mapping"
    assert manifest.display_name == "Deed To IR"


def test_domain_pack_builds() -> None:
    pack = build_deed_to_ir_domain_pack()
    payload = pack.build_surface_payload()
    assert payload["tool_ids"] == []
    assert payload["tool_specs"] == []
    assert payload["closure_policy"]["hard_enforced"] is False
    assert len(pack.build_semantic_prompt_blocks()) == 3


def test_branch_and_guidance_skeleton_markers() -> None:
    branch = build_deed_to_ir_branch_blocks()[0].text.lower()
    assert "deed-to-ir" in branch
    assert "transcript-edit output" in branch
    assert "normalized_or_mapping_transcript" in branch
    assert "source_transcript_verbatim" in branch
    assert "parcel_metadata" in branch
    assert "feature-graph ir" in branch
    assert "agent_kernel" not in branch
    assert "draft_ir" not in branch
    assert "hydrate_deed" not in branch

    guidance = next(
        b.text.lower()
        for b in build_deed_to_ir_domain_pack().build_semantic_prompt_blocks()
        if b.block_id == "deed_to_ir_procedural_guidance"
    )
    assert "forwardable vs blocked" in guidance
    assert "save/compile/judge" in guidance


def test_mapping_registry_resolves_deed_to_ir() -> None:
    registry = build_mapping_domain_adapter_registry()
    adapter = registry.require("deed_to_ir")
    assert adapter.domain_id == "deed_to_ir"


def test_loader_copies_handoff_fields_without_inference() -> None:
    loaded = load_transcript_edit_output_handoff(output_path=_FIXTURE)
    assert loaded["counts"]["parcels"] == 2
    assert loaded["counts"]["issues"] == 1
    assert loaded["counts"]["hitl_decisions"] == 1
    assert "normalized_or_mapping_transcript" in loaded
    assert "source_transcript_verbatim" in loaded
    parcels = loaded["parcel_metadata"]["parcels"]
    assert parcels[0]["forwardable"] is True
    assert parcels[1]["forwardable"] is False
    # Loader must not invent blockers or rewrite forwardability
    assert parcels[0]["parcel_id"] == "parcel_1"
    assert "mapping_blocking" not in loaded


def test_closure_and_handoff_semantics_stable() -> None:
    c = deed_to_ir_closure_semantics()
    h = deed_to_ir_handoff_semantics()
    assert c.summary.strip()
    assert h.summary.strip()
    assert "agent_kernel" not in (c.summary + h.summary).lower()


def test_loader_does_not_author_semantic_fields() -> None:
    loaded = load_transcript_edit_output_handoff(output_path=_FIXTURE)
    # Mechanical copy only — no harness-authored blocker/forwardability inference keys
    assert "mapping_blocking" not in loaded
    assert "forwardable" not in loaded
    assert loaded["parcel_metadata"]["parcels"][0]["forwardable"] is True
    assert "transcript_edit_output_path" not in loaded.get("source", {})
    assert loaded["source"]["loaded_source_label"] == "transcript_edit_output"


def test_loader_output_excludes_filesystem_path_from_source() -> None:
    loaded = load_transcript_edit_output_handoff(output_path=_FIXTURE)
    dumped = str(loaded)
    assert str(_FIXTURE) not in dumped
    assert "test_fixtures" not in dumped.lower()
