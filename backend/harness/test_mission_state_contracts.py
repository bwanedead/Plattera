from __future__ import annotations

import pytest
from pydantic import ValidationError

from harness.mission_state import (
    MISSION_STATE_VERSION,
    RESOLUTION_STATE_VERSION,
    MissionState,
    new_mission_state,
    new_resolution_state,
    resolution_state_from_legacy_items,
)


def test_resolution_state_serializes_with_active_item_id_and_relations() -> None:
    resolution_state = new_resolution_state(
        active_item_id="item:range",
        items=[
            {
                "item_id": "item:range",
                "title": "Range",
                "kind": "work_item",
                "status": "waiting_feedback",
                "summary": "Awaiting confirmation",
                "history": [
                    {
                        "event_kind": "snapshot",
                        "summary": "row carried forward",
                        "outcome": "waiting_feedback",
                    }
                ],
                "domain_payload": {"source": "test"},
            }
        ],
        relations=[
            {
                "source_item_id": "item:range",
                "target_item_id": "item:township",
                "relation_type": "depends_on",
                "summary": "Range depends on township resolution",
            }
        ],
        domain_payload={"source": "test"},
    )

    assert resolution_state.schema_version == RESOLUTION_STATE_VERSION
    dumped = resolution_state.model_dump()
    assert dumped["active_item_id"] == "item:range"
    assert dumped["items"][0]["history"][0]["event_kind"] == "snapshot"
    assert dumped["relations"][0]["relation_type"] == "depends_on"


def test_mission_state_wraps_resolution_state_without_extra_fields() -> None:
    mission_state = new_mission_state(
        mission_id="mission-1",
        loop_family="mission_runtime",
        objective="shared continuity contract",
        active_mode="deed_to_ir",
        resolution_state=resolution_state_from_legacy_items(
            items=[
                {
                    "item_id": "item:active",
                    "title": "Active item",
                    "kind": "work_item",
                    "status": "open",
                }
            ],
            active_item_id="item:active",
        ),
        domain_payload={"source": "test"},
    )

    assert mission_state.schema_version == MISSION_STATE_VERSION
    assert mission_state.resolution_state.active_item_id == "item:active"
    assert mission_state.domain_payload == {"source": "test"}

    with pytest.raises(ValidationError):
        MissionState.model_validate(
            {
                "mission_id": "mission-2",
                "loop_family": "mission_runtime",
                "unexpected": "field",
            }
        )
