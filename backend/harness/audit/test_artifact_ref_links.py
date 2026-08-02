"""Tests for audit artifact image link helpers."""

from __future__ import annotations

from pathlib import Path

from harness.audit.artifact_ref_links import (
    ArtifactLinkContext,
    build_ref_path_index,
    resolve_artifact_image_link,
    _extract_image_derived_leaf,
)


def test_resolve_relative_markdown_link(tmp_path: Path) -> None:
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    image_path = images_dir / "master.png"
    image_path.write_bytes(b"png")

    timeline_path = tmp_path / "audit" / "human" / "timeline.md"
    timeline_path.parent.mkdir(parents=True)

    index = {"image:derived:master-1": str(image_path)}
    context = ArtifactLinkContext(timeline_path=timeline_path, ref_path_index=index)
    link = resolve_artifact_image_link("image:derived:master-1", context)

    assert link is not None
    assert link.path == "../../images/master.png"
    assert link.markdown_link == "[open image](../../images/master.png)"


def test_missing_path_returns_none(tmp_path: Path) -> None:
    timeline_path = tmp_path / "audit" / "human" / "timeline.md"
    timeline_path.parent.mkdir(parents=True)
    context = ArtifactLinkContext(timeline_path=timeline_path, ref_path_index={})
    assert resolve_artifact_image_link("image:derived:missing", context) is None


def test_angle_brackets_for_paths_with_spaces(tmp_path: Path) -> None:
    images_dir = tmp_path / "my images"
    images_dir.mkdir()
    image_path = images_dir / "crop a.png"
    image_path.write_bytes(b"png")

    timeline_path = tmp_path / "audit" / "human" / "timeline.md"
    timeline_path.parent.mkdir(parents=True)

    context = ArtifactLinkContext(
        timeline_path=timeline_path,
        ref_path_index={"image:derived:crop-a": str(image_path)},
    )
    link = resolve_artifact_image_link("image:derived:crop-a", context)

    assert link is not None
    assert link.markdown_link == "[open image](<../../my images/crop a.png>)"


def test_build_ref_path_index_from_turn_nested_metadata() -> None:
    turn = {
        "tool_result_raw": {
            "outputs": {
                "derived_ref_id": "image:derived:master-1",
                "absolute_path": str(Path("C:/runs/master.png")),
            }
        }
    }
    index = build_ref_path_index(turn=turn)
    assert index["image:derived:master-1"] == str(Path("C:/runs/master.png"))


def test_resolve_dossiers_feature_graph_png_ref(tmp_path: Path, monkeypatch) -> None:
    png_dir = tmp_path / "feature_graphs" / "d1" / "mappings" / "map1"
    png_dir.mkdir(parents=True)
    png_path = png_dir / "clean.png"
    png_path.write_bytes(b"png")

    timeline_path = tmp_path / "audit" / "human" / "timeline.md"
    timeline_path.parent.mkdir(parents=True)
    ref = "artifact://dossiers/feature_graphs/d1/mappings/map1/clean.png"
    monkeypatch.setattr(
        "harness.audit.artifact_ref_links.dossiers_artifacts_root",
        lambda: tmp_path,
    )
    context = ArtifactLinkContext(timeline_path=timeline_path, ref_path_index={})
    link = resolve_artifact_image_link(ref, context)

    assert link is not None
    assert link.path.endswith("feature_graphs/d1/mappings/map1/clean.png".replace("/", "\\")) or link.path.endswith(
        "feature_graphs/d1/mappings/map1/clean.png"
    )
    assert "[open image]" in link.markdown_link


def test_inline_budget_respects_cap(tmp_path: Path) -> None:
    timeline_path = tmp_path / "audit" / "human" / "timeline.md"
    timeline_path.parent.mkdir(parents=True)
    context = ArtifactLinkContext(timeline_path=timeline_path, ref_path_index={}, inline_budget=2)
    assert context.consume_inline() is True
    assert context.consume_inline() is True
    assert context.consume_inline() is False
    assert context.inline_cap_reached is True


def test_extract_image_derived_leaf_is_delimiter_bounded() -> None:
    assert (
        _extract_image_derived_leaf(
            "dossier_segment:seg_a:run:tx_a:image:derived:crop-uuid-001"
        )
        == "image:derived:crop-uuid-001"
    )
    assert _extract_image_derived_leaf("image:derived:crop-uuid-001") == "image:derived:crop-uuid-001"
    assert _extract_image_derived_leaf("notimage:derived:crop-uuid-001") is None
    assert _extract_image_derived_leaf("dossier_segment:seg_a:run:tx_a:image:derived:") is None
    assert _extract_image_derived_leaf("artifact:sample") is None


def test_build_ref_path_index_binds_wrapper_qualified_ref_to_leaf_descriptor(
    tmp_path: Path,
) -> None:
    images = tmp_path / "images"
    images.mkdir()
    png = images / "crop.png"
    png.write_bytes(b"png")
    leaf = "image:derived:crop-uuid-q1"
    qualified = f"dossier_segment:seg_a:run:tx_a:{leaf}"
    # Leaf path from turn metadata; qualified appears only as runtime identity.
    index = build_ref_path_index(
        turn={
            "tool_result_raw": {
                "artifact_refs": [qualified],
                "outputs": {
                    "derived_ref_id": leaf,
                    "absolute_path": str(png.resolve()),
                    "crop_ref": qualified,
                },
            }
        }
    )
    assert index[leaf] == str(png.resolve())
    assert index[qualified] == str(png.resolve())

    # Also binds when leaf path arrives via shared_index (descriptor scan) only.
    index2 = build_ref_path_index(
        turn={
            "tool_result_raw": {
                "artifact_refs": [qualified],
                "outputs": {"derived_ref_id": qualified, "crop_ref": qualified},
            }
        },
        shared_index={leaf: str(png.resolve())},
    )
    assert index2[qualified] == str(png.resolve())
    assert index2[leaf] == str(png.resolve())


def test_wrapper_bind_skips_ambiguous_leaf_paths(tmp_path: Path) -> None:
    images = tmp_path / "images"
    images.mkdir()
    a = images / "a.png"
    b = images / "b.png"
    a.write_bytes(b"png")
    b.write_bytes(b"png")
    leaf = "image:derived:ambiguous-leaf"
    qualified = f"dossier_segment:seg_a:run:tx_a:{leaf}"
    turn = {
        "tool_result_raw": {
            "artifact_refs": [qualified],
            "outputs": {
                "items": [
                    {"derived_ref_id": leaf, "absolute_path": str(a.resolve())},
                    {"derived_ref_id": leaf, "absolute_path": str(b.resolve())},
                ]
            },
        }
    }
    index = build_ref_path_index(turn=turn)
    assert leaf in index  # first-wins retained for unqualified
    assert qualified not in index


def test_fabricated_wrapper_or_unknown_leaf_produces_no_binding() -> None:
    qualified = "dossier_segment:seg_a:run:tx_a:image:derived:missing-leaf"
    index = build_ref_path_index(
        turn={"tool_result_raw": {"artifact_refs": [qualified], "outputs": {"derived_ref_id": qualified}}}
    )
    assert qualified not in index
