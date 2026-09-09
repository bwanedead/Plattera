"""Tests for inherited handoff condition projection."""

from __future__ import annotations

import json
from pathlib import Path

from domains.mapping.deed_to_ir.prompting.surfaces.startup_context import build_startup_context_block
from tooling.mapping.deed_to_ir import (
    build_inherited_handoff_conditions,
    load_transcript_edit_output_handoff,
    make_hydrate_deed_to_ir_input_handler,
    startup_handoff_from_loader_dict,
)
from domains.mapping.deed_to_ir.payloads import DeedToIrScope

_FIXTURE = Path(__file__).resolve().parents[3] / "domains" / "mapping" / "deed_to_ir" / "test_fixtures"
_HANDOFF_FIXTURE = _FIXTURE / "transcript_edit_output_handoff.json"
_PRACTICE_HANDOFF = (
    Path(__file__).resolve().parents[4] / "practice_deeds" / "right_of_way" / "deed_to_ir" / "transcript_edit_output.json"
)


def _build_block_from_fixture() -> dict:
    loaded = load_transcript_edit_output_handoff(output_path=_HANDOFF_FIXTURE)
    return build_inherited_handoff_conditions(
        source=loaded["source"],
        parcel_metadata=loaded["parcel_metadata"],
        issues=loaded["issues"],
        hitl_decisions=loaded["hitl_decisions"],
        evidence_refs=loaded["evidence_refs"],
        normalized_or_mapping_transcript=loaded.get("normalized_or_mapping_transcript"),
        source_transcript_verbatim=loaded.get("source_transcript_verbatim"),
        excerpts=loaded.get("excerpts"),
    )


def test_inherited_handoff_conditions_are_bounded_and_path_free() -> None:
    block = _build_block_from_fixture()
    dumped = json.dumps(block)

    assert block["block_id"] == "inherited_handoff_conditions"
    assert len(block["parcels"]) == 2
    assert block["parcels"][0]["forwardable"] is True
    assert block["parcels"][1]["forwardable"] is False
    assert block["issues"]
    assert block["hitl_decisions"]
    assert block["evidence_refs"]["count"] >= 1
    assert "agent conclusions" not in dumped.lower()
    assert "test_fixtures" not in dumped.lower()
    assert str(_HANDOFF_FIXTURE) not in dumped


def test_inherited_handoff_conditions_surface_parcel2_cutoff_from_fixture() -> None:
    block = _build_block_from_fixture()
    issue = block["issues"][0]
    assert issue["issue_id"] == "parcel_2_continuation_scope"
    assert "cut" in issue["summary"].lower() or "ends" in issue["summary"].lower()
    assert issue.get("mapping_blocking") is True
    parcel_2 = next(row for row in block["parcels"] if row["parcel_id"] == "parcel_2")
    assert parcel_2["forwardable"] is False


def test_practice_fixture_surfaces_range_conflict_and_hitl_choice() -> None:
    loaded = load_transcript_edit_output_handoff(output_path=_PRACTICE_HANDOFF)
    block = build_inherited_handoff_conditions(
        source=loaded["source"],
        parcel_metadata=loaded["parcel_metadata"],
        issues=loaded["issues"],
        hitl_decisions=loaded["hitl_decisions"],
        evidence_refs=loaded["evidence_refs"],
        excerpts=loaded.get("excerpts"),
    )
    dumped = json.dumps(block).lower()
    assert "range 74" in dumped
    assert "range 75" in dumped
    assert any("range 75" in str(row.get("choice", "")).lower() for row in block["hitl_decisions"])
    assert str(_PRACTICE_HANDOFF) not in dumped


def test_startup_and_hydration_share_same_inherited_handoff_block() -> None:
    loaded = load_transcript_edit_output_handoff(output_path=_HANDOFF_FIXTURE)
    handoff = startup_handoff_from_loader_dict(
        scope=DeedToIrScope(dossier_id="d-test"),
        loaded=loaded,
        resolution_state_ref="transcript_edit:resolution_state:fixture-001",
        resolution_state_snapshot={"items": [], "relations": []},
    )
    startup_block = build_startup_context_block(handoff)
    assert "Inherited handoff conditions" in startup_block.text
    assert "not agent conclusions" in startup_block.text
    assert handoff.inherited_handoff_conditions["block_id"] == "inherited_handoff_conditions"

    handler = make_hydrate_deed_to_ir_input_handler(
        handoff_context={
            **loaded,
            "resolution_state_ref": "transcript_edit:resolution_state:fixture-001",
            "resolution_state_snapshot": {"items": [], "relations": []},
            "inherited_handoff_conditions": handoff.inherited_handoff_conditions,
        }
    )
    result = handler({"sections": ["parcel_metadata"]})
    assert result["executed"] is True
    assert result["outputs"]["inherited_handoff_conditions"] == handoff.inherited_handoff_conditions


def test_hydrate_section_inherited_handoff_conditions_matches_top_level() -> None:
    loaded = load_transcript_edit_output_handoff(output_path=_HANDOFF_FIXTURE)
    handler = make_hydrate_deed_to_ir_input_handler(handoff_context=loaded)
    result = handler({"sections": ["inherited_handoff_conditions"]})
    top_level = result["outputs"]["inherited_handoff_conditions"]
    section = result["outputs"]["results"]["inherited_handoff_conditions"]
    assert section == top_level
    assert top_level["block_id"] == "inherited_handoff_conditions"


def test_decision_summary_agent_facing_once_in_wire_and_hydrate() -> None:
    """Typed summary is nested only; production wire/prompt expose each decision id once."""
    from domains.mapping.deed_to_ir.runtime_adapter.composition import (
        _handoff_tool_context,
        _handoff_wire,
    )

    loaded = load_transcript_edit_output_handoff(output_path=_HANDOFF_FIXTURE)
    # Inject a compact provisional summary as the loader would for managed provenance.
    loaded["transcript_edit_decision_summary"] = {
        "schema_version": 2,
        "decisions": [
            {
                "decision_id": "unique-decision-1",
                "determination": "provisional",
                "uncertainty_reasons": ["observer_disagreement"],
                "replacements": [
                    {
                        "lane": "source_transcript_verbatim",
                        "replacement_text": "Range 75",
                    }
                ],
            }
        ],
        "counts": {
            "source": 1,
            "retained": 1,
            "provisional": 1,
            "earned": 0,
            "omitted": 0,
            "source_provisional": 1,
            "source_earned": 0,
        },
    }
    handoff = startup_handoff_from_loader_dict(
        scope=DeedToIrScope(dossier_id="d-test"),
        loaded=loaded,
    )
    assert handoff.transcript_edit_decision_summary["decisions"]
    nested = handoff.inherited_handoff_conditions.get("transcript_edit_decision_summary")
    assert nested and nested["decisions"][0]["decision_id"] == "unique-decision-1"

    wire = _handoff_wire(handoff)
    tool_ctx = _handoff_tool_context(handoff)
    assert "transcript_edit_decision_summary" not in wire
    assert "transcript_edit_decision_summary" not in tool_ctx
    assert "transcript_edit_decision_summary" in wire["inherited_handoff_conditions"]
    assert "transcript_edit_decision_summary" in tool_ctx["inherited_handoff_conditions"]

    wire_dump = json.dumps(wire)
    assert wire_dump.count("unique-decision-1") == 1

    prompt = build_startup_context_block(handoff).text
    assert prompt.count("unique-decision-1") == 1

    handler = make_hydrate_deed_to_ir_input_handler(
        handoff_context={
            **{k: v for k, v in loaded.items() if k != "transcript_edit_decision_summary"},
            "inherited_handoff_conditions": handoff.inherited_handoff_conditions,
        }
    )
    result = handler({"sections": ["inherited_handoff_conditions"]})
    assert result["executed"] is True
    hydrated = result["outputs"]["inherited_handoff_conditions"]
    assert hydrated["transcript_edit_decision_summary"]["decisions"][0]["decision_id"] == (
        "unique-decision-1"
    )


def test_markdown_formatter_labels_upstream_not_agent_conclusions() -> None:
    from domains.mapping.deed_to_ir.prompting.surfaces.inherited_handoff_prompt import (
        format_inherited_handoff_conditions_markdown,
    )

    block = _build_block_from_fixture()
    text = format_inherited_handoff_conditions_markdown(block)
    assert "not agent conclusions" in text
    assert "parcel_1" in text
    assert "parcel_2" in text
    assert "Range 75" in text or "range 75" in text.lower()
