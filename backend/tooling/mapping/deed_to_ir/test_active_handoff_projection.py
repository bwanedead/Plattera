"""Deterministic tests for lineage-aware active handoff projection."""

from __future__ import annotations

import copy

from domains.mapping.deed_to_ir.domain_pack import build_deed_to_ir_domain_pack
from tooling.mapping.deed_to_ir.active_handoff_projection import (
    HISTORICAL_CONTEXT_NOTE,
    build_active_handoff_context,
    classify_work_item_lineage_epoch,
    project_lineage_aware_handoff_context,
    render_lineage_aware_handoff_prompt_lines,
)
from tooling.mapping.deed_to_ir.mapping_lineage import build_current_mapping_lineage


CURRENT_MAPPING = "feature_graph:mapping:mapping_current_abc"
CURRENT_IR = "feature_graph:ir:graph__ws_run_v2"
SUPERSEDED_MAPPING = "feature_graph:mapping:mapping_old_xyz"
SUPERSEDED_IR = "feature_graph:ir:graph__ws_run_v0"


def _usable_lineage(**overrides):
    lineage = build_current_mapping_lineage(
        mapping_artifact_ref=CURRENT_MAPPING,
        source_ir_artifact_ref=CURRENT_IR,
        compile_gap_count=0,
        judge_gap_count=0,
        lineage_current=True,
        use_for_next_preview=True,
    )
    lineage.update(overrides)
    return lineage


def test_usable_current_lineage_produces_one_active_candidate() -> None:
    active = build_active_handoff_context(_usable_lineage())
    assert active is not None
    assert active["mapping_artifact_ref"] == CURRENT_MAPPING
    assert active["source_ir_artifact_ref"] == CURRENT_IR
    assert active["lineage_status"] == "current"
    assert active["selected_for_next_preview"] is True
    assert active["compile_gap_count"] == 0
    assert active["judge_gap_count"] == 0
    assert "scope_status" not in active
    assert "accepted" not in active
    assert "publish" not in str(active).lower()


def test_stale_or_unselected_lineage_omits_active_handoff() -> None:
    stale = _usable_lineage(stale=True, lineage_current=False, use_for_next_preview=False)
    assert build_active_handoff_context(stale) is None
    unselected = _usable_lineage(use_for_next_preview=False)
    assert build_active_handoff_context(unselected) is None


def test_superseded_only_work_is_historical_not_hot() -> None:
    lineage = _usable_lineage()
    items = [
        {
            "item_id": "old_map_obligation",
            "title": "Inspect first mapping",
            "status": "open",
            "evidence_refs": [SUPERSEDED_MAPPING, SUPERSEDED_IR],
        }
    ]
    projection = project_lineage_aware_handoff_context(lineage=lineage, work_items=items)
    assert "active_handoff_context" in projection
    historical = projection["historical_lineage_context"]
    assert historical["note"] == HISTORICAL_CONTEXT_NOTE
    assert len(historical["items"]) == 1
    assert historical["items"][0]["item_id"] == "old_map_obligation"
    assert historical["items"][0]["lineage_epoch"] == "historical"
    assert "current_lineage_work_items" not in projection


def test_current_lineage_work_remains_current() -> None:
    lineage = _usable_lineage()
    items = [
        {
            "item_id": "preview_now",
            "status": "open",
            "evidence_refs": [CURRENT_MAPPING],
        }
    ]
    projection = project_lineage_aware_handoff_context(lineage=lineage, work_items=items)
    assert projection["current_lineage_work_items"][0]["lineage_epoch"] == "current"
    assert "historical_lineage_context" not in projection


def test_mixed_current_and_superseded_refs_remain_current() -> None:
    epoch = classify_work_item_lineage_epoch(
        {
            "item_id": "mixed",
            "evidence_refs": [SUPERSEDED_MAPPING, CURRENT_IR, "image:derived:abc"],
        },
        current_refs=frozenset({CURRENT_MAPPING, CURRENT_IR}),
    )
    assert epoch == "current"


def test_unreferenced_work_remains_unchanged() -> None:
    lineage = _usable_lineage()
    items = [
        {
            "item_id": "author_ir",
            "status": "open",
            "evidence_refs": ["image:derived:abc", "operand_suite:ref"],
        }
    ]
    projection = project_lineage_aware_handoff_context(lineage=lineage, work_items=items)
    assert "historical_lineage_context" not in projection
    assert "current_lineage_work_items" not in projection
    assert classify_work_item_lineage_epoch(
        items[0],
        current_refs=frozenset({CURRENT_MAPPING, CURRENT_IR}),
    ) is None


def test_projection_mutates_no_semantic_state_or_relations() -> None:
    lineage = _usable_lineage()
    items = [
        {
            "item_id": "old",
            "status": "open",
            "blocking": True,
            "evidence_refs": [SUPERSEDED_MAPPING],
            "relations_note": "blocks final_handoff",
        }
    ]
    original = copy.deepcopy(items)
    projection = project_lineage_aware_handoff_context(lineage=lineage, work_items=items)
    assert items == original
    hist = projection["historical_lineage_context"]["items"][0]
    assert hist["status"] == "open"
    assert "blocking" not in hist
    assert items[0]["blocking"] is True


def test_blocked_scope_alone_never_upgrades_to_handoff_fact() -> None:
    # Active context is lineage-only; blocked scope status is irrelevant.
    active = build_active_handoff_context(_usable_lineage())
    assert active is not None
    assert "scope_status" not in active
    assert "blocked" not in str(active).lower()
    # Without usable lineage, blocked scope still does not create active handoff.
    assert build_active_handoff_context(None) is None


def test_prompt_ordering_active_before_historical() -> None:
    projection = project_lineage_aware_handoff_context(
        lineage=_usable_lineage(),
        work_items=[
            {
                "item_id": "old",
                "evidence_refs": [SUPERSEDED_MAPPING],
            }
        ],
    )
    text = "\n".join(render_lineage_aware_handoff_prompt_lines(projection))
    active_at = text.index("active_handoff_context:")
    historical_at = text.index("historical_lineage_context:")
    assert active_at < historical_at
    assert HISTORICAL_CONTEXT_NOTE in text


def test_guidance_covers_scoped_source_limitations_and_active_handoff() -> None:
    pack = build_deed_to_ir_domain_pack()
    block = next(
        b
        for b in pack.build_semantic_prompt_blocks()
        if b.block_id == "deed_to_ir_procedural_guidance"
    )
    assert block.version == "v33"
    text = block.text
    assert "active_handoff_context" in text
    assert "sole hot mapping" in text or "sole hot mapping/IR" in text
    assert "scoped blocked continuation" in text
    assert "durable package limitation" in text
    assert "blocks → final_handoff" in text or "blocks -> final_handoff" in text
    assert "historical lineage context" in text.lower() or "Historical lineage" in text
