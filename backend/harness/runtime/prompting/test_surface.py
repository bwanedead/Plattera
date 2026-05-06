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
    assert "false determination" in text
    assert "falsely earned determination is dangerous" in text
    # terminal posture section
    assert "terminal completion posture" in text
    assert "complete_run" in text
    # hitl repair section
    assert "hitl repair behavior" in text
    assert "re-asking when a valid answer already exists" in text


def test_harness_surface_teaches_mission_critical_exactness() -> None:
    text = _HARNESS_TRUNK_METHOD_TEXT
    lowered = text.lower()
    assert "mission-critical exactness" in lowered
    assert "false determination is a common agent failure mode" in lowered
    assert "broad familiarity with the source" in lowered
    assert "locally and directly inspectable" in lowered
    assert "this is not ceremony" in lowered
    assert "falsely earned unit is dangerous" in lowered


def test_mission_critical_exactness_section_has_no_domain_examples() -> None:
    lowered = _HARNESS_TRUNK_METHOD_TEXT.lower()
    start = lowered.find("## mission-critical exactness")
    end = lowered.find("## defensible evidence rule")
    assert start >= 0, "mission-critical exactness section must exist"
    assert end > start, "defensible evidence rule section should follow mission-critical exactness"
    section = lowered[start:end]
    for banned in ("deed", "parcel", "range", "acreage", "plss", "transcript"):
        assert banned not in section, f"Found banned term {banned!r} in generic exactness doctrine"


def test_surface_teaches_decisive_detail_localization() -> None:
    text = _HARNESS_TRUNK_METHOD_TEXT
    lowered = text.lower()
    assert "decisive-detail localization" in lowered
    assert "smallest decisive detail" in lowered
    assert "common failure mode, not an edge case" in lowered
    assert "broad evidence can guide investigation" in lowered
    assert "does not prove the decisive atom" in lowered
    assert "point of difference" in lowered
    assert "isolate the decisive detail" in lowered


def test_decisive_detail_localization_section_has_no_domain_examples() -> None:
    lowered = _HARNESS_TRUNK_METHOD_TEXT.lower()
    start = lowered.find("## decisive-detail localization")
    end = lowered.find("## defensible evidence rule")
    assert start >= 0, "decisive-detail localization section must exist"
    assert end > start, "defensible evidence rule section should follow decisive-detail localization"
    section = lowered[start:end]
    for banned in ("deed", "parcel", "range", "bearing", "distance", "acreage", "plss", "transcript"):
        assert banned not in section, f"Found banned term {banned!r} in decisive-detail doctrine"


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


def test_surface_prompt_work_graph_projection_has_no_domain_examples() -> None:
    lowered = _HARNESS_TRUNK_METHOD_TEXT.lower()
    start = lowered.find("## prompt work-graph projection")
    end = lowered.find("## evidence refs vs evidence locators")
    assert start >= 0, "prompt work-graph projection section must exist"
    assert end > start, "evidence locator section should follow prompt projection section"
    section = lowered[start:end]
    for banned in ("deed", "parcel", "range", "bearing", "distance", "cutoff", "mapping"):
        assert banned not in section, f"Found banned term {banned!r} in prompt projection doctrine"


def test_surface_teaches_field_role_separation() -> None:
    text = _HARNESS_TRUNK_METHOD_TEXT
    lowered = text.lower()
    assert "field roles" in lowered
    assert "compact skeleton fields" in lowered
    assert "prose fields preserve reasoning" in lowered
    assert "determined_value` is for compact resolved values only" in text
    assert "candidate_values` is for considered options, not exhaustive truth" in text
    assert "closure_summary` is the short memory retained after closure" in text
    assert "reopen_triggers` describe what would invalidate or reopen the row" in text
    assert "long text belongs in artifacts" in lowered


def test_surface_field_roles_have_no_domain_examples() -> None:
    lowered = _HARNESS_TRUNK_METHOD_TEXT.lower()
    start = lowered.find("## field roles")
    end = lowered.find("## prompt work-graph projection")
    assert start >= 0, "field roles section must exist"
    assert end > start, "prompt projection section should follow field roles"
    section = lowered[start:end]
    for banned in ("deed", "parcel", "range", "bearing", "distance", "cutoff", "mapping"):
        assert banned not in section, f"Found banned term {banned!r} in field-role doctrine"


def test_surface_teaches_locator_rendering_without_domain_examples() -> None:
    lowered = _HARNESS_TRUNK_METHOD_TEXT.lower()
    start = lowered.find("## evidence refs vs evidence locators")
    end = lowered.find("## read carry-forward rule")
    assert start >= 0 and end > start
    section = lowered[start:end]
    assert "agent authors locators" in section
    assert "image regions" in section
    assert "text spans" in section
    assert "table cells" in section
    assert "json paths" in section
    assert "claim-local rendered evidence lets a reviewer" in section
    for banned in ("deed", "parcel", "range", "bearing", "distance", "cutoff", "mapping"):
        assert banned not in section, f"Found banned term {banned!r} in locator rendering doctrine"


def test_surface_source_downstream_lane_section_has_no_current_deed_examples() -> None:
    lowered = _HARNESS_TRUNK_METHOD_TEXT.lower()
    start = lowered.find("## source-observed vs downstream-usable lanes")
    end = lowered.find("## compact claim atoms")
    assert start >= 0, "source/downstream lane section must exist in method text"
    assert end > start, "compact claim atoms section must follow source/downstream lane section"
    section = lowered[start:end]
    for banned in ("range 75", "range 74", "parcel 1", "parcel 2", "nw corner", "1638"):
        assert banned not in section, f"Found banned term {banned!r} in source/downstream lane section"


def test_surface_teaches_hitl_evidence_readiness() -> None:
    """HITL evidence readiness doctrine appears in method text and names the mechanical flag."""
    assert "## HITL evidence readiness" in _HARNESS_TRUNK_METHOD_TEXT
    assert "hitl_evidence_readiness_debt" in _HARNESS_TRUNK_METHOD_TEXT
    assert "rendered_evidence_refs" in _HARNESS_TRUNK_METHOD_TEXT
    assert "evidence_artifact_summary" in _HARNESS_TRUNK_METHOD_TEXT


def test_surface_hitl_evidence_readiness_section_has_no_domain_terms() -> None:
    """HITL evidence readiness section contains no domain-specific terms."""
    lowered = _HARNESS_TRUNK_METHOD_TEXT.lower()
    start = lowered.find("## hitl evidence readiness")
    end = lowered.find("## projection boundary rule")
    assert start >= 0, "HITL evidence readiness section must exist"
    assert end > start, "Projection boundary rule section must follow HITL evidence readiness"
    section = lowered[start:end]
    domain_terms = ["deed", "parcel", "plss", "transcription", "dossier", "mapping"]
    for term in domain_terms:
        assert term not in section, f"Domain term {term!r} found in HITL evidence readiness section"
