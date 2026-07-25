"""Tests for dossier action result-ref remapping."""

from __future__ import annotations

from copy import deepcopy

import pytest

from tooling.mapping.transcript_edit.dossier_action_result_refs import (
    DossierActionResultRefError,
    project_dossier_leaf_failure,
    remap_dossier_action_result,
)
from tooling.mapping.transcript_edit.dossier_artifact_refs import (
    DossierArtifactRefTarget,
    build_dossier_artifact_ref_index,
    qualify_leaf_ref,
)


def _index():
    entries = []
    for segment_id, transcription_id, leaf_ref in (
        ("seg_a", "tx_a", "image:assoc:tx_a:original"),
        ("seg_b", "tx_b", "image:assoc:tx_b:original"),
        ("seg_a", "tx_a", "t0:raw:draft_1"),
        ("seg_b", "tx_b", "t0:raw:draft_1"),
    ):
        q = qualify_leaf_ref(
            segment_id=segment_id,
            transcription_id=transcription_id,
            leaf_ref=leaf_ref,
        )
        entries.append(
            (
                q,
                DossierArtifactRefTarget(
                    segment_id=segment_id,
                    transcription_id=transcription_id,
                    leaf_ref=leaf_ref,
                ),
            )
        )
    return build_dossier_artifact_ref_index(
        dossier_id="d1",
        topology_fingerprint="fp",
        entries=entries,
        run_bindings=frozenset({("seg_a", "tx_a"), ("seg_b", "tx_b")}),
    )


def test_remaps_leaf_local_refs_and_strips_host_binary() -> None:
    index = _index()
    target = DossierArtifactRefTarget(
        segment_id="seg_a",
        transcription_id="tx_a",
        leaf_ref="image:assoc:tx_a:original",
    )
    leaf = {
        "executed": True,
        "artifact_refs": ["image:derived:abcdef0123456789abcdef0123456789"],
        "outputs": {
            "derived_ref_id": "image:derived:abcdef0123456789abcdef0123456789",
            "parent_ref_id": "image:assoc:tx_a:original",
            "source_unwrapped_from_ref": "image:derived:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "rendered_evidence_refs": [
                {"rendered_ref": "image:derived:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "count": 1}
            ],
            "path": r"C:\Users\example\secret.png",
            "absolute_path": r"C:\Users\example\secret.png",
            "image_b64": "abc",
            "basename": "out.png",
            "width_height": [10, 20],
        },
        "image_evidence": [
            {
                "ref_id": "image:derived:abcdef0123456789abcdef0123456789",
                "bytes": b"\xff\xd8",
                "absolute_path": r"C:\Users\example\secret.png",
            }
        ],
    }
    original = deepcopy(leaf)
    out = remap_dossier_action_result(result=leaf, ref_index=index, target=target)
    assert leaf == original
    assert out["segment_id"] == "seg_a"
    assert out["transcription_id"] == "tx_a"
    q_derived = qualify_leaf_ref(
        segment_id="seg_a",
        transcription_id="tx_a",
        leaf_ref="image:derived:abcdef0123456789abcdef0123456789",
    )
    assert out["artifact_refs"] == [q_derived]
    assert out["outputs"]["derived_ref_id"] == q_derived
    assert out["outputs"]["parent_ref_id"] == qualify_leaf_ref(
        segment_id="seg_a",
        transcription_id="tx_a",
        leaf_ref="image:assoc:tx_a:original",
    )
    assert out["outputs"]["source_unwrapped_from_ref"].startswith("dossier_segment:seg_a:")
    assert out["outputs"]["rendered_evidence_refs"][0]["rendered_ref"].startswith(
        "dossier_segment:seg_a:"
    )
    assert out["outputs"]["basename"] == "out.png"
    assert out["outputs"]["width_height"] == [10, 20]
    assert "path" not in out["outputs"]
    assert "absolute_path" not in out["outputs"]
    assert "image_b64" not in out["outputs"]
    assert out["image_evidence"][0]["ref_id"] == q_derived
    assert out["image_evidence"][0]["bytes"] == b"\xff\xd8"
    assert out["image_evidence"][0]["absolute_path"] == r"C:\Users\example\secret.png"


def test_fabricated_qualified_ref_is_refused() -> None:
    index = _index()
    target = DossierArtifactRefTarget(
        segment_id="seg_a",
        transcription_id="tx_a",
        leaf_ref="t0:raw:draft_1",
    )
    with pytest.raises(DossierActionResultRefError) as exc:
        remap_dossier_action_result(
            result={
                "executed": True,
                "artifact_refs": ["dossier_segment:seg_a:run:tx_a:evil:artifact"],
            },
            ref_index=index,
            target=target,
        )
    assert exc.value.code == "dossier_result_ref_remap_failed"


def test_malformed_qualified_revision_ref_is_refused() -> None:
    index = _index()
    target = DossierArtifactRefTarget(
        segment_id="seg_a",
        transcription_id="tx_a",
        leaf_ref="transcript_edit:working",
    )
    with pytest.raises(DossierActionResultRefError) as exc:
        remap_dossier_action_result(
            result={
                "executed": True,
                "outputs": {
                    "working_draft_ref": "dossier_segment:seg_a:run:tx_a:transcript_edit:working:rev:12"
                },
            },
            ref_index=index,
            target=target,
        )
    assert exc.value.code == "dossier_result_ref_remap_failed"


def test_qualified_unknown_run_is_refused() -> None:
    index = _index()
    target = DossierArtifactRefTarget(
        segment_id="seg_a",
        transcription_id="tx_a",
        leaf_ref="transcript_edit:working",
    )
    with pytest.raises(DossierActionResultRefError) as exc:
        remap_dossier_action_result(
            result={
                "executed": True,
                "artifact_refs": [
                    "dossier_segment:missing:run:tx_z:transcript_edit:working:rev:0001"
                ],
            },
            ref_index=index,
            target=target,
        )
    assert exc.value.code == "dossier_result_ref_remap_failed"


def test_malformed_qualified_derived_ref_is_refused() -> None:
    index = _index()
    target = DossierArtifactRefTarget(
        segment_id="seg_a",
        transcription_id="tx_a",
        leaf_ref="image:assoc:tx_a:original",
    )
    with pytest.raises(DossierActionResultRefError) as exc:
        remap_dossier_action_result(
            result={
                "executed": True,
                "outputs": {
                    "derived_ref_id": "dossier_segment:seg_a:run:tx_a:image:derived:not-hex!!"
                },
            },
            ref_index=index,
            target=target,
        )
    assert exc.value.code == "dossier_result_ref_remap_failed"


def test_preserves_cross_segment_qualified_evidence_refs() -> None:
    index = _index()
    target = DossierArtifactRefTarget(
        segment_id="seg_a",
        transcription_id="tx_a",
        leaf_ref="transcript_edit:working",
    )
    cross = qualify_leaf_ref(
        segment_id="seg_b",
        transcription_id="tx_b",
        leaf_ref="image:assoc:tx_b:original",
    )
    leaf = {
        "executed": True,
        "artifact_refs": ["transcript_edit:working:rev:0001", "transcript_edit:working"],
        "outputs": {
            "working_draft_ref": "transcript_edit:working:rev:0001",
            "aggregate_working_ref": "transcript_edit:working",
            "evidence_refs": [cross, "image:assoc:tx_a:original"],
            "workspace_root": r"C:\Users\example\workspace",
            "revision_relative_path": "working/rev_0001.json",
        },
    }
    out = remap_dossier_action_result(result=leaf, ref_index=index, target=target)
    assert out["outputs"]["evidence_refs"][0] == cross
    assert out["outputs"]["evidence_refs"][1] == qualify_leaf_ref(
        segment_id="seg_a",
        transcription_id="tx_a",
        leaf_ref="image:assoc:tx_a:original",
    )
    assert "workspace_root" not in out["outputs"]
    assert "revision_relative_path" not in out["outputs"]
    assert out["artifact_refs"][0] == qualify_leaf_ref(
        segment_id="seg_a",
        transcription_id="tx_a",
        leaf_ref="transcript_edit:working:rev:0001",
    )


def test_unqualified_foreign_assoc_ref_keeps_original_owner() -> None:
    index = _index()
    target = DossierArtifactRefTarget(
        segment_id="seg_a",
        transcription_id="tx_a",
        leaf_ref="transcript_edit:working",
    )
    out = remap_dossier_action_result(
        result={
            "executed": True,
            "outputs": {
                "evidence_refs": ["image:assoc:tx_b:original"],
            },
        },
        ref_index=index,
        target=target,
    )
    assert out["outputs"]["evidence_refs"][0] == qualify_leaf_ref(
        segment_id="seg_b",
        transcription_id="tx_b",
        leaf_ref="image:assoc:tx_b:original",
    )


def test_unknown_strings_are_not_guessed_into_refs() -> None:
    index = _index()
    target = DossierArtifactRefTarget(
        segment_id="seg_a",
        transcription_id="tx_a",
        leaf_ref="t0:raw:draft_1",
    )
    out = remap_dossier_action_result(
        result={
            "executed": True,
            "outputs": {"note": "not-a-ref", "status": "ok"},
        },
        ref_index=index,
        target=target,
    )
    assert out["outputs"]["note"] == "not-a-ref"


def test_leaf_failure_projection_strips_paths_keeps_repair_hint() -> None:
    index = _index()
    target = DossierArtifactRefTarget(
        segment_id="seg_a",
        transcription_id="tx_a",
        leaf_ref="image:assoc:tx_a:original",
    )
    missing = project_dossier_leaf_failure(
        result={
            "executed": False,
            "refusal": {
                "reason_code": "source_image_missing",
                "retryable": False,
                "blocked_by_invariant": True,
                "blocked_by_budget": False,
                "missing_inputs": [],
            },
            "outputs": {
                "error": {
                    "code": "source_image_missing",
                    "message": r"missing C:\Users\example\AppData\Local\scan.png",
                },
                "absolute_path": r"C:\Users\example\AppData\Local\scan.png",
            },
        },
        ref_index=index,
        target=target,
    )
    blob = str(missing)
    assert "AppData" not in blob
    assert r"C:\Users" not in blob
    assert missing["outputs"]["error"]["code"] == "source_image_missing"
    assert "absolute_path" not in missing["outputs"]
    assert missing["segment_id"] == "seg_a"

    param = project_dossier_leaf_failure(
        result={
            "executed": False,
            "refusal": {
                "reason_code": "invalid_transform_params",
                "retryable": True,
                "blocked_by_invariant": False,
                "blocked_by_budget": False,
                "missing_inputs": [],
            },
            "outputs": {
                "error": {
                    "code": "invalid_transform_params",
                    "message": "crop requires params.box or params.box_norm.",
                    "repair_hint": 'Provide params.box_norm = [0.0, 0.0, 1.0, 1.0].',
                }
            },
        },
        ref_index=index,
        target=target,
    )
    assert param["refusal"]["retryable"] is True
    assert param["outputs"]["error"]["repair_hint"].startswith("Provide params.box_norm")
    assert "absolute_path" not in str(param)
