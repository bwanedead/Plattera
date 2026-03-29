from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.domains.mapping.transcript_edit.decision_ledger import initialize_decision_ledger_with_domain_template_seed
from backend.domains.mapping.transcript_edit.work_board_projection import (
    active_work_board_item_for_focus,
    active_work_board_item_for_key,
    project_decision_ledger_to_work_board,
)
from backend.harness.mission_state.resolution_projection import (
    RESOLUTION_PROJECTION_VERSION,
    new_resolution_projection,
    resolution_item_row_dict,
)


def test_project_ledger_preserves_item_count_and_ids() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    board = project_decision_ledger_to_work_board(ledger)
    assert board["schema_version"] == RESOLUTION_PROJECTION_VERSION
    assert board["domain_projection"] == "transcript_edit.decision_ledger"
    assert len(board["items"]) == len(ledger["items"])
    keys = {str(i["key"]) for i in ledger["items"]}
    ids = {str(row["domain_payload"]["decision_key"]) for row in board["items"]}
    assert keys == ids


def test_active_item_lookup() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    board = project_decision_ledger_to_work_board(ledger)
    row = active_work_board_item_for_key(board, "range")
    assert row is not None
    assert row["item_id"] == "te:ledger:range"
    assert row["kind"] == "transcript_edit.decision_item"


def test_active_work_board_item_for_focus_resolves_emergent_id() -> None:
    row = resolution_item_row_dict(
        item_id="harness:emergent:deadbeef0001",
        title="Emergent row",
        kind="t",
        state="open",
        materiality="high",
        blocking_impact="mapping_blocking",
        provenance="harness.emergent.v1",
    )
    board = new_resolution_projection(domain_projection="test", items=[row])
    got = active_work_board_item_for_focus(board, "harness:emergent:deadbeef0001")
    assert got is not None
    assert got.get("item_id") == "harness:emergent:deadbeef0001"


def test_disputed_maps_to_blocked_board_state() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    for item in ledger["items"]:
        if str(item.get("key")) == "township":
            item["state"] = "disputed"
            break
    board = project_decision_ledger_to_work_board(ledger)
    tw = active_work_board_item_for_key(board, "township")
    assert tw is not None
    assert tw["state"] == "blocked"

