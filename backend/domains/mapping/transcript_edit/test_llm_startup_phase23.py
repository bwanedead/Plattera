"""Phase 23: LLM-authored startup — unit tests (no live LLM)."""
from __future__ import annotations

from domains.mapping.transcript_edit.blocker_registry_state import initialize_blocker_registry
from domains.mapping.transcript_edit.decision_ledger_state import initialize_decision_ledger, update_ledger_from_iteration
from domains.mapping.transcript_edit.llm_startup_understanding import (
    apply_llm_startup_to_ledger_and_registry,
    coerce_startup_understanding,
    emergent_blocker_updates_from_llm_blockers,
    fallback_decision_key_for_startup_merge,
    native_rows_from_llm_initial_ledger_items,
    startup_understanding_has_minimum_viable,
)
from domains.mapping.transcript_edit.transcript_edit_ledger_discovery_prep import (
    DISCOVERY_ITEM_PROVENANCE,
    infer_discovery_items_from_audit_findings,
    merge_discovery_from_audit_findings,
)


def test_coerce_startup_understanding_bounds_lists() -> None:
    raw = {
        "orientation_brief": "Case overview " * 2000,
        "startup_rationale": "Because " * 500,
        "initial_uncertainties": ["u1", "u2"],
        "initial_ledger_items": [{"title": "T1", "summary": "S1" * 300, "mapping_blocking": True}],
    }
    c = coerce_startup_understanding(raw)
    assert c.get("schema_version")
    assert len(str(c.get("orientation_brief") or "")) <= 4000
    assert isinstance(c.get("initial_ledger_items"), list)


def test_native_rows_from_llm_startup_use_discovery_provenance() -> None:
    rows = native_rows_from_llm_initial_ledger_items(
        [
            {
                "title": "Understand boundary ambiguity",
                "summary": "The deed mixes two range readings; need reconciliation before mapping.",
                "mapping_blocking": True,
            }
        ]
    )
    assert len(rows) == 1
    assert str(rows[0].get("key", "")).startswith("discovery:llm_startup_item:")
    assert rows[0].get("provenance") == DISCOVERY_ITEM_PROVENANCE
    dm = rows[0].get("discovery_meta") if isinstance(rows[0].get("discovery_meta"), dict) else {}
    assert dm.get("kind") == "llm_startup_item"


def test_apply_llm_startup_sets_ledger_sidecar() -> None:
    led = initialize_decision_ledger()
    reg = initialize_blocker_registry(run_id="r1", session_id="s1", source_transcript_ref=None)
    startup = {
        "orientation_brief": "Test case — mineral deed with OCR noise.",
        "initial_ledger_items": [
            {"title": "Confirm section grid", "summary": "Section call may be fractional; verify PLSS grid.", "mapping_blocking": True}
        ],
        "initial_blockers": [
            {
                "title": "Source truncation suspected",
                "reason": "Last page may be missing; need full scan before closure.",
                "blocker_kind": "source_truncation",
                "blocking_class": "source_blocking",
            }
        ],
    }
    led2, reg2 = apply_llm_startup_to_ledger_and_registry(
        ledger=led,
        registry=reg,
        startup=startup,
        fallback_decision_key="range",
    )
    assert isinstance(led2.get("llm_startup_understanding"), dict)
    assert led2.get("initial_ledger_source") == "llm_orient_startup"
    items = led2.get("items") if isinstance(led2.get("items"), list) else []
    assert any(str(it.get("key", "")).startswith("discovery:llm_startup_item:") for it in items if isinstance(it, dict))
    em = reg2.get("emergent") if isinstance(reg2.get("emergent"), dict) else {}
    erows = list(em.get("rows") or []) if isinstance(em, dict) else []
    assert len(erows) >= 1


def test_audit_findings_do_not_seed_ledger_rows() -> None:
    """Phase 24: validator observations never materialize checklist rows via update_ledger_from_iteration."""
    ledger = initialize_decision_ledger()
    finding = {
        "severity": "high",
        "message": "range contradiction between two recorded PLSS readings in the legal description for audit",
    }
    touched = update_ledger_from_iteration(ledger=ledger, findings=[finding])
    items_after = [x for x in (touched.get("items") or []) if isinstance(x, dict)]
    assert not any(str(x.get("key")) == "range" for x in items_after)


def test_merge_discovery_from_audit_is_noop() -> None:
    """Phase 24: validator→discovery merge is disabled."""
    ledger = initialize_decision_ledger()
    finding = {
        "severity": "high",
        "message": "contradiction between candidate bearings and recorded calls in the boundary description for audit",
    }
    assert infer_discovery_items_from_audit_findings([finding]) == []
    merged = merge_discovery_from_audit_findings(ledger, [finding])
    assert isinstance(merged, dict)
    items = [x for x in (merged.get("items") or []) if isinstance(x, dict)]
    assert not any(str(x.get("key", "")).startswith("discovery:") for x in items)


def test_emergent_blocker_updates_use_custom_kind_when_missing() -> None:
    ups = emergent_blocker_updates_from_llm_blockers(
        [{"title": "Blocker title here", "reason": "Detailed reason for the startup blocker here."}],
        fallback_decision_key="range",
    )
    assert len(ups) == 1
    assert ups[0].get("operation") == "add"
    assert str(ups[0].get("blocker_kind", "")).startswith("custom:startup_")


def test_update_ledger_from_iteration_preserves_llm_startup_sidecar() -> None:
    led = initialize_decision_ledger()
    led["llm_startup_understanding"] = {"schema_version": "llm_startup_understanding.v1", "orientation_brief": "x" * 30}
    out = update_ledger_from_iteration(ledger=led, findings=[])
    assert isinstance(out.get("llm_startup_understanding"), dict)
    assert out["llm_startup_understanding"].get("orientation_brief")


def test_blocker_updates_valid_archetype_passes() -> None:
    ups = emergent_blocker_updates_from_llm_blockers(
        [
            {
                "title": "Conflicting tokens",
                "reason": "Two township readings; need evidence to pick dominant reading.",
                "blocker_kind": "conflicting_location_token",
                "blocking_class": "mapping_blocking",
            }
        ],
        fallback_decision_key=None,
    )
    assert ups[0].get("blocker_kind") == "conflicting_location_token"


def test_coerce_merges_candidate_work_items_without_deed_keys() -> None:
    raw = {
        "orientation_brief": "Mineral deed with noisy OCR; mapping hinges on one ambiguous call.",
        "candidate_work_items": [
            {
                "title": "Resolve access easement language",
                "summary": "The servitude description may affect boundary interpretation.",
                "mission_impact": "mapping_critical",
                "suggested_key": "custom_easement_ambiguity",
            }
        ],
    }
    c = coerce_startup_understanding(raw)
    rows = c.get("initial_ledger_items") or []
    assert len(rows) == 1
    assert rows[0].get("suggested_decision_key") == "custom_easement_ambiguity"
    assert startup_understanding_has_minimum_viable(c) is True


def test_apply_llm_startup_generic_work_item_materializes_discovery_row() -> None:
    led = initialize_decision_ledger()
    reg = initialize_blocker_registry(run_id="r1", session_id="s1", source_transcript_ref=None)
    startup = {
        "orientation_brief": "Twenty character brief here ok.",
        "candidate_work_items": [
            {
                "title": "Verify riparian carve-out",
                "summary": "River boundary language may truncate the described tract.",
                "mission_impact": "mapping_blocking",
                "suggested_key": "riparian_edge_case",
            }
        ],
    }
    coerced = coerce_startup_understanding(startup)
    led2, _reg2 = apply_llm_startup_to_ledger_and_registry(
        ledger=led,
        registry=reg,
        startup=startup,
        fallback_decision_key=fallback_decision_key_for_startup_merge(orient_items=[], startup=coerced),
    )
    items = led2.get("items") if isinstance(led2.get("items"), list) else []
    assert any(
        isinstance(it, dict)
        and str(it.get("key", "")).startswith("discovery:llm_startup_item:")
        and (it.get("discovery_meta") or {}).get("suggested_decision_key") == "riparian_edge_case"
        for it in items
    )


def test_fallback_decision_key_from_suggested_key_without_orient_items() -> None:
    su = coerce_startup_understanding(
        {
            "orientation_brief": "x" * 25,
            "candidate_work_items": [{"title": "T", "summary": "S" * 10, "suggested_key": "model_chosen_focus"}],
        }
    )
    assert fallback_decision_key_for_startup_merge(orient_items=[], startup=su) == "model_chosen_focus"

