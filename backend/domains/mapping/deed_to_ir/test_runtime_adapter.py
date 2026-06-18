"""Runtime adapter tests for deed_to_ir domain skeleton."""

from __future__ import annotations

from pathlib import Path

import pytest

from domains.mapping.deed_to_ir.runtime_adapter import build_deed_to_ir_runtime_adapter
from harness.runtime.composition import TurnSurface

_FIXTURE = Path(__file__).resolve().parent / "test_fixtures" / "transcript_edit_output_handoff.json"


def test_runtime_adapter_builds_turn_surface_from_handoff() -> None:
    adapter = build_deed_to_ir_runtime_adapter()
    surface = adapter.build_turn_surface(
        {
            "dossier_id": "dossier-fixture",
            "transcript_edit_output_path": str(_FIXTURE),
            "run_id": "practice-row-live-20260619-76",
        }
    )

    assert isinstance(surface, TurnSurface)
    assert surface.surface_id == "deed_to_ir"
    assert len(surface.blocks) == 4
    assert surface.blocks[0].metadata["deed_to_ir.prompt_block"]["block_id"] == "mapping_family_branch"
    assert surface.blocks[1].metadata["deed_to_ir.prompt_block"]["block_id"] == "deed_to_ir_domain_branch"
    assert surface.blocks[3].metadata["deed_to_ir.prompt_block"]["block_id"] == "deed_to_ir_startup_context"

    startup_text = surface.blocks[3].content.lower()
    assert "startup handoff" in startup_text
    assert "parcel metadata" in startup_text
    assert "normalized / mapping lane excerpt" in startup_text
    assert "source verbatim lane excerpt" in startup_text
    assert "parcel_1" in startup_text
    assert "parcel_2" in startup_text

    payload = surface.payload["deed_to_ir"]
    assert payload["tool_ids"] == []
    assert surface.tool_bindings == ()

    handoff = surface.payload["deed_to_ir_startup_handoff"]
    assert handoff["source"]["source_revision_ref"] == "transcript_edit:working:rev:0001"
    assert handoff["source"]["loaded_source_label"] == "transcript_edit_output"
    assert "transcript_edit_output_path" not in handoff["source"]
    assert str(_FIXTURE) not in surface.blocks[3].content
    assert "output_path" not in startup_text
    assert "loaded_from" in startup_text
    assert handoff["counts"]["parcels"] == 2
    assert "normalized_or_mapping_transcript" in handoff
    assert "source_transcript_verbatim" in handoff
    assert handoff["parcel_metadata"]["parcels"][1]["forwardable"] is False


def test_runtime_adapter_requires_transcript_edit_output_path() -> None:
    adapter = build_deed_to_ir_runtime_adapter()
    with pytest.raises(ValueError, match="transcript_edit_output_path_required"):
        adapter.build_turn_surface({"dossier_id": "d1"})


def test_empty_tool_surface_is_intentional() -> None:
    adapter = build_deed_to_ir_runtime_adapter()
    surface = adapter.build_turn_surface(
        {
            "dossier_id": "d1",
            "transcript_edit_output_path": str(_FIXTURE),
        }
    )
    assert surface.tool_bindings == ()
    assert surface.payload["deed_to_ir"]["tool_ids"] == []
