"""Tests for harness operator derived-image cache reclamation CLI."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from PIL import Image

import config.paths as paths_mod
import tooling.mapping.transcript_edit.paths as te_paths_mod
from harness.cli import run_state as rs
from harness.cli.reclaim_derived_image_cache import (
    main,
    reclaim_derived_image_cache,
    resolve_reclamation_scope_from_run,
)
from harness.cli.run_layout import allocate_run_directory
from harness.cli.run_quiescence import REASON_RUN_ACTIVITY_UNKNOWN, assess_run_quiescence
from harness.cli import resume_checkpoint_compress as compress_mod
from tooling.mapping.transcript_edit.artifact_transform import make_transform_artifact_handler


def _png_bytes() -> bytes:
    img = Image.new("RGB", (40, 30), color=(200, 200, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _seed_run(
    isolated_harness_root: Path,
    *,
    run_id: str,
    launch: dict,
    pid: int = 999999999,
    domain_id: str = "transcript_edit",
) -> None:
    run_dir = allocate_run_directory(run_id=run_id, run_collection="deed_to_ir")
    spawn_argv = [
        "python",
        "-m",
        "harness.runtime.runner.entrypoint",
        "--domain-id",
        domain_id,
        "--launch-context-json",
        json.dumps(launch, separators=(",", ":")),
    ]
    state = rs.new_run_state(
        run_id=run_id,
        pid=pid,
        loop_kind="deed_to_ir",
        mode="live",
        spawn_argv=spawn_argv,
        run_dir=run_dir,
    )
    rs.write_state(state)


def _setup_dossier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, workspace_id: str) -> Path:
    root = tmp_path / "dossiers_data"
    root.mkdir()
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(te_paths_mod, "dossiers_root", lambda: root)
    original = root / "images" / "original"
    original.mkdir(parents=True)
    scan = original / "scan.png"
    scan.write_bytes(_png_bytes())
    assoc_dir = root / "associations"
    assoc_dir.mkdir(parents=True)
    (assoc_dir / "assoc_d1.json").write_text(
        json.dumps(
            {
                "associations": [
                    {
                        "transcription_id": "tx-1",
                        "metadata": {
                            "images": {
                                "original_path": str(scan),
                                "processed_path": str(scan),
                            }
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    handler = make_transform_artifact_handler(
        dossier_id="d1", transcription_id="tx-1", workspace_key=workspace_id
    )
    handler(
        {
            "ref_id": "image:assoc:tx-1:original",
            "sub_action": "crop",
            "params": {"box_norm": [0, 0, 0.5, 0.5]},
        }
    )
    return root


def test_resolve_scope_uses_run_id_as_workspace_when_omitted(isolated_harness_root) -> None:
    run_id = "reclaim-scope-ws-default"
    _seed_run(
        isolated_harness_root,
        run_id=run_id,
        launch={"dossier_id": "d1", "transcription_id": "tx-1"},
    )
    scope, err = resolve_reclamation_scope_from_run(run_id)
    assert err is None
    assert scope is not None
    assert scope["workspace_id"] == run_id
    assert scope["dossier_id"] == "d1"


def test_resolve_scope_refuses_missing_dossier(isolated_harness_root) -> None:
    run_id = "reclaim-scope-missing"
    _seed_run(isolated_harness_root, run_id=run_id, launch={"workspace_id": "ws-1"})
    scope, err = resolve_reclamation_scope_from_run(run_id)
    assert scope is None
    assert err == "run_scope_unknown"


def test_cli_dry_run_zero_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_harness_root
) -> None:
    run_id = "reclaim-cli-dry"
    _seed_run(
        isolated_harness_root,
        run_id=run_id,
        launch={"dossier_id": "d1", "transcription_id": "tx-1", "workspace_id": "ws-1"},
    )
    root = _setup_dossier(tmp_path, monkeypatch, workspace_id="ws-1")
    before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert main(["--run-id", run_id]) == 0
    after = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert before == after


def test_cli_apply_refuses_live_pid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_harness_root
) -> None:
    run_id = "reclaim-cli-live"
    _seed_run(
        isolated_harness_root,
        run_id=run_id,
        launch={"dossier_id": "d1", "transcription_id": "tx-1", "workspace_id": "ws-1"},
        pid=4242,
    )
    _setup_dossier(tmp_path, monkeypatch, workspace_id="ws-1")
    monkeypatch.setattr(
        "harness.cli.reclaim_derived_image_cache.assess_run_quiescence",
        lambda _rid: "run_not_quiescent",
    )
    result = reclaim_derived_image_cache(run_id=run_id, apply=True)
    assert result["status"] == "refused"
    assert result["reason_code"] == "run_not_quiescent"


def test_quiescence_seam_shared_with_resume_checkpoint_compress() -> None:
    from harness.cli.run_quiescence import assess_run_quiescence as shared

    assert shared is compress_mod.assess_run_quiescence


def test_unknown_run_activity_refuses_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, isolated_harness_root
) -> None:
    run_id = "reclaim-unknown-activity"
    _seed_run(
        isolated_harness_root,
        run_id=run_id,
        launch={"dossier_id": "d1", "transcription_id": "tx-1", "workspace_id": "ws-1"},
    )
    _setup_dossier(tmp_path, monkeypatch, workspace_id="ws-1")
    monkeypatch.setattr(
        "harness.cli.reclaim_derived_image_cache.assess_run_quiescence",
        lambda _rid: REASON_RUN_ACTIVITY_UNKNOWN,
    )
    result = reclaim_derived_image_cache(run_id=run_id, apply=True)
    assert result["status"] == "refused"
    assert result["reason_code"] == REASON_RUN_ACTIVITY_UNKNOWN


def test_non_transcript_edit_domain_is_run_scope_unknown(isolated_harness_root) -> None:
    run_id = "reclaim-wrong-domain"
    _seed_run(
        isolated_harness_root,
        run_id=run_id,
        launch={"dossier_id": "d1", "transcription_id": "tx-1", "workspace_id": "ws-1"},
        domain_id="deed_to_ir",
    )
    scope, err = resolve_reclamation_scope_from_run(run_id)
    assert scope is None
    assert err == "run_scope_unknown"


def test_non_string_launch_scope_fields_are_run_scope_unknown(isolated_harness_root) -> None:
    run_id = "reclaim-coercion"
    _seed_run(
        isolated_harness_root,
        run_id=run_id,
        launch={"dossier_id": 123, "transcription_id": "tx-1", "workspace_id": "ws-1"},
    )
    scope, err = resolve_reclamation_scope_from_run(run_id)
    assert scope is None
    assert err == "run_scope_unknown"
