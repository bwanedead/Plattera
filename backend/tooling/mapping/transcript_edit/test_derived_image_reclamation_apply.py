"""STORAGE-BR-010: quiescence-gated derived-image PNG cache reclamation apply."""

from __future__ import annotations

import inspect
import io
import json
import os
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

import config.paths as paths_mod
import tooling.mapping.transcript_edit.derived_image_descriptor as descriptor_mod
import tooling.mapping.transcript_edit.paths as te_paths_mod
from tooling.mapping.transcript_edit.artifact_hydration import make_hydrate_artifact_refs_handler
from tooling.mapping.transcript_edit.artifact_transform import make_transform_artifact_handler
from tooling.mapping.transcript_edit.derived_image_reclamation_apply import (
    REASON_APPLY_INVALID_TYPE,
    REASON_CANDIDATE_DELETE_FAILED,
    REASON_CANDIDATE_IDENTITY_CHANGED,
    REASON_CANDIDATE_IS_SYMLINK,
    REASON_CANDIDATE_NO_LONGER_ELIGIBLE,
    REASON_DELETION_BUDGET_INVALID,
    REASON_DESCRIPTOR_CHANGED,
    REASON_POST_DELETE_RECONSTRUCTION_FAILED,
    REASON_QUIESCENCE_CALLBACK_REQUIRED,
    REASON_RUN_ACTIVITY_UNKNOWN,
    REASON_RUN_NOT_QUIESCENT,
    REASON_RUN_SCOPE_UNKNOWN,
    SCHEMA_VERSION,
    apply_derived_image_reclamation,
)


def _root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "dossiers_data"
    root.mkdir()
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(te_paths_mod, "dossiers_root", lambda: root)
    return root


def _png_bytes(w: int = 100, h: int = 80, color: tuple[int, int, int] = (200, 200, 200)) -> bytes:
    img = Image.new("RGB", (w, h), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _write_assoc(root: Path, d: str, tx: str, image_path: Path) -> None:
    assoc_dir = root / "associations"
    assoc_dir.mkdir(parents=True, exist_ok=True)
    (assoc_dir / f"assoc_{d}.json").write_text(
        json.dumps(
            {
                "associations": [
                    {
                        "transcription_id": tx,
                        "metadata": {
                            "images": {
                                "original_path": str(image_path),
                                "processed_path": str(image_path),
                            }
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def _make_handlers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    d="d1",
    tx="tx-1",
    ws="ws-1",
):
    root = _root(tmp_path, monkeypatch)
    original_dir = root / "images" / "original"
    original_dir.mkdir(parents=True)
    img = original_dir / "scan.png"
    img.write_bytes(_png_bytes())
    _write_assoc(root, d, tx, img)
    transform = make_transform_artifact_handler(dossier_id=d, transcription_id=tx, workspace_key=ws)
    hydrate = make_hydrate_artifact_refs_handler(dossier_id=d, transcription_id=tx, workspace_key=ws)
    return transform, hydrate, root, f"image:assoc:{tx}:original"


def _crop(handler, ref_id: str) -> str:
    result = handler({"ref_id": ref_id, "sub_action": "crop", "params": {"box_norm": [0, 0, 0.5, 0.5]}})
    assert result["executed"] is True
    return result["outputs"]["derived_ref_id"]


def _derived_dir(root: Path, ws: str = "ws-1") -> Path:
    return root / "artifacts" / "transcript_edit" / "d1" / "tx-1" / ws / "derived_images"


def _snapshot_tree(root: Path) -> dict[str, tuple[bytes, int]]:
    out: dict[str, tuple[bytes, int]] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[p.relative_to(root).as_posix()] = (p.read_bytes(), p.stat().st_mtime_ns)
    return out


def _always_quiescent() -> str | None:
    return None


def test_dry_run_performs_zero_writes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    transform, _hydrate, root, ref_id = _make_handlers(tmp_path, monkeypatch)
    derived = _crop(transform, ref_id)
    before = _snapshot_tree(root)
    result = apply_derived_image_reclamation(
        dossier_id="d1",
        workspace_id="ws-1",
        apply=False,
    )
    assert result["status"] == "planned"
    assert result["deleted_count"] == 0
    assert result["bytes_reclaimed"] == 0
    assert derived.removeprefix("image:derived:") + ".png" in json.dumps(result)
    assert _snapshot_tree(root) == before


def test_apply_refuses_without_quiescence_callback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    transform, _hydrate, root, ref_id = _make_handlers(tmp_path, monkeypatch)
    _crop(transform, ref_id)
    result = apply_derived_image_reclamation(
        dossier_id="d1",
        workspace_id="ws-1",
        apply=True,
        quiescence_fn=None,
    )
    assert result["status"] == "refused"
    assert result["reason_code"] == REASON_QUIESCENCE_CALLBACK_REQUIRED
    assert _derived_dir(root).glob("*.png")


def test_apply_refuses_while_run_not_quiescent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    transform, _hydrate, root, ref_id = _make_handlers(tmp_path, monkeypatch)
    _crop(transform, ref_id)
    result = apply_derived_image_reclamation(
        dossier_id="d1",
        workspace_id="ws-1",
        apply=True,
        quiescence_fn=lambda: REASON_RUN_NOT_QUIESCENT,
    )
    assert result["status"] == "refused"
    assert result["reason_code"] == REASON_RUN_NOT_QUIESCENT
    assert list(_derived_dir(root).glob("*.png"))


def test_quiescence_lost_before_first_deletion_removes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transform, _hydrate, root, ref_id = _make_handlers(tmp_path, monkeypatch)
    _crop(transform, ref_id)
    calls = {"n": 0}

    def _quiescence() -> str | None:
        calls["n"] += 1
        if calls["n"] >= 2:
            return REASON_RUN_NOT_QUIESCENT
        return None

    result = apply_derived_image_reclamation(
        dossier_id="d1",
        workspace_id="ws-1",
        apply=True,
        quiescence_fn=_quiescence,
    )
    assert result["deleted_count"] == 0
    assert result["bytes_reclaimed"] == 0
    assert result["status"] == "refused"
    assert list(_derived_dir(root).glob("*.png"))


def test_quiescence_lost_between_candidates_stops_later_deletions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transform, _hydrate, root, ref_id = _make_handlers(tmp_path, monkeypatch)
    first = _crop(transform, ref_id)
    second = _crop(transform, ref_id)
    calls = {"n": 0}

    def _quiescence() -> str | None:
        calls["n"] += 1
        if calls["n"] >= 4:
            return REASON_RUN_NOT_QUIESCENT
        return None

    result = apply_derived_image_reclamation(
        dossier_id="d1",
        workspace_id="ws-1",
        apply=True,
        quiescence_fn=_quiescence,
        max_deletions=10,
    )
    assert result["deleted_count"] == 1
    assert result["aborted_count"] == 1
    remaining = {p.name for p in _derived_dir(root).glob("*.png")}
    assert len(remaining) == 1
    deleted_uuid = first.removeprefix("image:derived:")
    other_uuid = second.removeprefix("image:derived:")
    assert (f"{deleted_uuid}.png" in remaining) ^ (f"{other_uuid}.png" in remaining)


def test_one_verified_generic_png_deleted_descriptor_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transform, _hydrate, root, ref_id = _make_handlers(tmp_path, monkeypatch)
    derived = _crop(transform, ref_id)
    uuid = derived.removeprefix("image:derived:")
    desc_path = _derived_dir(root) / f"{uuid}.json"
    before_desc = desc_path.read_bytes()
    png_path = _derived_dir(root) / f"{uuid}.png"
    reclaimed = png_path.stat().st_size

    result = apply_derived_image_reclamation(
        dossier_id="d1",
        workspace_id="ws-1",
        apply=True,
        quiescence_fn=_always_quiescent,
    )
    assert result["status"] == "applied"
    assert result["deleted_count"] == 1
    assert result["bytes_reclaimed"] == reclaimed
    assert not png_path.exists()
    assert desc_path.read_bytes() == before_desc


def test_deleted_ref_hydrates_through_reconstruction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transform, hydrate, root, ref_id = _make_handlers(tmp_path, monkeypatch)
    derived = _crop(transform, ref_id)
    apply_derived_image_reclamation(
        dossier_id="d1",
        workspace_id="ws-1",
        apply=True,
        quiescence_fn=_always_quiescent,
    )
    out = hydrate({"ref_ids": [derived]})
    row = next(r for r in out["outputs"]["results"] if r["ref_id"] == derived)
    assert row.get("representation_kind") == "reconstructed_recipe"


def test_chained_transform_still_consumes_deleted_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transform, _hydrate, root, ref_id = _make_handlers(tmp_path, monkeypatch)
    parent = _crop(transform, ref_id)
    apply_derived_image_reclamation(
        dossier_id="d1",
        workspace_id="ws-1",
        apply=True,
        quiescence_fn=_always_quiescent,
    )
    child = transform({"ref_id": parent, "sub_action": "crop", "params": {"box_norm": [0, 0, 0.5, 0.5]}})
    assert child["executed"] is True


def test_referenced_generic_cache_still_eligible_and_reconstructible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transform, hydrate, root, ref_id = _make_handlers(tmp_path, monkeypatch)
    derived = _crop(transform, ref_id)
    working = root / "artifacts" / "transcript_edit" / "d1" / "tx-1" / "ws-1" / "working"
    working.mkdir(parents=True, exist_ok=True)
    (working / "rev_0001.json").write_text(
        json.dumps({"primary_evidence_ref": derived}),
        encoding="utf-8",
    )
    plan = apply_derived_image_reclamation(dossier_id="d1", workspace_id="ws-1", apply=False)
    assert plan["eligible_count"] >= 1
    apply_derived_image_reclamation(
        dossier_id="d1",
        workspace_id="ws-1",
        apply=True,
        quiescence_fn=_always_quiescent,
    )
    out = hydrate({"ref_ids": [derived]})
    assert out["outputs"]["results"][0].get("representation_kind") == "reconstructed_recipe"


@pytest.mark.parametrize(
    "fixture_fn",
    [
        lambda root: (root / "images" / "original" / "deed.png").write_bytes(_png_bytes()),
        lambda root: (root / "images" / "original" / "deed_derived_b034cdf9.png").write_bytes(
            _png_bytes(color=(1, 2, 3))
        ),
    ],
)
def test_canonical_and_legacy_never_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixture_fn
) -> None:
    transform, _hydrate, root, ref_id = _make_handlers(tmp_path, monkeypatch)
    _crop(transform, ref_id)
    original = root / "images" / "original"
    original.mkdir(parents=True, exist_ok=True)
    fixture_fn(root)
    canon_before = {
        p.name: p.read_bytes() for p in original.iterdir() if p.is_file()
    }
    apply_derived_image_reclamation(
        dossier_id="d1",
        workspace_id="ws-1",
        apply=True,
        quiescence_fn=_always_quiescent,
        max_deletions=100,
    )
    canon_after = {p.name: p.read_bytes() for p in original.iterdir() if p.is_file()}
    assert canon_after == canon_before


def test_point_crops_never_deleted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    transform, _hydrate, root, ref_id = _make_handlers(tmp_path, monkeypatch)
    result = transform(
        {
            "ref_id": ref_id,
            "sub_action": "point_crops",
            "params": {
                "points": [{"alias": "a", "point_norm": [0.4, 0.5], "size": "medium", "shape": "wide"}]
            },
        }
    )
    master = result["outputs"]["derived_ref_id"]
    before = _snapshot_tree(root)
    apply_derived_image_reclamation(
        dossier_id="d1",
        workspace_id="ws-1",
        apply=True,
        quiescence_fn=_always_quiescent,
        max_deletions=100,
    )
    assert _snapshot_tree(root) == before
    assert (_derived_dir(root) / f"{master.removeprefix('image:derived:')}.png").is_file()


def test_orphan_conflicting_unsafe_rows_never_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transform, _hydrate, root, ref_id = _make_handlers(tmp_path, monkeypatch)
    derived = _crop(transform, ref_id)
    di = _derived_dir(root)
    (di / ("b" * 32 + ".png")).write_bytes(_png_bytes(color=(5, 6, 7)))
    uuid = derived.removeprefix("image:derived:")
    moved = di / ("c" * 32 + ".png")
    moved.write_bytes((di / f"{uuid}.png").read_bytes())
    (di / f"{uuid}.png").unlink()
    desc = json.loads((di / f"{uuid}.json").read_text(encoding="utf-8"))
    desc["absolute_path"] = str(moved.resolve())
    (di / f"{uuid}.json").write_text(json.dumps(desc), encoding="utf-8")
    before = _snapshot_tree(root)
    apply_derived_image_reclamation(
        dossier_id="d1",
        workspace_id="ws-1",
        apply=True,
        quiescence_fn=_always_quiescent,
        max_deletions=100,
    )
    assert _snapshot_tree(root) == before


def test_changed_png_bytes_after_planning_cause_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transform, _hydrate, root, ref_id = _make_handlers(tmp_path, monkeypatch)
    derived = _crop(transform, ref_id)
    png = _derived_dir(root) / f"{derived.removeprefix('image:derived:')}.png"
    calls = {"n": 0}

    def _quiescence() -> str | None:
        calls["n"] += 1
        # Call 1: pre-inventory; call 2: pre-mutation; call 3: first candidate — mutate live bytes.
        if calls["n"] == 3:
            img = Image.open(png)
            img.load()
            alt = Image.new("RGB", img.size, color=(1, 2, 3))
            buf = io.BytesIO()
            alt.save(buf, format="PNG")
            png.write_bytes(buf.getvalue())
        return None

    result = apply_derived_image_reclamation(
        dossier_id="d1",
        workspace_id="ws-1",
        apply=True,
        quiescence_fn=_quiescence,
        max_deletions=1,
    )
    assert result["deleted_count"] == 0
    assert result["bytes_reclaimed"] == 0
    assert any(a.get("reason_code") == REASON_CANDIDATE_IDENTITY_CHANGED for a in result["artifacts"])
    assert png.is_file()


def test_changed_descriptor_or_recipe_fingerprint_causes_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transform, _hydrate, root, ref_id = _make_handlers(tmp_path, monkeypatch)
    derived = _crop(transform, ref_id)
    desc_path = _derived_dir(root) / f"{derived.removeprefix('image:derived:')}.json"
    calls = {"n": 0}

    def _quiescence() -> str | None:
        calls["n"] += 1
        if calls["n"] == 3:
            desc = json.loads(desc_path.read_text(encoding="utf-8"))
            desc["note"] = "operator-mutated"
            desc_path.write_text(json.dumps(desc), encoding="utf-8")
        return None

    result = apply_derived_image_reclamation(
        dossier_id="d1",
        workspace_id="ws-1",
        apply=True,
        quiescence_fn=_quiescence,
        max_deletions=1,
    )
    assert result["deleted_count"] == 0
    assert any(a.get("reason_code") == REASON_DESCRIPTOR_CHANGED for a in result["artifacts"])


def test_delete_failure_reports_zero_reclaimed_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transform, _hydrate, root, ref_id = _make_handlers(tmp_path, monkeypatch)
    _crop(transform, ref_id)

    def _fail_delete(_path: Path) -> None:
        raise OSError("simulated delete failure")

    result = apply_derived_image_reclamation(
        dossier_id="d1",
        workspace_id="ws-1",
        apply=True,
        quiescence_fn=_always_quiescent,
        delete_fn=_fail_delete,
    )
    assert result["deleted_count"] == 0
    assert result["bytes_reclaimed"] == 0
    assert any(a.get("reason_code") == REASON_CANDIDATE_DELETE_FAILED for a in result["artifacts"])


def test_broken_symlink_rejected_without_following(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transform, _hydrate, root, ref_id = _make_handlers(tmp_path, monkeypatch)
    derived = _crop(transform, ref_id)
    png = _derived_dir(root) / f"{derived.removeprefix('image:derived:')}.png"
    calls = {"n": 0}

    def _quiescence() -> str | None:
        calls["n"] += 1
        if calls["n"] == 3:
            _install_png_symlink_mocks(monkeypatch, png)
        return None

    result = apply_derived_image_reclamation(
        dossier_id="d1",
        workspace_id="ws-1",
        apply=True,
        quiescence_fn=_quiescence,
        max_deletions=1,
    )
    assert result["deleted_count"] == 0
    assert any(a.get("reason_code") == REASON_CANDIDATE_IS_SYMLINK for a in result["artifacts"])


def _install_png_symlink_mocks(monkeypatch: pytest.MonkeyPatch, png: Path) -> None:
    PathCls = type(png)
    orig_lexists = os.path.lexists
    orig_islink = os.path.islink
    orig_is_symlink = PathCls.is_symlink
    target = os.fspath(png)

    def fake_lexists(path: Any) -> bool:
        if os.fspath(path) == target:
            return True
        return orig_lexists(path)

    def fake_islink(path: Any) -> bool:
        if os.fspath(path) == target:
            return True
        return orig_islink(path)

    def fake_is_symlink(self: PathCls) -> bool:
        if os.fspath(self) == target:
            return True
        return orig_is_symlink(self)

    monkeypatch.setattr(os.path, "lexists", fake_lexists)
    monkeypatch.setattr(os.path, "islink", fake_islink)
    monkeypatch.setattr(PathCls, "is_symlink", fake_is_symlink)
    monkeypatch.setattr(descriptor_mod.os.path, "islink", fake_islink)


def test_operator_cap_applies_deterministically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    transform, _hydrate, root, ref_id = _make_handlers(tmp_path, monkeypatch)
    for _ in range(3):
        _crop(transform, ref_id)
    full = apply_derived_image_reclamation(
        dossier_id="d1", workspace_id="ws-1", apply=False, max_deletions=100
    )
    capped = apply_derived_image_reclamation(
        dossier_id="d1", workspace_id="ws-1", apply=False, max_deletions=1
    )
    assert capped["eligible_count"] == full["eligible_count"]
    assert capped["selected_count"] == 1
    assert capped["not_selected_count"] == full["eligible_count"] - 1


def test_no_recursive_delete_or_glob_deletion_helpers() -> None:
    import tooling.mapping.transcript_edit.derived_image_reclamation_apply as mod

    source = inspect.getsource(mod)
    assert "rmtree" not in source
    assert "glob(" not in source
    assert "rglob(" not in source


def test_output_contains_no_absolute_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    transform, _hydrate, root, ref_id = _make_handlers(tmp_path, monkeypatch)
    _crop(transform, ref_id)
    result = apply_derived_image_reclamation(dossier_id="d1", workspace_id="ws-1", apply=False)
    blob = json.dumps(result)
    assert "absolute_path" not in blob
    assert ":\\" not in blob


def test_invalid_deletion_budget_refused() -> None:
    result = apply_derived_image_reclamation(
        dossier_id="d1",
        workspace_id="ws-1",
        apply=False,
        max_deletions=-1,
    )
    assert result["reason_code"] == REASON_DELETION_BUDGET_INVALID


def test_changed_recipe_source_before_delete_keeps_png(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fresh recipe reconstruction must refuse unlink when the source image changed."""
    transform, _hydrate, root, ref_id = _make_handlers(tmp_path, monkeypatch)
    derived = _crop(transform, ref_id)
    png = _derived_dir(root) / f"{derived.removeprefix('image:derived:')}.png"
    source = root / "images" / "original" / "scan.png"
    before_png = png.read_bytes()
    calls = {"n": 0}

    def _quiescence() -> str | None:
        calls["n"] += 1
        if calls["n"] == 3:
            # Change the assoc source so recipe reconstruction no longer matches cached pixels.
            source.write_bytes(_png_bytes(color=(10, 20, 30)))
        return None

    result = apply_derived_image_reclamation(
        dossier_id="d1",
        workspace_id="ws-1",
        apply=True,
        quiescence_fn=_quiescence,
        max_deletions=1,
    )
    assert result["deleted_count"] == 0
    assert result["bytes_reclaimed"] == 0
    assert png.is_file()
    assert png.read_bytes() == before_png
    assert any(
        a.get("reason_code")
        in {REASON_CANDIDATE_IDENTITY_CHANGED, REASON_CANDIDATE_NO_LONGER_ELIGIBLE}
        for a in result["artifacts"]
    )


def test_post_delete_reconstruction_failure_counts_deleted_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tooling.mapping.transcript_edit.derived_image_reclamation_apply as apply_mod
    from tooling.mapping.transcript_edit.derived_image_resolution import (
        DerivedImageResolutionError,
    )

    transform, _hydrate, root, ref_id = _make_handlers(tmp_path, monkeypatch)
    first = _crop(transform, ref_id)
    second = _crop(transform, ref_id)
    orig_resolve = apply_mod.resolve_derived_image_for_read

    def _resolve_fail_after_unlink(**kwargs: Any):
        target = kwargs.get("ref_id") or ""
        path = _derived_dir(root) / f"{str(target).removeprefix('image:derived:')}.png"
        if not path.exists():
            raise DerivedImageResolutionError(
                "recipe_unavailable",
                "forced post-delete reconstruction failure",
            )
        return orig_resolve(**kwargs)

    monkeypatch.setattr(apply_mod, "resolve_derived_image_for_read", _resolve_fail_after_unlink)

    result = apply_derived_image_reclamation(
        dossier_id="d1",
        workspace_id="ws-1",
        apply=True,
        quiescence_fn=_always_quiescent,
        max_deletions=10,
    )
    assert result["deleted_count"] == 1
    assert result["bytes_reclaimed"] > 0
    assert result["status"] == "partially_applied"
    assert result["reason_code"] == REASON_POST_DELETE_RECONSTRUCTION_FAILED
    failed = [a for a in result["artifacts"] if a.get("status") == "deleted_reconstruction_failed"]
    assert len(failed) == 1
    failed_ref = failed[0]["ref_id"]
    assert failed_ref in {first, second}
    assert failed[0]["size_bytes"] == result["bytes_reclaimed"]
    remaining = second if failed_ref == first else first
    assert (_derived_dir(root) / f"{remaining.removeprefix('image:derived:')}.png").is_file()
    assert not (_derived_dir(root) / f"{failed_ref.removeprefix('image:derived:')}.png").exists()


def test_apply_rejects_non_boolean_apply_without_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transform, _hydrate, root, ref_id = _make_handlers(tmp_path, monkeypatch)
    _crop(transform, ref_id)
    before = _snapshot_tree(root)
    result = apply_derived_image_reclamation(
        dossier_id="d1",
        workspace_id="ws-1",
        apply="false",  # type: ignore[arg-type]
    )
    assert result["status"] == "refused"
    assert result["reason_code"] == REASON_APPLY_INVALID_TYPE
    assert result["apply"] is False
    assert result["deleted_count"] == 0
    assert _snapshot_tree(root) == before


def test_post_delete_reconstruction_failure_reports_ineligible_when_recipe_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transform, _hydrate, root, ref_id = _make_handlers(tmp_path, monkeypatch)
    derived = _crop(transform, ref_id)
    desc_path = _derived_dir(root) / f"{derived.removeprefix('image:derived:')}.json"
    desc = json.loads(desc_path.read_text(encoding="utf-8"))
    desc.pop("recipe", None)
    desc.pop("recipe_fingerprint", None)
    desc_path.write_text(json.dumps(desc), encoding="utf-8")

    result = apply_derived_image_reclamation(
        dossier_id="d1",
        workspace_id="ws-1",
        apply=True,
        quiescence_fn=_always_quiescent,
        max_deletions=1,
    )
    assert result["deleted_count"] == 0
    assert result["eligible_count"] == 0


@pytest.mark.parametrize(
    "bad_result",
    [False, 0, "", "   ", {}, []],
    ids=["false", "zero", "blank", "whitespace", "mapping", "list"],
)
def test_malformed_quiescence_result_refuses_before_unlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad_result: Any
) -> None:
    transform, _hydrate, root, ref_id = _make_handlers(tmp_path, monkeypatch)
    derived = _crop(transform, ref_id)
    png = _derived_dir(root) / f"{derived.removeprefix('image:derived:')}.png"
    before = png.read_bytes()

    result = apply_derived_image_reclamation(
        dossier_id="d1",
        workspace_id="ws-1",
        apply=True,
        quiescence_fn=lambda: bad_result,  # type: ignore[arg-type,return-value]
    )
    assert result["status"] == "refused"
    assert result["reason_code"] == REASON_RUN_ACTIVITY_UNKNOWN
    assert result["deleted_count"] == 0
    assert result["bytes_reclaimed"] == 0
    assert png.is_file()
    assert png.read_bytes() == before


def test_quiescence_exception_refuses_before_unlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transform, _hydrate, root, ref_id = _make_handlers(tmp_path, monkeypatch)
    derived = _crop(transform, ref_id)
    png = _derived_dir(root) / f"{derived.removeprefix('image:derived:')}.png"
    before = png.read_bytes()

    def _boom() -> str | None:
        raise RuntimeError("quiescence probe failed")

    result = apply_derived_image_reclamation(
        dossier_id="d1",
        workspace_id="ws-1",
        apply=True,
        quiescence_fn=_boom,
    )
    assert result["status"] == "refused"
    assert result["reason_code"] == REASON_RUN_ACTIVITY_UNKNOWN
    assert result["deleted_count"] == 0
    assert png.read_bytes() == before


@pytest.mark.parametrize(
    "kwargs",
    [
        {"dossier_id": 123, "workspace_id": "ws-1"},
        {"dossier_id": "d1", "workspace_id": True},
        {"dossier_id": "d1", "workspace_id": "ws-1", "transcription_id": 7},
        {"dossier_id": "d1", "workspace_id": "ws-1", "transcription_id": ""},
        {"dossier_id": "d1", "workspace_id": "ws-1", "run_id": 99},
        {"dossier_id": "d1", "workspace_id": "ws-1", "run_id": ""},
        {"dossier_id": "", "workspace_id": "ws-1"},
        {"dossier_id": "d1", "workspace_id": "  "},
    ],
)
def test_tooling_scope_types_refuse_before_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kwargs: dict[str, Any]
) -> None:
    transform, _hydrate, root, ref_id = _make_handlers(tmp_path, monkeypatch)
    _crop(transform, ref_id)
    before = _snapshot_tree(root)
    result = apply_derived_image_reclamation(apply=False, **kwargs)  # type: ignore[arg-type]
    assert result["status"] == "refused"
    assert result["reason_code"] == REASON_RUN_SCOPE_UNKNOWN
    assert result["eligible_count"] == 0
    assert _snapshot_tree(root) == before


def test_tooling_scope_types_refuse_before_quiescence_on_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transform, _hydrate, root, ref_id = _make_handlers(tmp_path, monkeypatch)
    _crop(transform, ref_id)
    before = _snapshot_tree(root)
    called = {"n": 0}

    def _quiescence() -> str | None:
        called["n"] += 1
        return None

    result = apply_derived_image_reclamation(
        dossier_id=1,  # type: ignore[arg-type]
        workspace_id="ws-1",
        apply=True,
        quiescence_fn=_quiescence,
    )
    assert result["status"] == "refused"
    assert result["reason_code"] == REASON_RUN_SCOPE_UNKNOWN
    assert called["n"] == 0
    assert _snapshot_tree(root) == before
