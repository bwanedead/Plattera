from __future__ import annotations

from domains.mapping.transcript_edit.runtime_adapter import build_transcript_edit_runtime_adapter
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
