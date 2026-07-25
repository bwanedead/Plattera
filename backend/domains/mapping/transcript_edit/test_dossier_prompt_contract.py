"""Dossier-mode prompt and tool-contract checks."""

from __future__ import annotations

from domains.mapping.transcript_edit.domain_pack import build_transcript_edit_domain_pack
from domains.mapping.transcript_edit.execution.dossier_tool_specs import (
    build_dossier_transcript_edit_tool_specs,
)
from domains.mapping.transcript_edit.execution.tool_specs import (
    build_transcript_edit_tool_specs,
)
from domains.mapping.transcript_edit.payloads import (
    DossierTopologyDiagnostic,
    DossierTranscriptEditScope,
    DossierTranscriptEditStartupInventory,
    DossierTranscriptRunInventory,
    DossierTranscriptSegmentInventory,
    MissingResource,
)
from domains.mapping.transcript_edit.prompting.surfaces.startup_context import (
    build_startup_context_block,
)


def _q(segment: str, transcription: str, leaf: str) -> str:
    return f"dossier_segment:{segment}:run:{transcription}:{leaf}"


def _inventory() -> DossierTranscriptEditStartupInventory:
    return DossierTranscriptEditStartupInventory(
        scope=DossierTranscriptEditScope(
            dossier_id="dossier-1",
            run_id="run-1",
            workspace_id="workspace-1",
        ),
        topology_fingerprint="a" * 64,
        segment_count=2,
        segments=(
            DossierTranscriptSegmentInventory(
                segment_id="segment-01",
                position=0,
                previous_segment_id=None,
                next_segment_id="segment-02",
                runs=(
                    DossierTranscriptRunInventory(
                        transcription_id="tx-01a",
                        position=0,
                        source_image_refs=(
                            _q(
                                "segment-01",
                                "tx-01a",
                                "image:assoc:tx-01a:original",
                            ),
                        ),
                        t0_draft_refs=(
                            _q("segment-01", "tx-01a", "t0:raw:pass_1"),
                            _q("segment-01", "tx-01a", "t0:raw:pass_2"),
                        ),
                        working_draft_ref=None,
                        working_latest_revision_ref=None,
                        output_draft_ref=None,
                        artifact_fingerprint="b" * 64,
                        missing_resources=(),
                    ),
                    DossierTranscriptRunInventory(
                        transcription_id="tx-01b",
                        position=1,
                        source_image_refs=(),
                        t0_draft_refs=(
                            _q("segment-01", "tx-01b", "t0:raw:pass_1"),
                        ),
                        working_draft_ref=None,
                        working_latest_revision_ref=None,
                        output_draft_ref=None,
                        artifact_fingerprint="c" * 64,
                        missing_resources=(
                            MissingResource(
                                code="source_image_missing",
                                message="Original source image is unavailable.",
                                detail=r"C:\private\source.png",
                            ),
                        ),
                    ),
                ),
            ),
            DossierTranscriptSegmentInventory(
                segment_id="segment-02",
                position=1,
                previous_segment_id="segment-01",
                next_segment_id=None,
                runs=(
                    DossierTranscriptRunInventory(
                        transcription_id="tx-02",
                        position=0,
                        source_image_refs=(
                            _q(
                                "segment-02",
                                "tx-02",
                                "image:assoc:tx-02:original",
                            ),
                        ),
                        t0_draft_refs=(
                            _q("segment-02", "tx-02", "t0:raw:pass_1"),
                        ),
                        working_draft_ref=_q(
                            "segment-02",
                            "tx-02",
                            "transcript_edit:working",
                        ),
                        working_latest_revision_ref=_q(
                            "segment-02",
                            "tx-02",
                            "transcript_edit:working:rev:0002",
                        ),
                        output_draft_ref=None,
                        artifact_fingerprint="d" * 64,
                        missing_resources=(),
                    ),
                ),
            ),
        ),
        topology_diagnostics=(
            DossierTopologyDiagnostic(
                code="association_missing",
                segment_id="segment-01",
                transcription_id="tx-01b",
                detail=r"C:\private\association.json",
            ),
        ),
    )


def test_dossier_startup_context_projects_complete_ordered_inventory() -> None:
    text = build_startup_context_block(_inventory()).text

    assert text.index("`segment-01`") < text.index("`segment-02`")
    assert "next `segment-02`" in text
    assert "previous `segment-01`" in text
    assert "`tx-01a`" in text and "`tx-01b`" in text and "`tx-02`" in text
    assert _q("segment-01", "tx-01a", "t0:raw:pass_1") in text
    assert _q("segment-02", "tx-02", "transcript_edit:working:rev:0002") in text
    assert "The runs below are peers" in text
    assert "source_image_missing" in text
    assert "association_missing" in text
    assert r"C:\private" not in text
    assert "path/metadata" not in text


def test_dossier_driver_is_mode_specific_and_preserves_one_run_semantics() -> None:
    pack = build_transcript_edit_domain_pack()
    dossier_blocks = pack.build_runtime_prompt_blocks(startup_inventory=_inventory())
    dossier_ids = [block.block_id for block in dossier_blocks]

    assert dossier_ids == [
        "mapping_family_branch",
        "transcript_edit_domain_branch",
        "transcript_edit_procedural_guidance",
        "transcript_edit_dossier_guidance",
        "transcript_edit_startup_context",
    ]
    dossier_text = next(
        block.text
        for block in dossier_blocks
        if block.block_id == "transcript_edit_dossier_guidance"
    ).lower()
    for required in (
        "one continuous semantic job",
        "bounded evidence windows",
        "not independent transcript-edit jobs",
        "peer candidate",
        "one explicitly chosen exact working revision",
        "source_revision_refs",
        "dependency fact",
    ):
        assert required in dossier_text
    for retired_fallback in ("automatically best", "longest, consensus"):
        assert retired_fallback in dossier_text


def test_dossier_tool_contracts_change_transport_not_capability_ids() -> None:
    leaf_specs = build_transcript_edit_tool_specs()
    dossier_specs = build_dossier_transcript_edit_tool_specs()
    assert [spec.tool_id for spec in dossier_specs] == [
        spec.tool_id for spec in leaf_specs
    ]

    by_id = {spec.tool_id: spec for spec in dossier_specs}
    save = by_id["save_workspace_artifact"]
    copy_forward = by_id["copy_forward_save_workspace_artifact"]
    publish = by_id["publish_workspace_artifact"]
    hydrate = by_id["hydrate_artifact_refs"]

    assert "target_ref" in save.expected_request_json_shape["properties"]
    assert "dossier-qualified" in save.expected_request_shape
    assert "target_ref" in copy_forward.expected_request_json_shape["properties"]
    assert publish.expected_request_json_shape["required"] == ["source_revision_refs"]
    assert set(publish.expected_request_json_shape["properties"]) == {
        "source_revision_refs"
    }
    assert "singular source_revision_ref field is not accepted" in (
        publish.expected_request_shape
    )
    assert "dossier_segment:" in hydrate.expected_request_shape
    assert "absolute_path" not in hydrate.expected_result_shape.lower()
    assert "{payload, path}" not in hydrate.expected_result_shape.lower()


def test_dossier_surface_payload_uses_dossier_contracts_only_when_selected() -> None:
    pack = build_transcript_edit_domain_pack()
    leaf_payload = pack.build_surface_payload()
    dossier_payload = pack.build_surface_payload(startup_inventory=_inventory())

    assert leaf_payload["tool_ids"] == dossier_payload["tool_ids"]
    leaf_publish = next(
        row
        for row in leaf_payload["tool_specs"]
        if row["tool_id"] == "publish_workspace_artifact"
    )
    dossier_publish = next(
        row
        for row in dossier_payload["tool_specs"]
        if row["tool_id"] == "publish_workspace_artifact"
    )
    assert leaf_publish["expected_request_json_shape"]["required"] == [
        "source_revision_ref"
    ]
    assert dossier_publish["expected_request_json_shape"]["required"] == [
        "source_revision_refs"
    ]
