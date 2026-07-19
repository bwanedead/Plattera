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
    assert "motion_posture" in text
    assert "does not block tools based on motion posture" in text


def test_harness_surface_defines_inventory_and_resolution_motion_gate() -> None:
    text = _HARNESS_TRUNK_METHOD_TEXT.lower()
    assert "inventory motion and resolution motion are different jobs" in text
    assert "inventory motion is work whose purpose is to discover, name, structure, and organize" in text
    assert "inventory motion may record candidate values and likely work items" in text
    assert "resolution motion is work whose purpose is to learn, prove, localize, inspect, delegate" in text
    assert "if the move is meant to decide whether a specific atom is true" in text
    assert "cropping a specific value so it can be read" in text
    assert "a partial universe is not permission to begin resolving the favorite item" in text
    assert "stay in inventory motion" in text
    assert "enter resolution motion" in text
    assert "moving from inventory motion into resolution motion is an authored commitment" in text
    assert "retroflect immediately" in text


def test_harness_surface_teaches_user_messages_and_resolution_course() -> None:
    text = _HARNESS_TRUNK_METHOD_TEXT.lower()
    assert "user messages are first-class run information" in text
    assert "highest-signal input for the run" in text
    assert "do not quietly override user-provided information" in text
    assert "resolution motion should have a course" in text
    assert "not just reactions" in text
    assert "reset the method from a cleaner view of the landscape" in text
    assert "better trial quality, not surrender" in text


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
    # evidence law (closing line preserves the evidence-local handle)
    assert "evidence-local earned claims are the only earned claims this harness respects" in text
    assert "direct inspectability" in text
    assert "false determination" in text
    assert "falsely earned unit is dangerous" in text
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
    assert "false determination — false earned certainty — is a common agent failure mode" in lowered
    assert "broad familiarity with the source" in lowered
    assert "locally and directly inspectable" in lowered
    assert "consider delegation the normal high-signal path" in lowered
    assert "smaller neutral task and a curated evidence packet" in lowered
    assert "attention quality and token efficiency" in lowered
    assert "this is not ceremony" in lowered
    assert "falsely earned unit is dangerous" in lowered


def test_surface_teaches_the_evidence_law() -> None:
    """The Evidence Law is the single canonical home of evidence/localization doctrine."""
    lowered = _HARNESS_TRUNK_METHOD_TEXT.lower()
    assert lowered.count("## the evidence law") == 1
    # the five old homes are gone; their handles live as beats inside the law
    assert "## mission-critical exactness" not in lowered
    assert "## decisive-detail localization" not in lowered
    assert "## defensible evidence rule" not in lowered
    assert "## orientation evidence vs claim-local evidence" not in lowered
    assert "## evidence-local earned claims" not in lowered
    # the law's spine
    assert "localize first, then determine" in lowered
    assert "evidence is the method of determination, not a decoration attached after the fact" in lowered
    assert "evidence cannot be retroactive" in lowered
    assert "a locator attached after closure is not proof that closure was valid" in lowered
    assert "evidence-local earned claims are the only earned claims this harness respects" in lowered
    # orientation vs claim-local
    assert "orientation evidence helps you find the right area" in lowered
    assert "do not dress a signpost up as proof" in lowered
    # the goal line
    assert "the goal is to make it hard for a wrong exact value to survive" in lowered


def test_evidence_law_section_has_no_domain_examples() -> None:
    lowered = _HARNESS_TRUNK_METHOD_TEXT.lower()
    start = lowered.find("## the evidence law")
    end = lowered.find("## source-observed vs downstream-usable lanes")
    assert start >= 0, "the evidence law section must exist"
    assert end > start, "source/downstream lanes section should follow the evidence law"
    section = lowered[start:end]
    # union of the old per-section banned lists; " bearing" spaced to allow "load-bearing"
    for banned in ("deed", "parcel", "range", " bearing", "distance", "acreage", "plss", "transcript"):
        assert banned not in section, f"Found banned term {banned!r} in evidence law doctrine"


def test_surface_teaches_decisive_detail_localization() -> None:
    text = _HARNESS_TRUNK_METHOD_TEXT
    lowered = text.lower()
    assert "decisive-detail localization" in lowered
    assert "smallest decisive detail" in lowered
    assert "common agent failure mode, not a theoretical edge case" in lowered
    assert "does not prove the decisive atom" in lowered
    assert "point of difference" in lowered
    assert "isolate the decisive detail" in lowered


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
    assert "latest_action_results" in text
    assert "projection windows" in lowered or "not boundary assertions" in lowered
    assert "absent from a bounded view" in lowered or "absent from the source" in lowered
    assert "artifact_excerpt_boundary_risk" not in text


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


def test_surface_compact_claim_atoms_section_has_no_domain_examples() -> None:
    lowered = _HARNESS_TRUNK_METHOD_TEXT.lower()
    start = lowered.find("## compact claim atoms")
    end = lowered.find("## inventory gate and resolution motion")
    assert start >= 0, "compact claim atoms section must exist"
    assert end > start, "inventory gate section should follow compact claim atoms"
    section = lowered[start:end]
    for banned in ("deed", "parcel", "range", "bearing", "distance", "cutoff", "mapping"):
        assert banned not in section, f"Found banned term {banned!r} in compact claim atom doctrine"


def test_surface_compact_claim_atoms_is_the_single_field_semantics_home() -> None:
    """Field semantics are taught once, natively, in the compact-claim-atoms law."""
    lowered = _HARNESS_TRUNK_METHOD_TEXT.lower()
    assert lowered.count("## compact claim atoms") == 1
    assert "## field roles" not in lowered
    assert "## prompt work-graph projection" not in lowered
    section = lowered[lowered.find("## compact claim atoms"):]
    assert "compact projection of durable state" in section
    assert "reopen or patch the row rather than silently overwriting" in section


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
    end = lowered.find("## evidence refs vs evidence locators")
    assert start >= 0, "source/downstream lane section must exist in method text"
    assert end > start, "evidence locator section must follow source/downstream lane section"
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
