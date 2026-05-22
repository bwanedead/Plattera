"""Phase 6 mechanical checks: transcript-edit profile composes and projects end-to-end."""

from __future__ import annotations

import json

from domains.mapping.transcript_edit import build_transcript_edit_domain_pack
from harness.runtime.orchestration.subtasks.contracts import DelegateSubtaskRequest
from harness.runtime.orchestration.subtasks.projection import project_subtask_output
from harness.runtime.orchestration.subtasks.registry import build_composed_subtask_registry
from harness.runtime.orchestration.subtasks.runner import normalize_child_output


def test_transcript_edit_surface_exposes_visual_source_observation_profile() -> None:
    payload = build_transcript_edit_domain_pack().build_surface_payload()
    assert isinstance(payload.get("subtask_profiles"), list)
    profile_ids = {row["profile_id"] for row in payload["subtask_profiles"]}
    assert "transcript_edit.visual_source_observation" in profile_ids


def test_composed_registry_and_projection_preserve_custom_fields() -> None:
    payload = build_transcript_edit_domain_pack().build_surface_payload()
    registry = build_composed_subtask_registry(surface_payloads={"transcript_edit": payload})
    profile = registry.require("transcript_edit.visual_source_observation")

    normalized = normalize_child_output(
        json.dumps(
            {
                "status": "completed",
                "result": {
                    "task_response": "The visible bearing reads N. 4° 00' W.",
                    "source_visible_text": "N. 4° 00' W.",
                    "visual_basis": ["degree numeral stroke resembles a 4"],
                    "ambiguity": "",
                    "limits": [],
                },
            }
        ),
        subtask_id="blind_p1_bearing_read",
        request=DelegateSubtaskRequest(
            profile=profile.profile_id,
            task=(
                "Read the bearing text visible in the supplied localized crop. "
                "Preserve the source-visible text as written."
            ),
            context_refs=("image:derived:5d79cd203e114c529042676fb06c217f",),
            isolation={
                "omit_parent_graph": True,
                "omit_peer_candidates": True,
                "omit_parent_closure_ledger": True,
                "omit_broad_doctrine": True,
            },
            output_contract={
                "kind": "visual_source_observation",
                "need": "source-visible reading and visual basis",
            },
        ),
        profile=profile,
    )

    projected = project_subtask_output(normalized)
    assert projected is not None
    assert projected["profile"] == "transcript_edit.visual_source_observation"
    assert projected["result"]["source_visible_text"] == "N. 4° 00' W."
    assert projected["result"]["visual_basis"] == ["degree numeral stroke resembles a 4"]
    assert "confidence" not in projected["result"]
