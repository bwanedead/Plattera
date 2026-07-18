"""Deterministic coverage for inert pending result delivery substrate."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from harness.execution.agent_result_view import (
    MAX_AGENT_RESULT_VIEW_CHARS,
    OMISSION_REASON_INVALID_SHAPE,
    OMISSION_REASON_NOT_JSON_SAFE,
    OMISSION_REASON_VIEW_BUDGET,
    AgentResultView,
    AgentResultViewOmission,
    build_agent_result_view,
)
from harness.execution.contracts import ActionDispatchResult
from harness.runtime.memory.result_delivery import (
    MAX_DELIVERY_ARTIFACT_REFS,
    MAX_DELIVERY_OUTPUT_KEYS,
    MAX_LATEST_ACTION_RESULTS_CHARS,
    MAX_PENDING_RESULT_DELIVERIES,
    MAX_RESULT_CONTACTS,
    MIN_REQUIRED_RESULT_CONTACTS,
    REASON_CAPACITY_EXCEEDED,
    REASON_INVALID_VIEW,
    REASON_MISSING_VIEW,
    REPRESENTATION_AGENT_RESULT_VIEW,
    REPRESENTATION_EXACT_OUTPUTS,
    REPRESENTATION_UNAVAILABLE,
    acknowledge_result_delivery_contacts,
    admit_pending_result_delivery,
    make_delivery_id,
    measure_compact_json_chars,
    project_latest_action_results,
    validate_stored_pending_result_delivery,
)


def _result(
    *,
    outputs: dict | None = None,
    view: AgentResultView | None = None,
    omitted: AgentResultViewOmission | None = None,
    artifact_refs: tuple[str, ...] = (),
    image_evidence: tuple[dict, ...] = (),
    action_id: str = "tool_a",
) -> ActionDispatchResult:
    return ActionDispatchResult(
        action_id=action_id,
        executed=True,
        outputs=dict(outputs or {}),
        artifact_refs=artifact_refs,
        image_evidence=image_evidence,
        agent_result_view=view,
        agent_result_view_omitted=omitted,
    )


def _pad_outputs(chars: int) -> dict:
    base = {"pad": ""}
    overhead = measure_compact_json_chars(base)
    return {"pad": "x" * (chars - overhead)}


def test_small_output_selects_exact_outputs() -> None:
    deliveries: list[dict] = []
    out = admit_pending_result_delivery(
        deliveries,
        result=_result(outputs={"ok": True}),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    assert out.status == "admitted"
    assert deliveries[0]["representation_kind"] == REPRESENTATION_EXACT_OUTPUTS
    assert deliveries[0]["representation"] == {"ok": True}


def test_exact_12000_char_output_boundary() -> None:
    outputs = _pad_outputs(MAX_AGENT_RESULT_VIEW_CHARS)
    assert measure_compact_json_chars(outputs) == MAX_AGENT_RESULT_VIEW_CHARS
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs=outputs),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    assert deliveries[0]["representation_kind"] == REPRESENTATION_EXACT_OUTPUTS


def test_one_over_uses_valid_provider_view() -> None:
    outputs = _pad_outputs(MAX_AGENT_RESULT_VIEW_CHARS + 1)
    view, omitted = build_agent_result_view(
        schema_id="test.view.v1",
        payload={"summary": "provider"},
        continuity_key="map:current",
    )
    assert omitted is None and view is not None
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs=outputs, view=view),
        source_turn_index=2,
        action_index=1,
        action_alias="review",
        execution_state="executed",
    )
    assert deliveries[0]["representation_kind"] == REPRESENTATION_AGENT_RESULT_VIEW
    assert deliveries[0]["continuity_key"] == "map:current"
    assert deliveries[0]["representation"]["payload"] == {"summary": "provider"}


def test_large_output_without_view_is_unavailable() -> None:
    outputs = _pad_outputs(MAX_AGENT_RESULT_VIEW_CHARS + 1)
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs=outputs),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    assert deliveries[0]["representation_kind"] == REPRESENTATION_UNAVAILABLE
    assert deliveries[0]["representation"]["reason"] == REASON_MISSING_VIEW
    assert "xxxx" not in json.dumps(deliveries[0]["representation"])
    assert deliveries[0]["representation"].get("pad") is None


def test_invalid_view_marker() -> None:
    outputs = _pad_outputs(MAX_AGENT_RESULT_VIEW_CHARS + 1)
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(
            outputs=outputs,
            omitted=AgentResultViewOmission(reason="invalid_shape"),
        ),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    assert deliveries[0]["representation"]["reason"] == REASON_INVALID_VIEW
    assert deliveries[0]["representation"]["view_omission"]["reason"] == "invalid_shape"


def test_small_exact_despite_malformed_optional_view() -> None:
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(
            outputs={"ok": True},
            omitted=AgentResultViewOmission(reason="not_json_safe"),
        ),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    assert deliveries[0]["representation_kind"] == REPRESENTATION_EXACT_OUTPUTS
    assert deliveries[0]["representation"] == {"ok": True}
    assert deliveries[0]["view_omission_reason"] == "not_json_safe"


def test_image_evidence_excluded() -> None:
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(
            outputs={"ok": True},
            image_evidence=({"ref_id": "i", "b64": "AAAA"},),
        ),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    blob = json.dumps(deliveries[0])
    assert "AAAA" not in blob
    assert "image_evidence" not in deliveries[0]


def test_refs_deduped_and_bounded() -> None:
    refs = tuple(f"artifact://ref-{i}" for i in range(MAX_DELIVERY_ARTIFACT_REFS + 5))
    refs = ("artifact://dup", "artifact://dup") + refs
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs={"ok": True}, artifact_refs=refs),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    assert len(deliveries[0]["artifact_refs"]) == MAX_DELIVERY_ARTIFACT_REFS
    assert deliveries[0]["artifact_refs_omitted_count"] >= 5
    assert deliveries[0]["artifact_refs"][0] == "artifact://dup"


def test_output_key_inventory_bounded() -> None:
    outputs = {f"k{i}": i for i in range(MAX_DELIVERY_OUTPUT_KEYS + 10)}
    # Force unavailable path with oversized pad + keys.
    outputs["pad"] = "x" * (MAX_AGENT_RESULT_VIEW_CHARS + 1)
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs=outputs),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    marker = deliveries[0]["representation"]
    assert len(marker["output_keys"]) == MAX_DELIVERY_OUTPUT_KEYS
    assert marker["output_keys_omitted_count"] >= 10


def test_same_delivery_id_idempotent() -> None:
    deliveries: list[dict] = []
    kwargs = dict(
        result=_result(outputs={"ok": True}),
        source_turn_index=4,
        action_index=1,
        action_alias="review_mapping",
        execution_state="executed",
    )
    first = admit_pending_result_delivery(deliveries, **kwargs)
    deliveries[0]["successful_content_contact_ids"] = ["prior"]
    second = admit_pending_result_delivery(deliveries, **kwargs)
    assert first.status == "admitted"
    assert second.status == "idempotent"
    assert len(deliveries) == 1
    assert deliveries[0]["successful_content_contact_ids"] == ["prior"]


def test_same_continuity_key_supersedes() -> None:
    view1, _ = build_agent_result_view(
        schema_id="t.v1", payload={"n": 1}, continuity_key="map:current"
    )
    view2, _ = build_agent_result_view(
        schema_id="t.v1", payload={"n": 2}, continuity_key="map:current"
    )
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs=_pad_outputs(MAX_AGENT_RESULT_VIEW_CHARS + 1), view=view1),
        source_turn_index=1,
        action_index=0,
        action_alias="old",
        execution_state="executed",
    )
    deliveries[0]["successful_content_contact_ids"] = ["prior"]
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs=_pad_outputs(MAX_AGENT_RESULT_VIEW_CHARS + 1), view=view2),
        source_turn_index=2,
        action_index=0,
        action_alias="new",
        execution_state="executed",
    )
    assert len(deliveries) == 1
    assert deliveries[0]["action_alias"] == "new"
    assert deliveries[0]["successful_content_contact_ids"] == []
    assert deliveries[0]["representation"]["payload"] == {"n": 2}


def test_different_keys_coexist() -> None:
    a, _ = build_agent_result_view(schema_id="t.v1", payload={"a": 1}, continuity_key="k:a")
    b, _ = build_agent_result_view(schema_id="t.v1", payload={"b": 1}, continuity_key="k:b")
    big = _pad_outputs(MAX_AGENT_RESULT_VIEW_CHARS + 1)
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs=big, view=a),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs=big, view=b, action_id="tool_b"),
        source_turn_index=1,
        action_index=1,
        action_alias="b",
        execution_state="executed",
    )
    assert len(deliveries) == 2


def test_keyless_do_not_supersede() -> None:
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs={"a": 1}),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs={"b": 1}, action_id="tool_b"),
        source_turn_index=2,
        action_index=0,
        action_alias="b",
        execution_state="executed",
    )
    assert len(deliveries) == 2


def test_renderer_does_not_mutate_state() -> None:
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs={"ok": True}),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    before = json.dumps(deliveries, sort_keys=True)
    project_latest_action_results(deliveries)
    assert json.dumps(deliveries, sort_keys=True) == before


def test_first_contact_retains() -> None:
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs={"ok": True}),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    proj = project_latest_action_results(deliveries)
    acknowledge_result_delivery_contacts(
        deliveries,
        contact_id="c1",
        receipt=proj.contact_receipt,
        active_attention_refs=set(),
    )
    assert len(deliveries) == 1
    assert deliveries[0]["successful_content_contact_ids"] == ["c1"]


def test_second_contact_removes_when_not_hot() -> None:
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs={"ok": True}, artifact_refs=("artifact://x",)),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    for cid in ("c1", "c2"):
        proj = project_latest_action_results(deliveries)
        acknowledge_result_delivery_contacts(
            deliveries,
            contact_id=cid,
            receipt=proj.contact_receipt,
            active_attention_refs=set(),
        )
    assert deliveries == []


def test_hot_ref_retains_after_contact_two() -> None:
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs={"ok": True}, artifact_refs=("artifact://hot",)),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    for cid in ("c1", "c2"):
        proj = project_latest_action_results(deliveries)
        acknowledge_result_delivery_contacts(
            deliveries,
            contact_id=cid,
            receipt=proj.contact_receipt,
            active_attention_refs={"artifact://hot"},
        )
    assert len(deliveries) == 1
    assert deliveries[0]["successful_content_contact_ids"] == ["c1", "c2"]


def test_hot_expires_after_eight_contacts() -> None:
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs={"ok": True}, artifact_refs=("artifact://hot",)),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    for i in range(MAX_RESULT_CONTACTS):
        proj = project_latest_action_results(deliveries)
        acknowledge_result_delivery_contacts(
            deliveries,
            contact_id=f"c{i}",
            receipt=proj.contact_receipt,
            active_attention_refs={"artifact://hot"},
        )
    assert deliveries == []


def test_nonmatching_refs_do_not_extend() -> None:
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs={"ok": True}, artifact_refs=("artifact://a",)),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    for cid in ("c1", "c2"):
        proj = project_latest_action_results(deliveries)
        acknowledge_result_delivery_contacts(
            deliveries,
            contact_id=cid,
            receipt=proj.contact_receipt,
            active_attention_refs={"artifact://other"},
        )
    assert deliveries == []


def test_duplicate_contact_id_does_not_double_count() -> None:
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs={"ok": True}),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    proj = project_latest_action_results(deliveries)
    acknowledge_result_delivery_contacts(
        deliveries, contact_id="same", receipt=proj.contact_receipt, active_attention_refs=set()
    )
    acknowledge_result_delivery_contacts(
        deliveries, contact_id="same", receipt=proj.contact_receipt, active_attention_refs=set()
    )
    assert deliveries[0]["successful_content_contact_ids"] == ["same"]


def test_lane_budget_marker_does_not_count() -> None:
    deliveries: list[dict] = []
    # Build enough near-max views that the 64k collection must spill some rows.
    for i in range(12):
        view, _ = build_agent_result_view(
            schema_id="t.v1",
            payload={"pad": "y" * 10000, "i": i},
            continuity_key=f"k:{i}",
        )
        admit_pending_result_delivery(
            deliveries,
            result=_result(
                outputs=_pad_outputs(MAX_AGENT_RESULT_VIEW_CHARS + 1),
                view=view,
                action_id=f"tool_{i}",
            ),
            source_turn_index=i,
            action_index=0,
            action_alias=f"a{i}",
            execution_state="executed",
        )
    proj = project_latest_action_results(deliveries)
    assert proj.serialized_chars <= MAX_LATEST_ACTION_RESULTS_CHARS
    assert proj.contact_receipt.lane_budget_delivery_ids
    before = {d["delivery_id"]: list(d.get("successful_content_contact_ids") or []) for d in deliveries}
    acknowledge_result_delivery_contacts(
        deliveries,
        contact_id="c-lane",
        receipt=proj.contact_receipt,
        active_attention_refs=set(),
    )
    after = {d["delivery_id"]: list(d.get("successful_content_contact_ids") or []) for d in deliveries}
    for did in proj.contact_receipt.lane_budget_delivery_ids:
        assert after[did] == before[did]


def test_intrinsic_unavailable_does_count() -> None:
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs=_pad_outputs(MAX_AGENT_RESULT_VIEW_CHARS + 1)),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    assert deliveries[0]["representation_kind"] == REPRESENTATION_UNAVAILABLE
    proj = project_latest_action_results(deliveries)
    assert deliveries[0]["delivery_id"] in proj.contact_receipt.content_exposed_delivery_ids
    acknowledge_result_delivery_contacts(
        deliveries, contact_id="c1", receipt=proj.contact_receipt, active_attention_refs=set()
    )
    assert deliveries[0]["successful_content_contact_ids"] == ["c1"]


def test_five_action_batch_preserves_all_aliases() -> None:
    deliveries: list[dict] = []
    for i in range(5):
        admit_pending_result_delivery(
            deliveries,
            result=_result(outputs={"i": i}, action_id=f"tool_{i}"),
            source_turn_index=9,
            action_index=i,
            action_alias=f"alias_{i}",
            execution_state="executed",
        )
    proj = project_latest_action_results(deliveries)
    aliases = {row["action_alias"] for row in proj.latest_action_results}
    assert aliases == {f"alias_{i}" for i in range(5)}


def test_multi_turn_lane_pressure_fairly_rotates() -> None:
    deliveries: list[dict] = []
    for i in range(6):
        view, _ = build_agent_result_view(
            schema_id="t.v1",
            payload={"pad": "z" * 9000, "i": i},
            continuity_key=f"fair:{i}",
        )
        admit_pending_result_delivery(
            deliveries,
            result=_result(
                outputs=_pad_outputs(MAX_AGENT_RESULT_VIEW_CHARS + 1),
                view=view,
                action_id=f"tool_{i}",
            ),
            source_turn_index=i,
            action_index=0,
            action_alias=f"a{i}",
            execution_state="executed",
        )
    first = project_latest_action_results(deliveries)
    acknowledge_result_delivery_contacts(
        deliveries, contact_id="fair-1", receipt=first.contact_receipt, active_attention_refs=set()
    )
    second = project_latest_action_results(deliveries)
    # Rows that received detail first should yield to still-undelivered rows.
    first_content = set(first.contact_receipt.content_exposed_delivery_ids)
    second_content = set(second.contact_receipt.content_exposed_delivery_ids)
    if first_content and second.contact_receipt.lane_budget_delivery_ids:
        assert second_content - first_content or first_content != second_content
    assert second.serialized_chars <= MAX_LATEST_ACTION_RESULTS_CHARS
    assert {r["action_alias"] for r in second.latest_action_results} == {f"a{i}" for i in range(6)}


def test_complete_serialized_lane_never_exceeds_budget() -> None:
    deliveries: list[dict] = []
    for i in range(10):
        view, _ = build_agent_result_view(
            schema_id="t.v1",
            payload={"pad": "q" * 8000, "i": i},
            continuity_key=f"cap:{i}",
        )
        admit_pending_result_delivery(
            deliveries,
            result=_result(
                outputs=_pad_outputs(MAX_AGENT_RESULT_VIEW_CHARS + 1),
                view=view,
                action_id=f"tool_{i}",
            ),
            source_turn_index=i,
            action_index=0,
            action_alias=f"a{i}",
            execution_state="executed",
        )
    proj = project_latest_action_results(deliveries)
    assert proj.serialized_chars <= MAX_LATEST_ACTION_RESULTS_CHARS
    assert measure_compact_json_chars(proj.latest_action_results) == proj.serialized_chars


def test_no_partial_json_or_output_prefixes() -> None:
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs=_pad_outputs(MAX_AGENT_RESULT_VIEW_CHARS + 50)),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    marker = deliveries[0]["representation"]
    assert marker["reason"] == REASON_MISSING_VIEW
    assert "pad" not in marker
    assert "xxxx" not in json.dumps(marker)


def test_capacity_evicts_already_contacted_first() -> None:
    deliveries: list[dict] = []
    for i in range(MAX_PENDING_RESULT_DELIVERIES):
        admit_pending_result_delivery(
            deliveries,
            result=_result(outputs={"i": i}, action_id=f"tool_{i}"),
            source_turn_index=i,
            action_index=0,
            action_alias=f"a{i}",
            execution_state="executed",
        )
        deliveries[-1]["successful_content_contact_ids"] = ["c1", "c2"]
    assert len(deliveries) == MAX_PENDING_RESULT_DELIVERIES
    out = admit_pending_result_delivery(
        deliveries,
        result=_result(outputs={"new": True}, action_id="tool_new"),
        source_turn_index=999,
        action_index=0,
        action_alias="new",
        execution_state="executed",
    )
    assert out.status == "admitted"
    assert any(d["action_alias"] == "new" for d in deliveries)
    assert len(deliveries) == MAX_PENDING_RESULT_DELIVERIES


def test_capacity_refuses_rather_than_evicting_undelivered() -> None:
    deliveries: list[dict] = []
    for i in range(MAX_PENDING_RESULT_DELIVERIES):
        admit_pending_result_delivery(
            deliveries,
            result=_result(outputs={"i": i}, action_id=f"tool_{i}"),
            source_turn_index=i,
            action_index=0,
            action_alias=f"a{i}",
            execution_state="executed",
        )
    before = json.dumps(deliveries, sort_keys=True, separators=(",", ":"))
    out = admit_pending_result_delivery(
        deliveries,
        result=_result(outputs={"new": True}, action_id="tool_new"),
        source_turn_index=999,
        action_index=0,
        action_alias="new",
        execution_state="executed",
    )
    assert out.status == "rejected"
    assert out.reason_code == REASON_CAPACITY_EXCEEDED
    assert json.dumps(deliveries, sort_keys=True, separators=(",", ":")) == before
    assert all(d["action_alias"] != "new" for d in deliveries)


def test_validate_stored_round_trip_shape() -> None:
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs={"ok": True}, artifact_refs=("artifact://x",)),
        source_turn_index=4,
        action_index=1,
        action_alias="review_mapping",
        execution_state="executed",
    )
    normalized = validate_stored_pending_result_delivery(deliveries[0])
    assert normalized is not None
    assert normalized["delivery_id"] == make_delivery_id(
        source_turn_index=4, action_index=1, action_alias="review_mapping"
    )


def test_module_has_no_domain_or_tooling_imports() -> None:
    source = Path(__file__).with_name("result_delivery.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    banned_substrings = ("transcript_edit", "deed_to_ir")

    def _has_banned_segment(module_name: str) -> bool:
        parts = [part for part in module_name.split(".") if part]
        return "domains" in parts or "tooling" in parts

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not _has_banned_segment(alias.name)
                assert not any(s in alias.name for s in banned_substrings)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not _has_banned_segment(module)
            assert not any(s in module for s in banned_substrings)


def _canonical_max_identity_row(i: int) -> dict:
    from harness.runtime.memory.result_delivery import (
        MAX_ACTION_ALIAS_CHARS,
        MAX_ACTION_ID_CHARS,
        MAX_DELIVERY_ID_CHARS,
        MAX_EXECUTION_STATE_CHARS,
        PENDING_RESULT_DELIVERY_SCHEMA_VERSION,
    )

    alias = ("a" * MAX_ACTION_ALIAS_CHARS)[:-len(str(i))] + str(i)
    action_id = ("t" * MAX_ACTION_ID_CHARS)[:-len(str(i))] + str(i)
    delivery_id = f"turn:{i}:action:0:{alias}"
    assert len(delivery_id) <= MAX_DELIVERY_ID_CHARS
    return {
        "schema_version": PENDING_RESULT_DELIVERY_SCHEMA_VERSION,
        "delivery_id": delivery_id,
        "source_turn_index": i,
        "action_index": 0,
        "action_alias": alias,
        "action_id": action_id,
        "execution_state": "e" * MAX_EXECUTION_STATE_CHARS,
        "executed": True,
        "reason_codes": [],
        "reason_codes_omitted_count": 0,
        "refusal": None,
        "artifact_refs": [f"artifact://ref-{i}"],
        "artifact_refs_omitted_count": 0,
        "representation_kind": REPRESENTATION_EXACT_OUTPUTS,
        "representation": {"ok": True, "i": i},
        "continuity_key": None,
        "successful_content_contact_ids": [],
    }


def test_collection_cap_holds_for_32_max_metadata_rows() -> None:
    from harness.runtime.memory.result_delivery import REASON_LANE_BUDGET_AGGREGATE

    rows = [_canonical_max_identity_row(i) for i in range(MAX_PENDING_RESULT_DELIVERIES)]
    for row in rows:
        assert validate_stored_pending_result_delivery(row) is not None
    proj = project_latest_action_results(rows)
    assert proj.serialized_chars <= MAX_LATEST_ACTION_RESULTS_CHARS
    assert len(proj.latest_action_results) == MAX_PENDING_RESULT_DELIVERIES
    assert all(
        row.get("representation", {}).get("reason") != REASON_LANE_BUDGET_AGGREGATE
        for row in proj.latest_action_results
    )
    ids = {row["delivery_id"] for row in proj.latest_action_results}
    assert ids == {r["delivery_id"] for r in rows}


def test_corrupt_overlong_identity_falls_to_bounded_aggregate() -> None:
    from harness.runtime.memory.result_delivery import REASON_LANE_BUDGET_AGGREGATE

    rows = []
    for i in range(MAX_PENDING_RESULT_DELIVERIES):
        row = _canonical_max_identity_row(i)
        row["delivery_id"] = "x" * 20_000
        rows.append(row)
    proj = project_latest_action_results(rows)
    assert proj.serialized_chars <= MAX_LATEST_ACTION_RESULTS_CHARS
    assert len(proj.latest_action_results) == 1
    assert proj.latest_action_results[0]["representation"]["reason"] == REASON_LANE_BUDGET_AGGREGATE


def test_continuity_key_never_appears_in_projected_results() -> None:
    secret = "opaque-continuity-key-xyz-never-leak"
    view, _ = build_agent_result_view(
        schema_id="t.v1",
        payload={"summary": "provider", "note": "no key here"},
        continuity_key=secret,
    )
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs=_pad_outputs(MAX_AGENT_RESULT_VIEW_CHARS + 1), view=view),
        source_turn_index=1,
        action_index=0,
        action_alias="review",
        execution_state="executed",
    )
    assert deliveries[0]["continuity_key"] == secret
    assert "continuity_key" in deliveries[0]["representation"]
    proj = project_latest_action_results(deliveries)
    blob = json.dumps(proj.latest_action_results, ensure_ascii=False, sort_keys=True)
    assert "continuity_key" not in blob
    assert secret not in blob
    row = proj.latest_action_results[0]
    assert set(row["representation"].keys()) == {"schema_version", "schema_id", "payload"}


def test_overlong_artifact_ref_omitted_whole_no_prefix() -> None:
    from harness.runtime.memory.result_delivery import MAX_DELIVERY_ARTIFACT_REF_CHARS

    overlong = "artifact://" + ("z" * (MAX_DELIVERY_ARTIFACT_REF_CHARS + 50))
    prefix = overlong[:MAX_DELIVERY_ARTIFACT_REF_CHARS]
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs={"ok": True}, artifact_refs=(overlong, "artifact://ok")),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    stored = deliveries[0]
    assert stored["artifact_refs"] == ["artifact://ok"]
    assert stored["artifact_refs_omitted_count"] == 1
    assert prefix not in json.dumps(stored)
    assert overlong not in json.dumps(stored)
    proj = project_latest_action_results(deliveries)
    blob = json.dumps(proj.latest_action_results)
    assert prefix not in blob
    assert overlong not in blob


def test_lane_budget_makes_ref_suppression_explicit() -> None:
    deliveries: list[dict] = []
    for i in range(12):
        view, _ = build_agent_result_view(
            schema_id="t.v1",
            payload={"pad": "y" * 10000, "i": i},
            continuity_key=f"k:{i}",
        )
        admit_pending_result_delivery(
            deliveries,
            result=_result(
                outputs=_pad_outputs(MAX_AGENT_RESULT_VIEW_CHARS + 1),
                view=view,
                action_id=f"tool_{i}",
                artifact_refs=(f"artifact://hot-{i}",),
            ),
            source_turn_index=i,
            action_index=0,
            action_alias=f"a{i}",
            execution_state="executed",
        )
    proj = project_latest_action_results(deliveries)
    assert proj.contact_receipt.lane_budget_delivery_ids
    for row in proj.latest_action_results:
        if row["delivery_id"] in proj.contact_receipt.lane_budget_delivery_ids:
            assert row["artifact_refs"] == []
            assert row["artifact_refs_omitted_count"] >= 1


def test_nonconsecutive_contact_replay_is_noop() -> None:
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs={"ok": True}, artifact_refs=("artifact://hot",)),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    for cid in ("A", "B", "A"):
        proj = project_latest_action_results(deliveries)
        acknowledge_result_delivery_contacts(
            deliveries,
            contact_id=cid,
            receipt=proj.contact_receipt,
            active_attention_refs={"artifact://hot"},
        )
    assert deliveries[0]["successful_content_contact_ids"] == ["A", "B"]


def test_resume_list_then_replay_older_contact_is_noop() -> None:
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs={"ok": True}, artifact_refs=("artifact://hot",)),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    deliveries[0]["successful_content_contact_ids"] = ["A", "B"]
    normalized = validate_stored_pending_result_delivery(deliveries[0])
    assert normalized is not None
    deliveries[:] = [normalized]
    proj = project_latest_action_results(deliveries)
    acknowledge_result_delivery_contacts(
        deliveries,
        contact_id="A",
        receipt=proj.contact_receipt,
        active_attention_refs={"artifact://hot"},
    )
    assert deliveries[0]["successful_content_contact_ids"] == ["A", "B"]


def test_validate_rejects_oversized_exact_and_extra_fields() -> None:
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs={"ok": True}),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    row = dict(deliveries[0])
    row["representation"] = _pad_outputs(MAX_AGENT_RESULT_VIEW_CHARS + 1)
    assert validate_stored_pending_result_delivery(row) is None

    row2 = dict(deliveries[0])
    row2["extra_field"] = "nope"
    assert validate_stored_pending_result_delivery(row2) is None

    row3 = dict(deliveries[0])
    row3["artifact_refs_omitted_count"] = True
    assert validate_stored_pending_result_delivery(row3) is None

    row4 = dict(deliveries[0])
    row4["artifact_refs_omitted_count"] = "1"
    assert validate_stored_pending_result_delivery(row4) is None

    row5 = dict(deliveries[0])
    row5["artifact_refs"] = ["artifact://ok", "artifact://ok"]
    assert validate_stored_pending_result_delivery(row5) is None

    row6 = dict(deliveries[0])
    row6["artifact_refs"] = ["  padded  "]
    assert validate_stored_pending_result_delivery(row6) is None


def test_validate_rejects_malformed_unavailable_marker() -> None:
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs=_pad_outputs(MAX_AGENT_RESULT_VIEW_CHARS + 1)),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    row = dict(deliveries[0])
    assert row["representation_kind"] == REPRESENTATION_UNAVAILABLE
    bad = dict(row)
    bad["representation"] = dict(row["representation"])
    bad["representation"]["mystery"] = True
    assert validate_stored_pending_result_delivery(bad) is None
    bad2 = dict(row)
    bad2["representation"] = {"reason": REASON_MISSING_VIEW}
    assert validate_stored_pending_result_delivery(bad2) is None


def test_invalid_admission_leaves_pending_list_byte_identical() -> None:
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs={"ok": True}),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    before = json.dumps(deliveries, sort_keys=True, separators=(",", ":"))
    # Force invalid row construction via absurdly long alias (delivery_id / alias bounds).
    out = admit_pending_result_delivery(
        deliveries,
        result=_result(outputs={"ok": True}, action_id="tool_b"),
        source_turn_index=2,
        action_index=0,
        action_alias="x" * 10_000,
        execution_state="executed",
    )
    assert out.status == "rejected"
    assert json.dumps(deliveries, sort_keys=True, separators=(",", ":")) == before


def test_rejects_mismatched_delivery_id() -> None:
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs={"ok": True}),
        source_turn_index=3,
        action_index=1,
        action_alias="alias",
        execution_state="executed",
    )
    row = dict(deliveries[0])
    row["delivery_id"] = "turn:9:action:9:other"
    assert validate_stored_pending_result_delivery(row) is None


def test_projection_preserves_validator_accepted_indices() -> None:
    from harness.runtime.memory.result_delivery import MAX_ACTION_INDEX, MAX_SOURCE_TURN_INDEX

    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs={"ok": True}),
        source_turn_index=MAX_SOURCE_TURN_INDEX,
        action_index=MAX_ACTION_INDEX,
        action_alias="a",
        execution_state="executed",
    )
    assert validate_stored_pending_result_delivery(deliveries[0]) is not None
    proj = project_latest_action_results(deliveries)
    assert proj.latest_action_results[0]["source_turn_index"] == MAX_SOURCE_TURN_INDEX
    assert proj.latest_action_results[0]["action_index"] == MAX_ACTION_INDEX
    assert proj.latest_action_results[0]["delivery_id"] == deliveries[0]["delivery_id"]


def test_rejects_provider_view_continuity_key_mismatch() -> None:
    view, _ = build_agent_result_view(
        schema_id="t.v1", payload={"n": 1}, continuity_key="map:current"
    )
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs=_pad_outputs(MAX_AGENT_RESULT_VIEW_CHARS + 1), view=view),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    row = dict(deliveries[0])
    row["continuity_key"] = "map:other"
    assert validate_stored_pending_result_delivery(row) is None
    row2 = dict(deliveries[0])
    row2["continuity_key"] = None
    assert validate_stored_pending_result_delivery(row2) is None
    row3 = dict(deliveries[0])
    row3["view_omission_reason"] = OMISSION_REASON_INVALID_SHAPE
    assert validate_stored_pending_result_delivery(row3) is None


def test_rejects_unavailable_carrying_continuity_key() -> None:
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs=_pad_outputs(MAX_AGENT_RESULT_VIEW_CHARS + 1)),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    assert deliveries[0]["representation"]["reason"] == REASON_MISSING_VIEW
    row = dict(deliveries[0])
    row["continuity_key"] = "should-not-exist"
    assert validate_stored_pending_result_delivery(row) is None


def test_rejects_inconsistent_invalid_view_omission_reasons() -> None:
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(
            outputs=_pad_outputs(MAX_AGENT_RESULT_VIEW_CHARS + 1),
            omitted=AgentResultViewOmission(reason=OMISSION_REASON_INVALID_SHAPE),
        ),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    assert deliveries[0]["representation"]["reason"] == REASON_INVALID_VIEW
    row = dict(deliveries[0])
    row["view_omission_reason"] = OMISSION_REASON_VIEW_BUDGET
    assert validate_stored_pending_result_delivery(row) is None
    row2 = dict(deliveries[0])
    del row2["view_omission_reason"]
    assert validate_stored_pending_result_delivery(row2) is None


def test_rejects_exact_with_both_continuity_key_and_omission() -> None:
    view, _ = build_agent_result_view(
        schema_id="t.v1", payload={"n": 1}, continuity_key="map:keep"
    )
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs={"ok": True}, view=view),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    assert deliveries[0]["representation_kind"] == REPRESENTATION_EXACT_OUTPUTS
    assert deliveries[0]["continuity_key"] == "map:keep"
    row = dict(deliveries[0])
    row["view_omission_reason"] = OMISSION_REASON_NOT_JSON_SAFE
    assert validate_stored_pending_result_delivery(row) is None


def test_rejects_coercible_but_noncanonical_refusal() -> None:
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=_result(outputs={"ok": True}),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    row = dict(deliveries[0])
    row["refusal"] = {
        "reason_code": "blocked",
        "retryable": "false",
        "blocked_by_budget": False,
        "blocked_by_invariant": False,
        "missing_inputs": [],
    }
    assert validate_stored_pending_result_delivery(row) is None
    row2 = dict(deliveries[0])
    row2["refusal"] = {
        "reason_code": "blocked",
        "retryable": False,
        "blocked_by_budget": False,
        "blocked_by_invariant": False,
        "missing_inputs": "need-x",
    }
    assert validate_stored_pending_result_delivery(row2) is None


def test_reason_codes_omitted_count_is_tracked_and_projected() -> None:
    from harness.execution.contracts import ActionDispatchResult
    from harness.runtime.memory.result_delivery import MAX_REASON_CODE_CHARS, MAX_REASON_CODES

    overlong = "r" * (MAX_REASON_CODE_CHARS + 1)
    codes = tuple(f"code_{i}" for i in range(MAX_REASON_CODES + 3)) + (overlong, 123)
    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=ActionDispatchResult(
            action_id="tool_a",
            executed=True,
            outputs={"ok": True},
            reason_codes=codes,
        ),
        source_turn_index=1,
        action_index=0,
        action_alias="a",
        execution_state="executed",
    )
    row = deliveries[0]
    assert len(row["reason_codes"]) == MAX_REASON_CODES
    assert row["reason_codes_omitted_count"] == 5  # 3 excess + overlong + non-string
    assert validate_stored_pending_result_delivery(row) is not None
    proj = project_latest_action_results(deliveries)
    assert proj.latest_action_results[0]["reason_codes_omitted_count"] == 5
    assert "reason_codes" in proj.latest_action_results[0]
