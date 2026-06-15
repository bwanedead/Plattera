"""Tests for point-crop clean-source lineage resolution."""

from __future__ import annotations

from tooling.mapping.transcript_edit.point_crop_source_lineage import (
    repair_stored_point_crop_source_ref,
    resolve_point_crop_source_lineage,
)


def _desc(
    *,
    ref_id: str,
    role: str,
    source_ref: str,
    parent_ref_id: str | None = None,
    root_source_ref: str | None = None,
) -> dict:
    return {
        "ref_id": ref_id,
        "parent_ref_id": parent_ref_id or source_ref,
        "root_source_ref": root_source_ref,
        "transform_metadata": {
            "source_ref": source_ref,
            "overlay": {"overlay_role": role},
        },
    }


def test_resolve_assoc_ref_is_already_clean() -> None:
    lineage, error = resolve_point_crop_source_lineage(
        ref_id="image:assoc:tx-1:original",
        dossier_id="d1",
        transcription_id="tx-1",
        workspace_key="ws-1",
        loader=lambda *_args: None,
    )
    assert error is None
    assert lineage is not None
    assert lineage.clean_source_ref == "image:assoc:tx-1:original"
    assert lineage.placement_surface_ref is None


def test_resolve_scaffold_ref_unwraps_to_clean_source() -> None:
    scaffold_ref = "image:derived:scaffold"
    clean_ref = "image:assoc:tx-1:original"

    def loader(_d: str, _tx: str, _ws: str, ref: str):
        if ref == scaffold_ref:
            return _desc(
                ref_id=scaffold_ref,
                role="point_crop_placement_scaffold",
                source_ref=clean_ref,
            )
        return None

    lineage, error = resolve_point_crop_source_lineage(
        ref_id=scaffold_ref,
        dossier_id="d1",
        transcription_id="tx-1",
        workspace_key="ws-1",
        loader=loader,
    )
    assert error is None
    assert lineage is not None
    assert lineage.clean_source_ref == clean_ref
    assert lineage.placement_surface_ref == scaffold_ref
    assert lineage.source_unwrapped_from_ref == scaffold_ref


def test_repair_stored_polluted_source_ref_marks_legacy_warning() -> None:
    scaffold_ref = "image:derived:scaffold"
    clean_ref = "image:assoc:tx-1:original"

    def loader(_d: str, _tx: str, _ws: str, ref: str):
        if ref == scaffold_ref:
            return _desc(
                ref_id=scaffold_ref,
                role="point_crop_placement_scaffold",
                source_ref=clean_ref,
            )
        return None

    lineage, error = repair_stored_point_crop_source_ref(
        scaffold_ref,
        dossier_id="d1",
        transcription_id="tx-1",
        workspace_key="ws-1",
        placement_surface_ref=scaffold_ref,
        loader=loader,
    )
    assert error is None
    assert lineage is not None
    assert lineage.clean_source_ref == clean_ref
    assert lineage.legacy_source_repaired is True
    assert lineage.legacy_source_repair_warning


def test_resolve_regular_derived_crop_stays_local_source() -> None:
    crop_ref = "image:derived:crop"

    def loader(_d: str, _tx: str, _ws: str, ref: str):
        if ref == crop_ref:
            return {
                "ref_id": crop_ref,
                "parent_ref_id": "image:assoc:tx-1:original",
                "sub_action": "crop",
                "transform_metadata": {"source_ref": "image:assoc:tx-1:original"},
            }
        return None

    lineage, error = resolve_point_crop_source_lineage(
        ref_id=crop_ref,
        dossier_id="d1",
        transcription_id="tx-1",
        workspace_key="ws-1",
        loader=loader,
    )
    assert error is None
    assert lineage is not None
    assert lineage.clean_source_ref == crop_ref
    assert lineage.placement_surface_ref is None
