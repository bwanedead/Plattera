"""Production-shaped coverage for dossier-qualified delegate context refs."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import config.paths as paths_mod
import pytest
import tooling.mapping.transcript_edit.paths as te_paths
from PIL import Image

from domains.mapping.transcript_edit import build_transcript_edit_domain_pack
from domains.mapping.transcript_edit.execution.subtask_profiles import (
    TRANSCRIPT_EDIT_VISUAL_SOURCE_OBSERVATION_PROFILE_ID,
)
from domains.mapping.transcript_edit.payloads.startup_inventory import (
    SourceImageRefDescriptor,
    TranscriptEditDraftInventory,
    TranscriptEditScope,
    TranscriptEditStartupInventory,
)
from domains.mapping.transcript_edit.runtime_adapter.dossier_tool_bindings import (
    build_dossier_transcript_edit_tool_bindings,
)
from harness.execution.contracts import ExecutionStepRequest
from harness.runtime.orchestration.action_plan_parser import (
    parse_action_plan_response,
)
from harness.runtime.orchestration.subtasks.batch_policy import (
    delegate_subtask_tool_batch_policy,
)
from harness.runtime.orchestration.subtasks.contracts import DELEGATE_SUBTASK_ACTION_TYPE
from harness.runtime.orchestration.subtasks.registry import build_composed_subtask_registry
from harness.runtime.orchestration.subtasks.runner import run_delegate_subtask
from harness.runtime.orchestration.subtasks.validation import (
    ref_kind,
    validate_delegate_subtask_inputs,
)
from services.dossier.segment_topology import TopologyRunInput, TopologySegmentInput
from tooling.mapping.transcript_edit.dossier_artifact_refs import qualify_leaf_ref
from tooling.mapping.transcript_edit.dossier_startup_inventory import (
    build_dossier_transcript_edit_startup_inventory_from_segments,
)


def _dossiers_root(tmp_path: Path) -> Path:
    root = tmp_path / "dossiers_data"
    root.mkdir(parents=True)
    return root


def _patch_roots(monkeypatch, root: Path) -> None:
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(te_paths, "dossiers_root", lambda: root)


def _tiny_png_bytes() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (8, 8), (200, 180, 160)).save(buf, format="PNG")
    return buf.getvalue()


def _write_association(root: Path, dossier_id: str, transcription_id: str, image_path: Path) -> None:
    assoc_dir = root / "associations"
    assoc_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "dossier_id": dossier_id,
        "associations": [
            {
                "transcription_id": transcription_id,
                "position": 1,
                "metadata": {
                    "images": {
                        "original_path": str(image_path),
                        "processed_path": str(image_path),
                    }
                },
            }
        ],
    }
    (assoc_dir / f"assoc_{dossier_id}.json").write_text(json.dumps(payload), encoding="utf-8")


def _minimal_run_layout(root: Path, dossier_id: str, transcription_id: str) -> None:
    run = root / "views" / "transcriptions" / dossier_id / transcription_id
    raw = run / "raw"
    raw.mkdir(parents=True)
    (raw / f"{transcription_id}_draft_1.json").write_text(
        json.dumps({"sections": [{"body": f"t0 {transcription_id}"}]}),
        encoding="utf-8",
    )
    (run / "run.json").write_text(
        json.dumps({"completed_drafts": [f"{transcription_id}_draft_1"]}),
        encoding="utf-8",
    )


def _image_bundle(tmp_path, monkeypatch, *, workspace_id: str = "ws-delegate"):
    root = _dossiers_root(tmp_path)
    _patch_roots(monkeypatch, root)
    dossier_id = "d1"
    _minimal_run_layout(root, dossier_id, "tx_a")
    img = tmp_path / "images" / "scan.png"
    img.parent.mkdir(parents=True)
    img.write_bytes(_tiny_png_bytes())
    _write_association(root, dossier_id, "tx_a", img)

    def leaf_builder(**kwargs):
        tid = kwargs["transcription_id"]
        return TranscriptEditStartupInventory(
            scope=TranscriptEditScope(
                dossier_id=dossier_id,
                transcription_id=tid,
                segment_id=kwargs.get("segment_id"),
                workspace_id=workspace_id,
            ),
            source_images=(
                SourceImageRefDescriptor(
                    ref_id=f"image:assoc:{tid}:original",
                    role="source_original",
                    basename="scan.png",
                ),
            ),
            transcript_edit_drafts=TranscriptEditDraftInventory(working_draft_exists=False),
        )

    bundle = build_dossier_transcript_edit_startup_inventory_from_segments(
        dossier_id=dossier_id,
        workspace_id=workspace_id,
        segments=(TopologySegmentInput("seg_a", 0, (TopologyRunInput("tx_a", 0),)),),
        association_positions={"tx_a": 1},
        leaf_inventory_builder=leaf_builder,
    )
    return bundle


def _te_registry():
    payload = build_transcript_edit_domain_pack().build_surface_payload()
    return build_composed_subtask_registry(surface_payloads={"transcript_edit": payload})


def _q_derived(*, segment: str = "seg_a", transcription: str = "tx_a", leaf_id: str = "abc123") -> str:
    return qualify_leaf_ref(
        segment_id=segment,
        transcription_id=transcription,
        leaf_ref=f"image:derived:{leaf_id}",
    )


def test_leaf_and_qualified_refs_validate_unchanged() -> None:
    registry = _te_registry()
    leaf_image = validate_delegate_subtask_inputs(
        {
            "profile": TRANSCRIPT_EDIT_VISUAL_SOURCE_OBSERVATION_PROFILE_ID,
            "task": "Read the visible mark.",
            "context_refs": ["image:derived:crop_001"],
        },
        registry=registry,
    )
    assert leaf_image.context_refs == ("image:derived:crop_001",)

    leaf_artifact = validate_delegate_subtask_inputs(
        {
            "profile": TRANSCRIPT_EDIT_VISUAL_SOURCE_OBSERVATION_PROFILE_ID,
            "task": "Read the supplied artifact.",
            "context_refs": ["artifact:sample"],
        },
        registry=registry,
    )
    assert leaf_artifact.context_refs == ("artifact:sample",)

    qualified = _q_derived()
    assert ref_kind(qualified) == "dossier_segment"
    request = validate_delegate_subtask_inputs(
        {
            "profile": TRANSCRIPT_EDIT_VISUAL_SOURCE_OBSERVATION_PROFILE_ID,
            "task": "Read the visible mark in the qualified crop.",
            "context_refs": [qualified],
        },
        registry=registry,
    )
    assert request.context_refs == (qualified,)


def test_qualified_derived_hydrates_and_delegate_preserves_ref(tmp_path, monkeypatch) -> None:
    bundle = _image_bundle(tmp_path, monkeypatch)
    bindings = build_dossier_transcript_edit_tool_bindings(bundle=bundle)
    hydrate = next(b for b in bindings if b.tool_id == "hydrate_artifact_refs").handler
    transform = next(b for b in bindings if b.tool_id == "transform_artifact").handler

    source = qualify_leaf_ref(
        segment_id="seg_a",
        transcription_id="tx_a",
        leaf_ref="image:assoc:tx_a:original",
    )
    cropped = transform(
        ExecutionStepRequest(
            session_id="s1",
            action_id="transform_artifact",
            inputs={
                "ref_id": source,
                "sub_action": "crop",
                "params": {"box_norm": [0.0, 0.0, 1.0, 1.0]},
            },
        )
    )
    assert cropped["executed"] is True
    qualified = cropped["outputs"]["derived_ref_id"]
    assert qualified.startswith("dossier_segment:seg_a:run:tx_a:image:derived:")

    hydrated = hydrate(
        ExecutionStepRequest(
            session_id="s1",
            action_id="hydrate_artifact_refs",
            inputs={"ref_ids": [qualified], "max_refs": 4},
        )
    )
    assert hydrated["executed"] is True
    assert hydrated["outputs"]["hydrated_count"] == 1
    assert hydrated["outputs"]["results"][0]["ref_id"] == qualified
    assert isinstance(hydrated.get("image_evidence"), list) and hydrated["image_evidence"]
    assert hydrated["image_evidence"][0]["ref_id"] == qualified

    registry = _te_registry()
    profile = registry.require(TRANSCRIPT_EDIT_VISUAL_SOURCE_OBSERVATION_PROFILE_ID)
    request = validate_delegate_subtask_inputs(
        {
            "profile": profile.profile_id,
            "task": "Read the visible mark in the supplied crop.",
            "context_refs": [qualified],
        },
        registry=registry,
    )
    assert request.context_refs == (qualified,)

    seen_refs: list[str] = []
    image_counts: list[int] = []

    def model_caller(prompt: str, model_name: str, *, call_options):
        del prompt, model_name
        image_counts.append(len(call_options.image_attachments))
        for attachment in call_options.image_attachments:
            if isinstance(attachment, dict):
                seen_refs.append(str(attachment.get("ref_id") or ""))
            else:
                seen_refs.append(str(getattr(attachment, "ref_id", "") or ""))
        return json.dumps(
            {
                "status": "completed",
                "result": {
                    "task_response": "mark reads A",
                    "source_visible_text": "A",
                    "visual_basis": ["center stroke"],
                    "ambiguity": "",
                    "limits": [],
                },
            }
        )

    output = run_delegate_subtask(
        subtask_id="visual_read_qualified",
        request=request,
        profile=profile,
        model_caller=model_caller,
        default_model_name="model-a",
        hydration_handler=hydrate,
        parent_request=ExecutionStepRequest(
            session_id="s1",
            action_id="delegate_subtask",
            inputs={},
            idempotency_key="req:iter:1:dispatch:delegate_subtask",
            run_id="r1",
        ),
    )
    assert output["status"] == "completed"
    assert output["input_refs"] == [qualified]
    assert image_counts == [1]
    assert seen_refs == [qualified]
    trace = output.get("subtask_trace") or {}
    assert trace.get("image_refs")
    assert trace["image_refs"][0]["ref_id"] == qualified


def test_fabricated_or_unsupported_qualified_ref_refuses_without_image(
    tmp_path, monkeypatch
) -> None:
    bundle = _image_bundle(tmp_path, monkeypatch)
    bindings = build_dossier_transcript_edit_tool_bindings(bundle=bundle)
    hydrate = next(b for b in bindings if b.tool_id == "hydrate_artifact_refs").handler

    fabricated = qualify_leaf_ref(
        segment_id="seg_missing",
        transcription_id="tx_a",
        leaf_ref="image:derived:abc123",
    )
    unsupported_inner = qualify_leaf_ref(
        segment_id="seg_a",
        transcription_id="tx_a",
        leaf_ref="text:not_an_image_leaf",
    )
    bad_binding = hydrate(
        ExecutionStepRequest(
            session_id="s1",
            action_id="hydrate_artifact_refs",
            inputs={"ref_ids": [fabricated], "max_refs": 4},
        )
    )
    assert bad_binding["executed"] is True
    assert bad_binding["outputs"]["hydrated_count"] == 0
    assert bad_binding["outputs"]["errors"]
    assert not bad_binding.get("image_evidence")

    unsupported = hydrate(
        ExecutionStepRequest(
            session_id="s1",
            action_id="hydrate_artifact_refs",
            inputs={"ref_ids": [unsupported_inner], "max_refs": 4},
        )
    )
    assert unsupported["executed"] is True
    assert unsupported["outputs"]["hydrated_count"] == 0
    assert unsupported["outputs"]["errors"]
    assert not unsupported.get("image_evidence")


def test_six_delegate_batch_with_qualified_refs_validates_without_repair() -> None:
    from domains.mapping.transcript_edit.execution.action_batch_policy import (
        build_transcript_edit_action_batch_policy,
    )
    from harness.runtime.orchestration.tool_batch_policy import DomainActionBatchPolicy

    registry = _te_registry()
    domain_policy = DomainActionBatchPolicy.from_mapping(
        build_transcript_edit_action_batch_policy()
    )
    actions = []
    for i in range(6):
        qualified = _q_derived(leaf_id=f"crop_{i:02d}")
        actions.append(
            {
                "alias": f"read_crop_{i:02d}",
                "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
                "action_inputs": {
                    "profile": TRANSCRIPT_EDIT_VISUAL_SOURCE_OBSERVATION_PROFILE_ID,
                    "task": f"Read the visible mark in crop {i:02d}.",
                    "context_refs": [qualified],
                },
            }
        )

    plan = parse_action_plan_response(
        json.dumps({"actions": actions, "rationale": "Parallel localized crop reads."}),
        available_tool_ids=(DELEGATE_SUBTASK_ACTION_TYPE,),
        tool_batch_policies={DELEGATE_SUBTASK_ACTION_TYPE: delegate_subtask_tool_batch_policy()},
        domain_batch_policy=domain_policy,
        subtask_profile_registry=registry,
    )
    assert len(plan.actions) == 6
    for action, expected in zip(plan.actions, actions, strict=True):
        assert action.action_inputs["context_refs"] == expected["action_inputs"]["context_refs"]

    # The original first action validates alone — no repair path that would strip context_refs.
    first = validate_delegate_subtask_inputs(
        actions[0]["action_inputs"],
        registry=registry,
    )
    assert first.context_refs == tuple(actions[0]["action_inputs"]["context_refs"])
    assert first.context_refs[0].startswith("dossier_segment:")


def test_disallowed_outer_kind_still_refuses_when_not_on_profile() -> None:
    """Guard: only the TE profile's allowlist change admits dossier_segment."""
    from harness.runtime.orchestration.subtasks.contracts import SubtaskProfile
    from harness.runtime.orchestration.subtasks.errors import SubtaskValidationError
    from harness.runtime.orchestration.subtasks.registry import SubtaskProfileRegistry

    registry = SubtaskProfileRegistry()
    registry.register(
        SubtaskProfile(
            profile_id="test.image_only",
            owner="test",
            description="image only",
            allowed_ref_kinds=("image", "artifact"),
            prompt_preamble="observe",
        )
    )
    with pytest.raises(SubtaskValidationError) as exc:
        validate_delegate_subtask_inputs(
            {
                "profile": "test.image_only",
                "task": "Read crop.",
                "context_refs": [_q_derived()],
            },
            registry=registry,
        )
    assert exc.value.reason_code == "context_ref_kind_disallowed"
