"""Deterministic coverage for transcript-edit hydrate/transform result views."""

from __future__ import annotations

import json

from harness.execution.agent_result_view import (
    MAX_AGENT_RESULT_VIEW_CHARS,
    agent_result_view_to_wire,
    measure_agent_result_view_chars,
    normalize_agent_result_view_pair,
)
from harness.execution.wire_codec import (
    action_dispatch_result_from_wire,
    action_dispatch_result_to_wire,
)
from harness.execution.contracts import ActionDispatchResult
from domains.mapping.transcript_edit.execution.result_views import (
    SCHEMA_HYDRATE_ARTIFACT_REFS,
    SCHEMA_TRANSFORM_ARTIFACT,
    attach_transcript_edit_result_view,
    build_hydrate_artifact_refs_view,
    build_transform_artifact_view,
)


def _measure_view(view) -> int:
    return measure_agent_result_view_chars(agent_result_view_to_wire(view))


def test_small_t0_text_preserved_exactly() -> None:
    outputs = {
        "hydrated_count": 1,
        "cap_exceeded": False,
        "results": [
            {
                "ref_id": "t0:raw:draft_1",
                "kind": "t0_draft",
                "text": "Exact T0 text",
                "metadata": {"section_count": 2, "path": "C:/host/secret.json"},
                "absolute_path": "C:/host/secret.json",
            }
        ],
        "errors": [],
    }
    view, omitted = build_hydrate_artifact_refs_view(outputs)
    assert omitted is None and view is not None
    assert view.schema_id == SCHEMA_HYDRATE_ARTIFACT_REFS
    assert view.continuity_key is None
    row = view.payload["results"][0]
    assert row["text"] == "Exact T0 text"
    assert "path" not in row.get("metadata", {})
    assert "absolute_path" not in json.dumps(view.payload)
    assert _measure_view(view) <= MAX_AGENT_RESULT_VIEW_CHARS


def test_small_transcript_edit_draft_payload_preserved() -> None:
    payload = {"transcript_text": "hello", "evidence_refs": ["image:assoc:x:original"]}
    outputs = {
        "hydrated_count": 1,
        "cap_exceeded": False,
        "results": [
            {
                "ref_id": "transcript_edit:working:rev:0001",
                "kind": "transcript_edit_draft",
                "payload": payload,
                "path": "C:/host/rev.json",
            }
        ],
        "errors": [],
    }
    view, omitted = build_hydrate_artifact_refs_view(outputs)
    assert omitted is None and view is not None
    assert view.payload["results"][0]["payload"] == payload
    assert "path" not in view.payload["results"][0]
    assert "continuity_key" not in agent_result_view_to_wire(view)


def test_oversized_text_omitted_whole_no_prefix() -> None:
    huge = "H" * 20_000
    prefix = huge[:500]
    outputs = {
        "hydrated_count": 1,
        "cap_exceeded": False,
        "results": [{"ref_id": "t0:raw:draft_1", "kind": "t0_draft", "text": huge}],
        "errors": [],
    }
    view, omitted = build_hydrate_artifact_refs_view(outputs)
    assert omitted is None and view is not None
    blob = json.dumps(view.payload)
    assert huge not in blob
    assert prefix not in blob
    assert view.payload["results"] == []
    assert view.payload["results_omitted"] == [
        {"ref_id": "t0:raw:draft_1", "kind": "t0_draft", "reason": "view_budget"}
    ]
    assert view.payload["results_omitted_count"] == 1


def test_oversized_structured_payload_omitted_whole() -> None:
    huge_payload = {"pad": "P" * 20_000}
    outputs = {
        "hydrated_count": 1,
        "cap_exceeded": False,
        "results": [
            {
                "ref_id": "transcript_edit:working:rev:0002",
                "kind": "transcript_edit_draft",
                "payload": huge_payload,
            }
        ],
        "errors": [],
    }
    view, omitted = build_hydrate_artifact_refs_view(outputs)
    assert omitted is None and view is not None
    assert view.payload["results"] == []
    assert view.payload["results_omitted_count"] == 1
    assert "PPPPP" not in json.dumps(view.payload)


def test_large_first_row_does_not_block_later_small_row() -> None:
    outputs = {
        "hydrated_count": 2,
        "cap_exceeded": False,
        "results": [
            {"ref_id": "t0:raw:draft_1", "kind": "t0_draft", "text": "X" * 20_000},
            {"ref_id": "t0:raw:draft_2", "kind": "t0_draft", "text": "small later"},
        ],
        "errors": [],
    }
    view, omitted = build_hydrate_artifact_refs_view(outputs)
    assert omitted is None and view is not None
    refs = [row["ref_id"] for row in view.payload["results"]]
    assert refs == ["t0:raw:draft_2"]
    assert view.payload["results"][0]["text"] == "small later"
    assert view.payload["results_omitted_count"] >= 1


def test_hydrate_error_rows_bounded_without_substring_truncation() -> None:
    long_msg = "E" * 500
    outputs = {
        "hydrated_count": 0,
        "cap_exceeded": False,
        "results": [],
        "errors": [{"code": "missing", "ref_id": "t0:raw:draft_9", "message": long_msg}],
    }
    view, omitted = build_hydrate_artifact_refs_view(outputs)
    assert omitted is None and view is not None
    err = view.payload["errors"][0]
    assert "message" not in err
    assert err["message_omitted"] is True
    assert err["message_chars"] == 500
    assert long_msg[:40] not in json.dumps(view.payload)


def test_transform_crop_geometry_and_source_window_survive() -> None:
    outputs = {
        "sub_action": "crop",
        "derived_ref_id": "image:derived:1",
        "parent_ref_id": "image:assoc:t:original",
        "basename": "crop.png",
        "width_height": (100, 80),
        "absolute_path": "C:/secret/crop.png",
        "resolved_geometry": {
            "box_norm": (0.1, 0.2, 0.3, 0.4),
            "source_width_height": (1000, 800),
            "absolute_path": "C:/nope",
        },
        "source_window": {
            "local_source_ref": "image:assoc:t:original",
            "local_box_norm": (0.1, 0.2, 0.3, 0.4),
            "can_expand": True,
            "absolute_path": "C:/nope",
        },
    }
    view, omitted = build_transform_artifact_view(outputs)
    assert omitted is None and view is not None
    assert view.schema_id == SCHEMA_TRANSFORM_ARTIFACT
    assert view.continuity_key is None
    assert view.payload["width_height"] == [100, 80]
    assert view.payload["resolved_geometry"]["box_norm"] == [0.1, 0.2, 0.3, 0.4]
    assert view.payload["source_window"]["can_expand"] is True
    assert "absolute_path" not in json.dumps(view.payload)
    assert _measure_view(view) <= MAX_AGENT_RESULT_VIEW_CHARS


def test_transform_point_crop_uses_canonical_projector() -> None:
    outputs = {
        "derived_ref_id": "image:derived:master-1",
        "parent_ref_id": "image:assoc:tx-1:original",
        "sub_action": "point_crops",
        "basename": "master.png",
        "width_height": [400, 300],
        "crop_set": {
            "master_overlay_ref": "image:derived:master-1",
            "source_ref": "image:assoc:tx-1:original",
            "points": [
                {
                    "letter": "A",
                    "alias": "tie",
                    "size": "M",
                    "shape": "circle",
                    "point_norm": [0.2, 0.3],
                    "box_norm": [0.1, 0.2, 0.3, 0.4],
                    "crop_ref": "image:derived:crop-a",
                    "absolute_path": "C:/secret.png",
                    "b64": "aaaa",
                }
            ],
            "review_lines": ["A tie ok"],
            "point_key_lines": ["A -> tie"],
        },
    }
    view, omitted = build_transform_artifact_view(outputs)
    assert omitted is None and view is not None
    crop = view.payload["point_crop_set"]
    assert crop["kind"] == "point_crop_set"
    assert crop["master_overlay_ref"] == "image:derived:master-1"
    assert crop["points"][0]["crop_ref"] == "image:derived:crop-a"
    assert "delegation_lines" in crop
    assert "absolute_path" not in json.dumps(view.payload)
    assert "aaaa" not in json.dumps(view.payload)
    assert "continuity_key" not in agent_result_view_to_wire(view)


def test_evidence_locator_collections_report_omission_counts() -> None:
    # Oversized rows force whole-row omission under the 12k envelope.
    outputs = {
        "sub_action": "render_evidence_locators",
        "derived_ref_id": "image:derived:loc",
        "parent_ref_id": "image:assoc:t:original",
        "basename": "loc.png",
        "width_height": (10, 10),
        "rendered_locators": [
            {
                "locator_index": i,
                "source_ref": "image:assoc:t:original",
                "label": f"L{i}",
                "pad": ("Z" * 800),
            }
            for i in range(40)
        ],
    }
    view, omitted = build_transform_artifact_view(outputs)
    assert omitted is None and view is not None
    kept = view.payload.get("rendered_locators") or []
    assert 0 < len(kept) < 40
    assert view.payload["rendered_locators_omitted_count"] == 40 - len(kept)
    assert _measure_view(view) <= MAX_AGENT_RESULT_VIEW_CHARS


def test_attach_view_on_success_and_skip_on_refusal() -> None:
    success = {
        "executed": True,
        "outputs": {
            "hydrated_count": 1,
            "cap_exceeded": False,
            "results": [{"ref_id": "t0:raw:draft_1", "kind": "t0_draft", "text": "ok"}],
            "errors": [],
        },
        "artifact_refs": [],
        "image_evidence": [{"ref_id": "image:assoc:x:original", "b64": "abc", "media_type": "image/png"}],
    }
    before_evidence = json.dumps(success["image_evidence"])
    attached = attach_transcript_edit_result_view(success, action_id="hydrate_artifact_refs")
    assert "agent_result_view" in attached
    assert "agent_result_view_omitted" not in attached
    assert attached["outputs"] == success["outputs"]
    assert json.dumps(attached["image_evidence"]) == before_evidence
    view, om = normalize_agent_result_view_pair(attached["agent_result_view"], None)
    assert view is not None and om is None

    refused = {
        "executed": False,
        "refusal": {"reason_code": "ref_ids_required", "retryable": False},
        "outputs": {"error": {"code": "ref_ids_required", "message": "needed"}},
    }
    skipped = attach_transcript_edit_result_view(refused, action_id="hydrate_artifact_refs")
    assert "agent_result_view" not in skipped
    assert "agent_result_view_omitted" not in skipped
    assert skipped["refusal"]["reason_code"] == "ref_ids_required"


def test_save_style_results_do_not_gain_views() -> None:
    save_like = {"executed": True, "outputs": {"revision_ref": "transcript_edit:working:rev:0001"}}
    out = attach_transcript_edit_result_view(save_like, action_id="save_workspace_artifact")
    assert out == save_like
    assert "agent_result_view" not in out


def test_wire_codec_accepts_attached_views() -> None:
    result = attach_transcript_edit_result_view(
        {
            "executed": True,
            "outputs": {
                "hydrated_count": 1,
                "cap_exceeded": False,
                "results": [{"ref_id": "t0:raw:draft_1", "kind": "t0_draft", "text": "ok"}],
                "errors": [],
            },
        },
        action_id="hydrate_artifact_refs",
    )
    adr = ActionDispatchResult(
        action_id="hydrate_artifact_refs",
        executed=True,
        outputs=dict(result["outputs"]),
        agent_result_view=normalize_agent_result_view_pair(result["agent_result_view"], None)[0],
    )
    wire = action_dispatch_result_to_wire(adr)
    restored = action_dispatch_result_from_wire(wire)
    assert restored is not None
    assert restored.agent_result_view is not None
    assert restored.agent_result_view.schema_id == SCHEMA_HYDRATE_ARTIFACT_REFS


def test_production_crop_tuple_width_height_yields_valid_list_view() -> None:
    outputs = {
        "sub_action": "crop",
        "derived_ref_id": "image:derived:crop-1",
        "parent_ref_id": "image:assoc:tx:original",
        "basename": "crop.png",
        "width_height": (640, 480),
        "resolved_geometry": {
            "box": (10, 20, 100, 80),
            "box_norm": (0.01, 0.02, 0.2, 0.2),
            "source_width_height": (2000, 1500),
        },
    }
    view, omitted = build_transform_artifact_view(outputs)
    assert omitted is None and view is not None
    assert view.payload["width_height"] == [640, 480]
    assert isinstance(view.payload["width_height"], list)
    assert view.payload["resolved_geometry"]["source_width_height"] == [2000, 1500]


def test_source_image_hydration_tuple_dimensions() -> None:
    outputs = {
        "hydrated_count": 1,
        "cap_exceeded": False,
        "results": [
            {
                "ref_id": "image:assoc:tx:original",
                "kind": "source_image",
                "basename": "page.png",
                "exists": True,
                "width_height": (1200, 900),
                "absolute_path": "C:/host/page.png",
            }
        ],
        "errors": [],
    }
    view, omitted = build_hydrate_artifact_refs_view(outputs)
    assert omitted is None and view is not None
    row = view.payload["results"][0]
    assert row["width_height"] == [1200, 900]
    assert "absolute_path" not in row


def test_resolved_annotations_survive_with_geometry() -> None:
    outputs = {
        "sub_action": "annotate",
        "derived_ref_id": "image:derived:ann-1",
        "parent_ref_id": "image:assoc:tx:original",
        "basename": "ann.png",
        "width_height": (100, 80),
        "resolved_annotations": [
            {
                "label": "A",
                "resolved_geometry": {
                    "box_norm": (0.1, 0.2, 0.3, 0.4),
                    "source_width_height": (100, 80),
                },
                "absolute_path": "C:/nope",
            },
            {
                "label": "B",
                "resolved_geometry": {
                    "box_norm": (0.5, 0.5, 0.6, 0.6),
                    "source_width_height": (100, 80),
                },
            },
        ],
    }
    view, omitted = build_transform_artifact_view(outputs)
    assert omitted is None and view is not None
    anns = view.payload["resolved_annotations"]
    assert len(anns) == 2
    assert anns[0]["resolved_geometry"]["box_norm"] == [0.1, 0.2, 0.3, 0.4]
    assert "absolute_path" not in json.dumps(view.payload)
    assert "annotations" not in view.payload


def test_large_errors_do_not_evict_small_hydration_result() -> None:
    outputs = {
        "hydrated_count": 1,
        "cap_exceeded": False,
        "results": [{"ref_id": "t0:raw:draft_1", "kind": "t0_draft", "text": "keep-me"}],
        "errors": [
            {"code": f"err_{i}", "ref_id": f"t0:raw:draft_{i}", "message": "M" * 200}
            for i in range(40)
        ],
    }
    view, omitted = build_hydrate_artifact_refs_view(outputs)
    assert omitted is None and view is not None
    assert view.payload["results"] == [
        {"ref_id": "t0:raw:draft_1", "kind": "t0_draft", "text": "keep-me"}
    ]
    assert view.payload.get("errors_omitted_count", 0) >= 1
    assert _measure_view(view) <= MAX_AGENT_RESULT_VIEW_CHARS


def test_oversized_error_code_omits_field_not_result() -> None:
    outputs = {
        "hydrated_count": 1,
        "cap_exceeded": False,
        "results": [{"ref_id": "t0:raw:draft_1", "kind": "t0_draft", "text": "ok"}],
        "errors": [{"code": "C" * 500, "ref_id": "t0:raw:draft_9", "message": "short"}],
    }
    view, omitted = build_hydrate_artifact_refs_view(outputs)
    assert omitted is None and view is not None
    assert view.payload["results"][0]["text"] == "ok"
    err = view.payload["errors"][0]
    assert "code" not in err
    assert err["code_omitted"] is True
    assert ("C" * 40) not in json.dumps(view.payload)


def test_composed_bindings_pass_views_through_executor() -> None:
    from domains.mapping.transcript_edit.execution.result_views import wrap_handler_with_result_view
    from harness.execution.contracts import ExecutionStepRequest
    from harness.execution.executor import ExecutionExecutor

    def hydrate_handler(_request):
        return {
            "executed": True,
            "outputs": {
                "hydrated_count": 1,
                "cap_exceeded": False,
                "results": [
                    {
                        "ref_id": "image:assoc:tx:original",
                        "kind": "source_image",
                        "width_height": (64, 32),
                        "basename": "x.png",
                    }
                ],
                "errors": [],
            },
        }

    def transform_handler(_request):
        return {
            "executed": True,
            "artifact_refs": ["image:derived:1"],
            "outputs": {
                "sub_action": "crop",
                "derived_ref_id": "image:derived:1",
                "parent_ref_id": "image:assoc:tx:original",
                "basename": "crop.png",
                "width_height": (50, 40),
            },
        }

    def save_handler(_request):
        return {"executed": True, "outputs": {"revision_ref": "transcript_edit:working:rev:0001"}}

    executor = ExecutionExecutor()
    executor.register(
        "hydrate_artifact_refs",
        wrap_handler_with_result_view(hydrate_handler, action_id="hydrate_artifact_refs"),
    )
    executor.register(
        "transform_artifact",
        wrap_handler_with_result_view(transform_handler, action_id="transform_artifact"),
    )
    executor.register("save_workspace_artifact", save_handler)
    executor.register("copy_forward_save_workspace_artifact", save_handler)
    executor.register("publish_workspace_artifact", save_handler)

    hydrated = executor.execute(
        ExecutionStepRequest(session_id="s1", action_id="hydrate_artifact_refs", idempotency_key="h1")
    )
    assert hydrated.agent_result_view is not None
    assert hydrated.agent_result_view_omitted is None
    assert hydrated.agent_result_view.payload["results"][0]["width_height"] == [64, 32]
    assert hydrated.outputs["results"][0]["width_height"] == (64, 32)

    transformed = executor.execute(
        ExecutionStepRequest(session_id="s1", action_id="transform_artifact", idempotency_key="t1")
    )
    assert transformed.agent_result_view is not None
    assert transformed.agent_result_view.payload["width_height"] == [50, 40]
    assert transformed.outputs["width_height"] == (50, 40)

    for action_id in (
        "save_workspace_artifact",
        "copy_forward_save_workspace_artifact",
        "publish_workspace_artifact",
    ):
        saved = executor.execute(
            ExecutionStepRequest(session_id="s1", action_id=action_id, idempotency_key=action_id)
        )
        assert saved.agent_result_view is None
        assert saved.agent_result_view_omitted is None


def test_nested_host_binary_fields_stripped_from_hydrate_views() -> None:
    outputs = {
        "hydrated_count": 2,
        "cap_exceeded": False,
        "results": [
            {
                "ref_id": "t0:raw:draft_1",
                "kind": "t0_draft",
                "text": "safe",
                "metadata": {
                    "section_count": 1,
                    "source": {
                        "absolute_path": "C:/host/secret.json",
                        "b64": "QUJD",
                        "stem": "draft_1",
                    },
                },
            },
            {
                "ref_id": "custom:blob:1",
                "kind": "unknown_bundle",
                "parts": (
                    {"label": "a", "absolute_path": "C:/host/a.bin", "ok": True},
                    {"label": "b", "b64": "aaaa", "note": "keep"},
                ),
            },
        ],
        "errors": [],
    }
    view, omitted = build_hydrate_artifact_refs_view(outputs)
    assert omitted is None and view is not None
    blob = json.dumps(view.payload)
    assert "absolute_path" not in blob
    assert "b64" not in blob
    assert "QUJD" not in blob
    assert "aaaa" not in blob
    assert "C:/host" not in blob
    meta = view.payload["results"][0]["metadata"]
    assert meta["section_count"] == 1
    assert meta["source"] == {"stem": "draft_1"}
    parts = view.payload["results"][1]["parts"]
    assert parts == [{"label": "a", "ok": True}, {"label": "b", "note": "keep"}]
