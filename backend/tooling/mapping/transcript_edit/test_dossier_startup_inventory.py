"""Tests for dossier-scoped startup inventory and qualified refs."""

from __future__ import annotations

from dataclasses import asdict

import pytest

from domains.mapping.transcript_edit.payloads.startup_inventory import (
    MissingResource,
    SourceImageRefDescriptor,
    T0DraftDescriptor,
    TranscriptEditDraftInventory,
    TranscriptEditScope,
    TranscriptEditStartupInventory,
)
from services.dossier.segment_topology import (
    TopologyRunInput,
    TopologySegmentInput,
    build_dossier_segment_topology,
)
from tooling.mapping.transcript_edit.dossier_artifact_refs import qualify_leaf_ref
from tooling.mapping.transcript_edit.dossier_startup_inventory import (
    DossierStartupInventoryError,
    build_dossier_transcript_edit_startup_inventory,
    build_dossier_transcript_edit_startup_inventory_from_segments,
)


def _leaf(
    *,
    dossier_id: str,
    transcription_id: str,
    segment_id: str | None = None,
    run_id: str | None = None,
    workspace_id: str | None = None,
    fail: bool = False,
    missing: tuple[MissingResource, ...] = (),
    working_draft_exists: bool = True,
    working_draft_ref: str | None = "transcript_edit:working",
    working_latest_revision: int | None = 1,
) -> TranscriptEditStartupInventory:
    if fail:
        raise RuntimeError(f"leaf boom for {transcription_id}")
    return TranscriptEditStartupInventory(
        scope=TranscriptEditScope(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            segment_id=segment_id,
            run_id=run_id,
            workspace_id=workspace_id,
        ),
        source_images=(
            SourceImageRefDescriptor(
                ref_id=f"image:assoc:{transcription_id}:original",
                role="source_original",
                basename=f"{transcription_id}.jpg",
            ),
        ),
        t0_drafts=(
            T0DraftDescriptor(
                ref_id="t0:raw:draft_1",
                variant_label="draft 1",
                source_file_stem=f"{transcription_id}_draft_1",
                snippet_preview="should-not-appear-in-aggregate",
            ),
            T0DraftDescriptor(
                ref_id="t0:raw:draft_2",
                variant_label="draft 2",
                source_file_stem=f"{transcription_id}_draft_2",
            ),
        ),
        transcript_edit_drafts=TranscriptEditDraftInventory(
            working_draft_exists=working_draft_exists,
            working_draft_ref=working_draft_ref if working_draft_exists else None,
            working_latest_revision=working_latest_revision if working_draft_exists else None,
            output_draft_exists=False,
        ),
        artifact_fingerprint=f"fp-{transcription_id}",
        missing_resources=missing,
    )


def test_leaf_builder_reused_and_order_preserved() -> None:
    calls: list[str] = []

    def builder(**kwargs):
        calls.append(kwargs["transcription_id"])
        return _leaf(**kwargs)

    bundle = build_dossier_transcript_edit_startup_inventory_from_segments(
        dossier_id="d1",
        segments=(
            TopologySegmentInput(
                segment_id="seg_a",
                position=0,
                runs=(TopologyRunInput("tx_a", 0),),
            ),
            TopologySegmentInput(
                segment_id="seg_b",
                position=1,
                runs=(TopologyRunInput("tx_b", 0), TopologyRunInput("tx_c", 1)),
            ),
        ),
        association_positions={"tx_a": 1, "tx_b": 2, "tx_c": 3},
        leaf_inventory_builder=builder,
    )
    inv = bundle.inventory
    assert calls == ["tx_a", "tx_b", "tx_c"]
    assert [s.segment_id for s in inv.segments] == ["seg_a", "seg_b"]
    assert [r.transcription_id for r in inv.segments[1].runs] == ["tx_b", "tx_c"]
    assert inv.segments[0].previous_segment_id is None
    assert inv.segments[0].next_segment_id == "seg_b"
    assert inv.segments[1].previous_segment_id == "seg_a"
    assert inv.segments[1].next_segment_id is None
    assert bundle.ref_index.dossier_id == "d1"
    assert bundle.ref_index.topology_fingerprint == inv.topology_fingerprint


def test_qualified_refs_unique_across_same_local_leaf() -> None:
    bundle = build_dossier_transcript_edit_startup_inventory_from_segments(
        dossier_id="d1",
        segments=(
            TopologySegmentInput("seg_a", 0, (TopologyRunInput("tx_a", 0),)),
            TopologySegmentInput("seg_b", 1, (TopologyRunInput("tx_b", 0),)),
        ),
        association_positions={"tx_a": 1, "tx_b": 2},
        leaf_inventory_builder=_leaf,
    )
    refs = list(bundle.ref_index.by_ref)
    assert len(refs) == len(set(refs))
    a = qualify_leaf_ref(segment_id="seg_a", transcription_id="tx_a", leaf_ref="t0:raw:draft_1")
    b = qualify_leaf_ref(segment_id="seg_b", transcription_id="tx_b", leaf_ref="t0:raw:draft_1")
    assert a != b
    assert a in bundle.ref_index.by_ref
    assert b in bundle.ref_index.by_ref


def test_agent_facing_refs_all_resolve_through_index() -> None:
    bundle = build_dossier_transcript_edit_startup_inventory_from_segments(
        dossier_id="d1",
        segments=(
            TopologySegmentInput("seg_a", 0, (TopologyRunInput("tx_a", 0),)),
            TopologySegmentInput("seg_b", 1, (TopologyRunInput("tx_b", 0),)),
        ),
        association_positions={"tx_a": 1, "tx_b": 2},
        leaf_inventory_builder=_leaf,
    )
    for segment in bundle.inventory.segments:
        for run in segment.runs:
            for ref in run.source_image_refs + run.t0_draft_refs:
                assert ref in bundle.ref_index.by_ref
            if run.working_draft_ref:
                assert run.working_draft_ref in bundle.ref_index.by_ref
            if run.output_draft_ref:
                assert run.output_draft_ref in bundle.ref_index.by_ref


def test_ref_index_rejects_post_construction_mutation() -> None:
    bundle = build_dossier_transcript_edit_startup_inventory_from_segments(
        dossier_id="d1",
        segments=(TopologySegmentInput("seg_a", 0, (TopologyRunInput("tx_a", 0),)),),
        association_positions={"tx_a": 1},
        leaf_inventory_builder=_leaf,
    )
    with pytest.raises(TypeError):
        bundle.ref_index.by_ref["injected"] = bundle.ref_index.resolve(  # type: ignore[index]
            next(iter(bundle.ref_index.by_ref))
        )


def test_topology_dossier_mismatch_refused() -> None:
    topo = build_dossier_segment_topology(
        dossier_id="dossier-a",
        segments=(TopologySegmentInput("seg_a", 0, (TopologyRunInput("tx_a", 0),)),),
        association_positions={"tx_a": 1},
    )
    with pytest.raises(DossierStartupInventoryError) as exc:
        build_dossier_transcript_edit_startup_inventory(
            dossier_id="dossier-b",
            topology=topo,
            leaf_inventory_builder=_leaf,
        )
    assert exc.value.code == "topology_dossier_mismatch"


def test_missing_resources_localized_and_neighbor_survives() -> None:
    def builder(**kwargs):
        if kwargs["transcription_id"] == "tx_bad":
            return _leaf(
                **kwargs,
                missing=(
                    MissingResource(
                        code="run_json_missing_or_unreadable",
                        message="broken",
                        detail="tx_bad",
                    ),
                ),
            )
        if kwargs["transcription_id"] == "tx_boom":
            return _leaf(**kwargs, fail=True)
        return _leaf(**kwargs)

    bundle = build_dossier_transcript_edit_startup_inventory_from_segments(
        dossier_id="d1",
        segments=(
            TopologySegmentInput("seg_a", 0, (TopologyRunInput("tx_ok", 0),)),
            TopologySegmentInput("seg_b", 1, (TopologyRunInput("tx_bad", 0),)),
            TopologySegmentInput("seg_c", 2, (TopologyRunInput("tx_boom", 0),)),
        ),
        association_positions={"tx_ok": 1, "tx_bad": 2, "tx_boom": 3},
        leaf_inventory_builder=builder,
    )
    inv = bundle.inventory
    assert inv.segment_count == 3
    assert inv.segments[0].runs[0].missing_resources == ()
    assert any(
        m.code == "run_json_missing_or_unreadable"
        for m in inv.segments[1].runs[0].missing_resources
    )
    assert any(
        m.code == "leaf_inventory_build_failed"
        for m in inv.segments[2].runs[0].missing_resources
    )
    boom = inv.segments[2].runs[0].missing_resources[0]
    assert boom.detail is None or boom.detail == ""
    assert "leaf boom" not in (boom.message or "")


def test_windows_absolute_path_in_leaf_detail_is_omitted() -> None:
    win_path = r"C:\Users\example\AppData\Local\Plattera\Data\dossiers_data\views\tx_a\run.json"

    def builder(**kwargs):
        return _leaf(
            **kwargs,
            missing=(
                MissingResource(
                    code="run_json_missing_or_unreadable",
                    message="Run JSON missing or unreadable.",
                    detail=win_path,
                ),
            ),
        )

    bundle = build_dossier_transcript_edit_startup_inventory_from_segments(
        dossier_id="d1",
        segments=(TopologySegmentInput("seg_a", 0, (TopologyRunInput("tx_a", 0),)),),
        association_positions={"tx_a": 1},
        leaf_inventory_builder=builder,
    )
    blob = json_dumps_safe(asdict(bundle.inventory))
    assert win_path not in blob
    assert r"C:\Users" not in blob
    assert "AppData" not in blob
    projected = bundle.inventory.segments[0].runs[0].missing_resources[0]
    assert projected.code == "run_json_missing_or_unreadable"
    assert projected.message == "Run JSON missing or unreadable."
    assert projected.detail is None or projected.detail == ""


def test_aggregate_excludes_snippets_paths_and_blobs() -> None:
    bundle = build_dossier_transcript_edit_startup_inventory_from_segments(
        dossier_id="d1",
        segments=(TopologySegmentInput("seg_a", 0, (TopologyRunInput("tx_a", 0),)),),
        association_positions={"tx_a": 1},
        leaf_inventory_builder=_leaf,
    )
    blob = json_dumps_safe(asdict(bundle.inventory))
    assert "should-not-appear-in-aggregate" not in blob
    assert "base64" not in blob.lower()
    assert ":\\" not in blob
    assert "C:/" not in blob


def test_seventy_segments_no_truncation() -> None:
    segments = tuple(
        TopologySegmentInput(f"seg_{i}", i, (TopologyRunInput(f"tx_{i}", 0),))
        for i in range(70)
    )
    assoc = {f"tx_{i}": i + 1 for i in range(70)}
    bundle = build_dossier_transcript_edit_startup_inventory_from_segments(
        dossier_id="d1",
        segments=segments,
        association_positions=assoc,
        leaf_inventory_builder=_leaf,
    )
    assert bundle.inventory.segment_count == 70
    assert len(bundle.inventory.segments) == 70
    assert [s.segment_id for s in bundle.inventory.segments] == [f"seg_{i}" for i in range(70)]


def test_single_segment_exposes_same_leaf_capabilities() -> None:
    leaf = _leaf(dossier_id="d1", transcription_id="tx_a", segment_id="seg_a")
    bundle = build_dossier_transcript_edit_startup_inventory_from_segments(
        dossier_id="d1",
        segments=(TopologySegmentInput("seg_a", 0, (TopologyRunInput("tx_a", 0),)),),
        association_positions={"tx_a": 1},
        leaf_inventory_builder=lambda **kwargs: leaf,
    )
    run = bundle.inventory.segments[0].runs[0]
    assert len(run.source_image_refs) == len(leaf.source_images)
    assert len(run.t0_draft_refs) == len(leaf.t0_drafts)
    assert run.working_draft_ref is not None
    assert run.output_draft_ref is None
    assert run.artifact_fingerprint == leaf.artifact_fingerprint
    assert not hasattr(run, "run_ref")


def test_working_latest_revision_ref_projected_and_indexed() -> None:
    bundle = build_dossier_transcript_edit_startup_inventory_from_segments(
        dossier_id="d1",
        segments=(TopologySegmentInput("seg_a", 0, (TopologyRunInput("tx_a", 0),)),),
        association_positions={"tx_a": 1},
        leaf_inventory_builder=lambda **kwargs: _leaf(**kwargs, working_latest_revision=3),
    )
    run = bundle.inventory.segments[0].runs[0]
    expected = qualify_leaf_ref(
        segment_id="seg_a",
        transcription_id="tx_a",
        leaf_ref="transcript_edit:working:rev:0003",
    )
    assert run.working_latest_revision_ref == expected
    assert expected in bundle.ref_index.by_ref
    assert bundle.ref_index.resolve(expected).leaf_ref == "transcript_edit:working:rev:0003"


def test_incoherent_working_latest_revision_does_not_invent_ref() -> None:
    bundle = build_dossier_transcript_edit_startup_inventory_from_segments(
        dossier_id="d1",
        segments=(TopologySegmentInput("seg_a", 0, (TopologyRunInput("tx_a", 0),)),),
        association_positions={"tx_a": 1},
        leaf_inventory_builder=lambda **kwargs: _leaf(
            **kwargs,
            working_draft_exists=True,
            working_draft_ref="transcript_edit:working",
            working_latest_revision=None,
        ),
    )
    run = bundle.inventory.segments[0].runs[0]
    assert run.working_latest_revision_ref is None
    assert any(
        m.code == "working_latest_revision_unavailable" for m in run.missing_resources
    )


def json_dumps_safe(obj: object) -> str:
    import json

    return json.dumps(obj, default=str)
