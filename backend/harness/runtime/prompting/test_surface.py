from __future__ import annotations

from harness.runtime.prompting.surface import (
    _HARNESS_TRUNK_METHOD_TEXT,
    build_harness_turn_surface,
)


def test_harness_surface_teaches_work_universe_posture_and_audit_sweep() -> None:
    surface = build_harness_turn_surface()
    text = "\n".join(block.content for block in surface.blocks).lower()
    assert "work_universe_posture" in text
    assert "initial" in text
    assert "believed_adequate" in text
    assert "audited" in text
    assert "audit sweep" in text
    assert "if i had to defend every closed item one by one" in text
    assert "mechanically blocked until `mission.work_universe_posture` is `audited`" in text


def test_harness_surface_teaches_hitl_self_audit_and_async_default() -> None:
    surface = build_harness_turn_surface()
    text = "\n".join(block.content for block in surface.blocks).lower()
    assert "which remaining material unresolved issues have exhausted the strongest in-run check" in text
    assert "multiple hitls in one run are valid" in text
    assert "async hitl is the default" in text
    assert "blocking hitl is for true pause conditions only" in text


def test_harness_surface_teaches_output_claim_coverage() -> None:
    surface = build_harness_turn_surface()
    text = "\n".join(block.content for block in surface.blocks).lower()
    assert "output-claim coverage" in text
    assert "material exact claim" in text
    assert "future review ui" in text
    assert "auditable" in text
    # evidence-local section
    assert "evidence-local earned claims" in text
    assert "direct inspectability" in text
    # terminal posture section
    assert "terminal completion posture" in text
    assert "complete_run" in text
    # hitl repair section
    assert "hitl repair behavior" in text
    assert "re-asking when a valid answer already exists" in text


def test_harness_surface_new_sections_contain_no_deed_examples() -> None:
    """New method-text sections must not introduce deed/mapping-shaped examples."""
    lowered = _HARNESS_TRUNK_METHOD_TEXT.lower()
    idx = lowered.find("## output-claim coverage")
    assert idx >= 0, "output-claim coverage section must exist in method text"
    new_sections = lowered[idx:]
    for banned in ("bearing", " range ", "parcel", "acreage", "cutoff"):
        assert banned not in new_sections, f"Found banned term {banned!r} in new sections"


def test_surface_teaches_projection_boundary_rule() -> None:
    text = _HARNESS_TRUNK_METHOD_TEXT
    lowered = text.lower()
    assert "projection boundary rule" in lowered
    assert "truncated excerpt is not evidence" in lowered
    assert "absent from the excerpt" in lowered
    assert "artifact_excerpt_boundary_risk" in text


def test_surface_teaches_partial_artifact_coverage_rule() -> None:
    text = _HARNESS_TRUNK_METHOD_TEXT
    lowered = text.lower()
    assert "partial artifact coverage rule" in lowered
    assert "visible, available, unblocked portion" in lowered
    assert "blocked portions explicitly" in lowered


def test_surface_teaches_source_and_downstream_lanes() -> None:
    text = _HARNESS_TRUNK_METHOD_TEXT
    lowered = text.lower()
    assert "source-observed vs downstream-usable lanes" in lowered
    assert "source-observed" in lowered
    assert "downstream-usable" in lowered
    assert "may be identical" in lowered
    assert "do not silently overwrite source-observed truth" in lowered
    assert "preserve the visible portion" in lowered


def test_surface_source_downstream_lane_section_has_no_current_deed_examples() -> None:
    lowered = _HARNESS_TRUNK_METHOD_TEXT.lower()
    start = lowered.find("## source-observed vs downstream-usable lanes")
    end = lowered.find("## compact claim atoms")
    assert start >= 0, "source/downstream lane section must exist in method text"
    assert end > start, "compact claim atoms section must follow source/downstream lane section"
    section = lowered[start:end]
    for banned in ("range 75", "range 74", "parcel 1", "parcel 2", "nw corner", "1638"):
        assert banned not in section, f"Found banned term {banned!r} in source/downstream lane section"
