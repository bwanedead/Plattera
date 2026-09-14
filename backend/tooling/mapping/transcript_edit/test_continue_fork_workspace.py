"""Offline continue-fork preserves transcript-edit workspace identity."""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import config.paths as paths_mod
import tooling.mapping.transcript_edit.paths as te_paths_mod
from PIL import Image

from harness.cli import fork_resume as cli_fork
from harness.cli import run_state as rs
from harness.cli.fork_spawn_argv import parse_embedded_launch_context
from harness.cli.launch_identity import merge_cli_launch_identity
from harness.cli.test_cli_fork_resume import _write_turn_checkpoint
from tooling.mapping.transcript_edit.artifact_hydration import make_hydrate_artifact_refs_handler
from tooling.mapping.transcript_edit.artifact_transform import make_transform_artifact_handler
from tooling.mapping.transcript_edit.draft_loading import hydrate_transcript_edit_working_draft
from tooling.mapping.transcript_edit.draft_persistence import save_transcript_edit
from tooling.mapping.transcript_edit.paths import (
    transcript_edit_latest_pointer_path,
    transcript_edit_revision_path,
    transcript_edit_workspace_root,
)
from tooling.mapping.transcript_edit.test_artifact_hydration_image import _write_association


def _seed_source_run(tmp_path: Path, *, source_id: str) -> tuple[rs.HarnessCliRunState, Path]:
    run_path = tmp_path / "cli" / source_id
    run_path.mkdir(parents=True, exist_ok=True)
    launch = {
        "run_id": source_id,
        "workspace_id": source_id,
        "dossier_id": "d-continue",
        "transcription_id": "tx-continue",
    }
    spawn_argv = [
        "python",
        "-m",
        "harness.runtime.runner.entrypoint",
        "--launch-context-json",
        json.dumps(launch, separators=(",", ":")),
    ]
    st = rs.new_run_state(
        run_id=source_id,
        pid=0,
        loop_kind="transcript_edit",
        mode="live",
        spawn_argv=spawn_argv,
        run_dir=run_path,
    )
    rs.write_state(st)
    _write_turn_checkpoint(run_path=run_path, turn=17, format="gzip")
    payload = {
        "status": "failed",
        "reason_code": "model_call_failed",
        "terminal_class": "failed",
    }
    (run_path / "result.json").write_text(json.dumps(payload), encoding="utf-8")
    (run_path / "done.json").write_text(json.dumps(payload), encoding="utf-8")
    audit = run_path / "audit" / "index.json"
    audit.parent.mkdir(parents=True, exist_ok=True)
    audit.write_text(json.dumps({"run_id": source_id, "terminal_class": "failed"}), encoding="utf-8")
    return st, run_path


def test_continue_fork_reuses_source_transcript_edit_workspace(tmp_path, monkeypatch) -> None:
    source_id = "source-te-run"
    child_id = "child-te-run"
    d, tx = "d-continue", "tx-continue"
    data_root = tmp_path / "data"
    data_root.mkdir()
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: data_root)
    monkeypatch.setattr(te_paths_mod, "dossiers_root", lambda: data_root)

    img_dir = tmp_path / "images"
    img_dir.mkdir()
    img_file = img_dir / "scan.png"
    buf = io.BytesIO()
    Image.new("RGB", (100, 80), color=(200, 200, 200)).save(buf, format="PNG")
    img_file.write_bytes(buf.getvalue())
    _write_association(data_root, d, tx, img_file)

    transform = make_transform_artifact_handler(
        dossier_id=d, transcription_id=tx, workspace_key=source_id
    )
    tr = transform(
        {
            "ref_id": f"image:assoc:{tx}:original",
            "sub_action": "zoom",
            "params": {"factor": 2.0},
        }
    )
    assert tr.get("executed") is True, tr
    derived_ref = tr["outputs"]["derived_ref_id"]

    saved = save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=source_id,
        draft_payload={"source_transcript_verbatim": "example provisional token"},
    )
    assert saved.get("executed") is True
    working_ref = saved["outputs"]["working_draft_ref"]
    assert working_ref.endswith("rev:0001")
    rev1_path = transcript_edit_revision_path(d, tx, source_id, "0001")
    rev1_before = rev1_path.read_bytes()

    source_state, source_path = _seed_source_run(tmp_path, source_id=source_id)
    source_state_bytes = (source_path / "state.json").read_bytes()
    source_audit_bytes = (source_path / "audit" / "index.json").read_bytes()
    source_ckpt = source_path / "resume_checkpoints" / "turn_0017.json.gz"
    source_ckpt_bytes = source_ckpt.read_bytes()

    monkeypatch.setattr(cli_fork, "run_dir", lambda _rid: source_path)
    monkeypatch.setattr(cli_fork, "read_state", lambda _rid: source_state)
    monkeypatch.setattr("harness.cli.fork_continue_eligibility.assess_run_quiescence", lambda _rid: None)
    scan_root = tmp_path / "cli_runs_root"
    scan_root.mkdir()
    import harness.cli.run_layout as layout_mod

    monkeypatch.setattr(layout_mod, "cli_runs_root", lambda: scan_root)

    child_path = tmp_path / "cli" / child_id

    class _Allocated:
        run_id = child_id
        run_dir = child_path
        human_timeline_path = child_path / "audit" / "human" / "timeline.md"

    with patch("harness.cli.fork_resume.allocate_automatic_run_id", return_value=_Allocated()):
        with patch("harness.cli.fork_resume.spawn_run_control_watchdog", return_value=None):
            with patch("harness.cli.fork_resume.subprocess.Popen") as popen:
                popen.return_value.pid = 99
                result = cli_fork.fork_run_from_turn(
                    run_id=source_id,
                    from_turn=17,
                    workspace_mode="continue",
                )

    assert result["status"] == "forked"
    assert result["fork_lineage"]["workspace_mode"] == "continue"
    assert result["fork_lineage"]["source_workspace_id"] == source_id
    child_state = rs.HarnessCliRunState.from_json_dict(
        json.loads((child_path / "state.json").read_text(encoding="utf-8"))
    )
    launch, parse_err = parse_embedded_launch_context(list(child_state.spawn_argv))
    assert parse_err is None
    assert launch is not None
    monkeypatch.setenv("HARNESS_CLI_RUN_ID", child_id)
    merged, err = merge_cli_launch_identity(launch)
    assert err is None
    assert merged["run_id"] == child_id
    assert merged["workspace_id"] == source_id
    assert "run_id" not in launch
    assert launch["workspace_id"] == source_id

    hydrate = make_hydrate_artifact_refs_handler(
        dossier_id=d, transcription_id=tx, workspace_key=merged["workspace_id"]
    )
    hydrated_image = hydrate({"ref_ids": [derived_ref]})
    assert hydrated_image["executed"] is True
    assert hydrated_image["outputs"]["results"][0]["kind"] == "derived_image"

    loaded = hydrate_transcript_edit_working_draft(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=merged["workspace_id"],
        ref_id=working_ref,
    )
    assert loaded.get("status") != "error"

    next_save = save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=merged["workspace_id"],
        run_id=merged["run_id"],
        draft_payload={"source_transcript_verbatim": "example provisional token revised"},
        base_revision_ref=working_ref,
    )
    assert next_save.get("executed") is True
    assert next_save["outputs"]["working_draft_ref"].endswith("rev:0002")
    pointer = json.loads(
        transcript_edit_latest_pointer_path(d, tx, source_id).read_text(encoding="utf-8")
    )
    assert str(pointer.get("relative_path", "")).endswith("rev_0002.json")
    assert not transcript_edit_workspace_root(d, tx, child_id).exists()
    assert rev1_path.read_bytes() == rev1_before
    assert (source_path / "state.json").read_bytes() == source_state_bytes
    assert (source_path / "audit" / "index.json").read_bytes() == source_audit_bytes
    assert source_ckpt.read_bytes() == source_ckpt_bytes
