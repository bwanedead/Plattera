"""Deterministic tests for transcript-edit workspace persistence (artifacts/transcript_edit/)."""

from __future__ import annotations

import json
from pathlib import Path

import config.paths as paths_mod
from domains.mapping.transcript_edit.runtime_adapter import composition as runtime_composition
from harness.execution.contracts import (
    ExecutionSessionStartRequest,
    ExecutionState,
    ExecutionStepRequest,
)
from harness.execution.executor import ExecutionExecutor
from harness.execution.session import ExecutionSessionManager
from tooling.mapping.transcript_edit import (
    build_transcript_edit_startup_inventory,
    copy_forward_save,
    hydrate_transcript_edit_working_draft,
    publish_transcript_edit_output,
    save_transcript_edit,
)
from tooling.mapping.transcript_edit.paths import (
    transcript_edit_latest_pointer_path,
    transcript_edit_manifest_path,
    transcript_edit_output_path,
    transcript_edit_revision_path,
    transcript_edit_workspace_root,
)


def _dossiers_root(tmp_path: Path) -> Path:
    root = tmp_path / "dossiers_data"
    root.mkdir(parents=True)
    return root


def _minimal_run_layout(root: Path, dossier_id: str, transcription_id: str) -> Path:
    run = root / "views" / "transcriptions" / dossier_id / transcription_id
    raw = run / "raw"
    raw.mkdir(parents=True)
    t0_path = raw / "peer_a.json"
    t0_path.write_text(
        json.dumps({"sections": [{"body": "immutable t0"}]}),
        encoding="utf-8",
    )
    (run / "run.json").write_text(
        json.dumps({"completed_drafts": ["peer_a"]}),
        encoding="utf-8",
    )
    return t0_path


def _valid_handoff_payload(**overrides) -> dict:
    payload = {
        "source_transcript_verbatim": "source text",
        "normalized_or_mapping_transcript": "mapping text",
        "issues": [{"id": "issue-1", "status": "closed"}],
        "parcel_metadata": {"parcel_count": 1, "forwardable_scope": "visible_source"},
        "hitl_decisions": [{"prompt_id": "hitl-1", "choice": "accepted"}],
        "evidence_refs": ["image:assoc:t1:original"],
    }
    payload.update(overrides)
    return payload


def test_save_returns_top_level_artifact_refs_for_harness_latest_refs(tmp_path, monkeypatch):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    d, tx, ws = "d1", "t1", "ws-refs"
    _minimal_run_layout(root, d, tx)
    out = save_transcript_edit(dossier_id=d, transcription_id=tx, run_id=ws, transcript_text="x")
    assert out["artifact_refs"] == ("transcript_edit:working:rev:0001", "transcript_edit:working")


def test_save_first_revision_writes_rev_latest_manifest(tmp_path, monkeypatch):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    d, tx, ws = "d1", "t1", "run-ws-1"
    _minimal_run_layout(root, d, tx)

    out = save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        run_id=ws,
        transcript_text="first body",
    )
    assert out["executed"] is True
    assert out["outputs"]["working_draft_ref"] == "transcript_edit:working:rev:0001"
    assert out["outputs"]["revision"] == 1

    rev_path = transcript_edit_revision_path(d, tx, ws, "0001")
    assert rev_path.is_file()
    rev = json.loads(rev_path.read_text(encoding="utf-8"))
    assert rev["payload"]["transcript"] == "first body"
    assert rev["tool"] == "save_transcript_edit"

    latest = json.loads(transcript_edit_latest_pointer_path(d, tx, ws).read_text(encoding="utf-8"))
    assert latest["ref_id"] == "transcript_edit:working:rev:0001"
    assert latest["revision"] == 1

    man = json.loads(transcript_edit_manifest_path(d, tx, ws).read_text(encoding="utf-8"))
    assert man["latest_revision"] == 1
    assert man["revision_count"] == 1


def test_second_revision_updates_latest_and_manifest(tmp_path, monkeypatch):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    d, tx, ws = "d1", "t1", "ws-2"
    _minimal_run_layout(root, d, tx)

    save_transcript_edit(dossier_id=d, transcription_id=tx, workspace_id=ws, transcript_text="one")
    out2 = save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        draft_payload={"sections": [{"body": "two"}]},
        evidence_refs=["image:assoc:t1:original"],
        rationale="fix spacing",
    )
    assert out2["executed"] is True
    assert out2["outputs"]["revision"] == 2
    assert out2["outputs"]["working_draft_ref"] == "transcript_edit:working:rev:0002"

    latest = json.loads(transcript_edit_latest_pointer_path(d, tx, ws).read_text(encoding="utf-8"))
    assert latest["revision"] == 2
    assert latest["ref_id"] == "transcript_edit:working:rev:0002"

    man = json.loads(transcript_edit_manifest_path(d, tx, ws).read_text(encoding="utf-8"))
    assert man["latest_revision"] == 2
    assert man["revision_count"] == 2

    rev2 = json.loads(transcript_edit_revision_path(d, tx, ws, "0002").read_text(encoding="utf-8"))
    assert rev2["evidence_refs"] == ["image:assoc:t1:original"]
    assert rev2["rationale"] == "fix spacing"


def test_startup_inventory_surfaces_working_and_output_refs(tmp_path, monkeypatch):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    d, tx, ws = "d1", "t1", "ws-3"
    _minimal_run_layout(root, d, tx)

    s1 = save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        run_id=ws,
        draft_payload=_valid_handoff_payload(source_transcript_verbatim="alpha"),
    )
    ref1 = s1["outputs"]["working_draft_ref"]
    inv_mid = build_transcript_edit_startup_inventory(dossier_id=d, transcription_id=tx, run_id=ws)
    assert inv_mid.transcript_edit_drafts.working_draft_exists is True
    assert inv_mid.transcript_edit_drafts.working_draft_ref == "transcript_edit:working"
    assert inv_mid.transcript_edit_drafts.working_latest_revision == 1
    assert inv_mid.transcript_edit_drafts.output_draft_exists is False

    pub = publish_transcript_edit_output(
        dossier_id=d,
        transcription_id=tx,
        run_id=ws,
        source_revision_ref=ref1,
    )
    assert pub["executed"] is True
    inv_after = build_transcript_edit_startup_inventory(dossier_id=d, transcription_id=tx, run_id=ws)
    assert inv_after.transcript_edit_drafts.output_draft_exists is True
    assert inv_after.transcript_edit_drafts.output_draft_ref == "transcript_edit:output"
    assert inv_after.transcript_edit_drafts.output_published_at


def test_hydrate_latest_and_specific_revision(tmp_path, monkeypatch):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    d, tx, ws = "d1", "t1", "ws-4"
    _minimal_run_layout(root, d, tx)
    save_transcript_edit(dossier_id=d, transcription_id=tx, run_id=ws, transcript_text="v1")
    save_transcript_edit(dossier_id=d, transcription_id=tx, run_id=ws, transcript_text="v2-final")

    h_latest = hydrate_transcript_edit_working_draft(
        dossier_id=d,
        transcription_id=tx,
        ref_id="transcript_edit:working",
        run_id=ws,
    )
    assert h_latest["status"] == "ok"
    assert h_latest["payload"]["payload"]["transcript"] == "v2-final"

    h_rev1 = hydrate_transcript_edit_working_draft(
        dossier_id=d,
        transcription_id=tx,
        ref_id="transcript_edit:working:rev:0001",
        run_id=ws,
    )
    assert h_rev1["status"] == "ok"
    assert h_rev1["payload"]["payload"]["transcript"] == "v1"


def test_hydrate_output_after_publish(tmp_path, monkeypatch):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    d, tx, ws = "d1", "t1", "ws-5"
    _minimal_run_layout(root, d, tx)
    s = save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        run_id=ws,
        draft_payload=_valid_handoff_payload(source_transcript_verbatim="to-publish"),
    )
    publish_transcript_edit_output(
        dossier_id=d,
        transcription_id=tx,
        run_id=ws,
        source_revision_ref=s["outputs"]["working_draft_ref"],
    )
    ho = hydrate_transcript_edit_working_draft(
        dossier_id=d,
        transcription_id=tx,
        ref_id="transcript_edit:output",
        run_id=ws,
    )
    assert ho["status"] == "ok"
    assert ho["payload"]["tool"] == "publish_transcript_edit_output"
    assert ho["payload"]["revision_snapshot"]["payload"]["source_transcript_verbatim"] == "to-publish"
    assert ho["payload"]["handoff_metadata"]["payload_path"] == "revision_snapshot.payload"
    assert ho["payload"]["handoff_metadata"]["parcel_metadata"]["parcel_count"] == 1
    assert ho["payload"]["handoff_metadata"]["evidence_refs"] == ["image:assoc:t1:original"]


def test_invalid_publish_ref_and_missing_revision(tmp_path, monkeypatch):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    d, tx, ws = "d1", "t1", "ws-6"
    _minimal_run_layout(root, d, tx)

    bad = publish_transcript_edit_output(
        dossier_id=d,
        transcription_id=tx,
        run_id=ws,
        source_revision_ref="transcript_edit:working",
    )
    assert bad["executed"] is False
    assert bad["refusal"]["reason_code"] == "invalid_source_revision_ref"

    missing = publish_transcript_edit_output(
        dossier_id=d,
        transcription_id=tx,
        run_id=ws,
        source_revision_ref="transcript_edit:working:rev:0099",
    )
    assert missing["executed"] is False
    assert missing["refusal"]["reason_code"] == "source_revision_not_found"


def test_publish_refuses_unstructured_working_revision_for_handoff(tmp_path, monkeypatch):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    d, tx, ws = "d1", "t1", "ws-publish-shape"
    _minimal_run_layout(root, d, tx)

    saved = save_transcript_edit(dossier_id=d, transcription_id=tx, run_id=ws, transcript_text="plain")
    result = publish_transcript_edit_output(
        dossier_id=d,
        transcription_id=tx,
        run_id=ws,
        source_revision_ref=saved["outputs"]["working_draft_ref"],
    )

    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == "publish_handoff_payload_incomplete"
    assert result["refusal"]["retryable"] is True
    error_paths = {row["path"] for row in result["outputs"]["handoff_payload_errors"]}
    assert "payload.source_transcript_verbatim" in error_paths
    assert "payload.parcel_metadata" in error_paths


def test_publish_accepts_empty_optional_metadata_lanes_with_none_reasons(tmp_path, monkeypatch):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    d, tx, ws = "d1", "t1", "ws-publish-none-reasons"
    _minimal_run_layout(root, d, tx)
    payload = _valid_handoff_payload(
        issues=[],
        hitl_decisions=[],
        evidence_refs=[],
        issues_none_reason="No unresolved issues remain.",
        hitl_decisions_none_reason="No HITL was needed.",
        evidence_refs_none_reason="No separate evidence refs were produced.",
    )

    saved = save_transcript_edit(dossier_id=d, transcription_id=tx, run_id=ws, draft_payload=payload)
    result = publish_transcript_edit_output(
        dossier_id=d,
        transcription_id=tx,
        run_id=ws,
        source_revision_ref=saved["outputs"]["working_draft_ref"],
    )

    assert result["executed"] is True
    output_doc = json.loads(transcript_edit_output_path(d, tx, ws).read_text(encoding="utf-8"))
    assert output_doc["handoff_metadata"]["none_reasons"] == {
        "issues": "No unresolved issues remain.",
        "hitl_decisions": "No HITL was needed.",
        "evidence_refs": "No separate evidence refs were produced.",
    }


def test_publish_refuses_empty_optional_metadata_lanes_without_none_reasons(tmp_path, monkeypatch):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    d, tx, ws = "d1", "t1", "ws-publish-empty-lane"
    _minimal_run_layout(root, d, tx)
    payload = _valid_handoff_payload(hitl_decisions=[])

    saved = save_transcript_edit(dossier_id=d, transcription_id=tx, run_id=ws, draft_payload=payload)
    result = publish_transcript_edit_output(
        dossier_id=d,
        transcription_id=tx,
        run_id=ws,
        source_revision_ref=saved["outputs"]["working_draft_ref"],
    )

    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == "publish_handoff_payload_incomplete"
    assert any(
        row["path"] == "payload.hitl_decisions"
        and row["code"] == "empty_handoff_lane_missing_none_reason"
        for row in result["outputs"]["handoff_payload_errors"]
    )


def test_invalid_path_segment_refuses_save(tmp_path, monkeypatch):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    out = save_transcript_edit(
        dossier_id="d1/../evil",
        transcription_id="t1",
        run_id="ws",
        transcript_text="x",
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "invalid_scope_path"


def test_save_without_workspace_key_refusal():
    out = save_transcript_edit(
        dossier_id="d",
        transcription_id="t",
        transcript_text="x",
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "workspace_key_required"


def test_t0_raw_peer_unchanged_after_save_and_publish(tmp_path, monkeypatch):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    d, tx, ws = "d1", "t1", "ws-7"
    t0_path = _minimal_run_layout(root, d, tx)
    before = t0_path.read_bytes()

    s = save_transcript_edit(dossier_id=d, transcription_id=tx, run_id=ws, draft_payload=_valid_handoff_payload())
    publish_transcript_edit_output(
        dossier_id=d,
        transcription_id=tx,
        run_id=ws,
        source_revision_ref=s["outputs"]["working_draft_ref"],
    )
    assert t0_path.read_bytes() == before


def test_runtime_adapter_executor_runs_save_and_publish(tmp_path, monkeypatch):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    d, tx, ws = "d1", "t1", "ws-ex"
    _minimal_run_layout(root, d, tx)

    # Scope is closed over at binding creation time — not passed per-request.
    bindings = runtime_composition.build_transcript_edit_tool_bindings(
        dossier_id=d,
        transcription_id=tx,
        workspace_key=ws,
    )
    by_id = {b.tool_id: b for b in bindings}
    ex = ExecutionExecutor()
    for b in bindings:
        ex.register(b.tool_id, b.handler)

    r_save = ex.execute(
        ExecutionStepRequest(
            session_id="s1",
            action_id="save_workspace_artifact",
            inputs={"draft_payload": _valid_handoff_payload(source_transcript_verbatim="via executor")},
        )
    )
    assert r_save.executed is True
    assert r_save.outputs["working_draft_ref"] == "transcript_edit:working:rev:0001"
    assert r_save.artifact_refs == (
        "transcript_edit:working:rev:0001",
        "transcript_edit:working",
    )

    r_pub = ex.execute(
        ExecutionStepRequest(
            session_id="s1",
            action_id="publish_workspace_artifact",
            inputs={"source_revision_ref": "transcript_edit:working:rev:0001"},
        )
    )
    assert r_pub.executed is True
    assert r_pub.outputs["output_ref"] == "transcript_edit:output"
    assert r_pub.artifact_refs == (
        "transcript_edit:output",
        "transcript_edit:working:rev:0001",
    )
    assert by_id["save_workspace_artifact"].tool_id == "save_workspace_artifact"

    assert transcript_edit_output_path(d, tx, ws).is_file()


def test_hydrate_invalid_ref_shape(tmp_path, monkeypatch):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    d, tx, ws = "d1", "t1", "ws-bad-ref"
    _minimal_run_layout(root, d, tx)
    h = hydrate_transcript_edit_working_draft(
        dossier_id=d,
        transcription_id=tx,
        ref_id="transcript_edit:working:rev:abc",
        run_id=ws,
    )
    assert h["status"] == "error"
    assert h.get("code") == "invalid_ref"


def test_execution_session_merges_save_artifact_refs_into_latest_refs(tmp_path, monkeypatch):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    d, tx, ws = "d1", "t1", "sess-ws"
    _minimal_run_layout(root, d, tx)

    bindings = runtime_composition.build_transcript_edit_tool_bindings(
        dossier_id=d,
        transcription_id=tx,
        workspace_key=ws,
    )
    ex = ExecutionExecutor()
    for b in bindings:
        ex.register(b.tool_id, b.handler)
    mgr = ExecutionSessionManager(executor=ex)
    started = mgr.start_session(ExecutionSessionStartRequest(session_id="session-te", run_id="run-te"))
    step = mgr.step(
        ExecutionStepRequest(
            session_id=started.session_id,
            action_id="save_workspace_artifact",
            idempotency_key="save-1",
            inputs={"transcript_text": "session merge"},
        )
    )
    assert step.execution_state == ExecutionState.EXECUTED
    sess = mgr.sessions[started.session_id]
    lr = sess.run_artifact.latest_refs
    assert lr.get("transcript_edit:working:rev:0001") == "transcript_edit:working:rev:0001"
    assert lr.get("transcript_edit:working") == "transcript_edit:working"


def test_startup_inventory_invalid_workspace_segment(tmp_path, monkeypatch):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    d, tx = "d1", "t1"
    _minimal_run_layout(root, d, tx)
    inv = build_transcript_edit_startup_inventory(
        dossier_id=d,
        transcription_id=tx,
        run_id="bad/ws",
    )
    assert inv.transcript_edit_drafts.working_draft_exists is False
    assert any(m.code == "transcript_edit_scope_path_invalid" for m in inv.missing_resources)


def test_workspace_explicit_over_run_id(tmp_path, monkeypatch):
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    d, tx = "d1", "t1"
    _minimal_run_layout(root, d, tx)
    save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        run_id="ignored",
        workspace_id="real-ws",
        transcript_text="w",
    )
    root_ws = transcript_edit_workspace_root(d, tx, "real-ws")
    assert (root_ws / "working" / "rev_0001.json").is_file()
    assert not (transcript_edit_workspace_root(d, tx, "ignored") / "working").exists()


# ---------------------------------------------------------------------------
# copy_forward_save
# ---------------------------------------------------------------------------


def _base_draft_payload() -> dict:
    return {
        "source_transcript_verbatim": {"text": "long verbatim text " * 200},
        "normalized_or_mapping_transcript": {"text": "long normalized text " * 200},
        "issues": [],
        "parcel_metadata": {},
        "evidence_refs": [],
    }


def test_copy_forward_save_copies_text_lanes_and_sets_metadata(tmp_path, monkeypatch):
    """Copy two long text fields from base; set metadata fields; new revision is saved correctly."""
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    d, tx, ws = "d1", "t1", "ws-cfs-1"
    _minimal_run_layout(root, d, tx)

    base = save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        run_id=ws,
        draft_payload=_base_draft_payload(),
        rationale="initial",
    )
    assert base["executed"] is True
    base_ref = base["outputs"]["working_draft_ref"]

    new_issues = [{"id": "i1", "description": "Bearing updated."}]
    out = copy_forward_save(
        dossier_id=d,
        transcription_id=tx,
        run_id=ws,
        base_ref=base_ref,
        copy_forward_paths=[
            "payload.source_transcript_verbatim",
            "payload.normalized_or_mapping_transcript",
        ],
        set_paths={
            "payload.issues": new_issues,
            "payload.parcel_metadata": {"parcel_count": 1},
            "payload.evidence_refs": ["image:derived:tx:crop_001"],
        },
        rationale="Updated issues after zoom; verbatim unchanged.",
    )
    assert out["executed"] is True
    assert out["outputs"]["revision"] == 2
    assert out["outputs"]["working_draft_ref"] == "transcript_edit:working:rev:0002"

    rev2 = json.loads(
        transcript_edit_revision_path(d, tx, ws, "0002").read_text(encoding="utf-8")
    )
    payload = rev2["payload"]
    assert payload["source_transcript_verbatim"] == _base_draft_payload()["source_transcript_verbatim"]
    assert payload["normalized_or_mapping_transcript"] == _base_draft_payload()["normalized_or_mapping_transcript"]
    assert payload["issues"] == new_issues
    assert payload["parcel_metadata"] == {"parcel_count": 1}
    assert payload["evidence_refs"] == ["image:derived:tx:crop_001"]
    assert rev2["base_revision_ref"] == base_ref


def test_copy_forward_save_missing_path_returns_repair_error(tmp_path, monkeypatch):
    """Requesting a path not present in the base artifact returns missing_copy_paths refusal."""
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    d, tx, ws = "d1", "t1", "ws-cfs-2"
    _minimal_run_layout(root, d, tx)

    base = save_transcript_edit(
        dossier_id=d,
        transcription_id=tx,
        run_id=ws,
        draft_payload={"source_transcript_verbatim": {"text": "v1"}},
    )
    base_ref = base["outputs"]["working_draft_ref"]

    out = copy_forward_save(
        dossier_id=d,
        transcription_id=tx,
        run_id=ws,
        base_ref=base_ref,
        copy_forward_paths=["payload.does_not_exist"],
        set_paths={},
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "missing_copy_paths"
    assert "payload.does_not_exist" in out["outputs"]["missing_copy_paths"]
    assert "repair_hint" in out["outputs"]


def test_copy_forward_save_invalid_path_syntax_no_payload_prefix(tmp_path, monkeypatch):
    """Path without 'payload.' prefix returns invalid_path_syntax with repair hint."""
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    d, tx, ws = "d1", "t1", "ws-cfs-3"
    _minimal_run_layout(root, d, tx)

    base = save_transcript_edit(
        dossier_id=d, transcription_id=tx, run_id=ws, draft_payload={"x": 1}
    )
    base_ref = base["outputs"]["working_draft_ref"]

    out = copy_forward_save(
        dossier_id=d,
        transcription_id=tx,
        run_id=ws,
        base_ref=base_ref,
        copy_forward_paths=["source_transcript_verbatim"],
        set_paths={},
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "invalid_path_syntax"
    assert "repair_hint" in out["outputs"]
    assert out["outputs"]["invalid_path"] == "source_transcript_verbatim"


def test_copy_forward_save_overlapping_paths_rejected(tmp_path, monkeypatch):
    """Same path in both copy_forward_paths and set_paths is rejected with overlapping_paths."""
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    d, tx, ws = "d1", "t1", "ws-cfs-4"
    _minimal_run_layout(root, d, tx)

    base = save_transcript_edit(
        dossier_id=d, transcription_id=tx, run_id=ws, draft_payload={"issues": []}
    )
    base_ref = base["outputs"]["working_draft_ref"]

    out = copy_forward_save(
        dossier_id=d,
        transcription_id=tx,
        run_id=ws,
        base_ref=base_ref,
        copy_forward_paths=["payload.issues"],
        set_paths={"payload.issues": [{"id": "new"}]},
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "overlapping_paths"
    assert "payload.issues" in out["outputs"]["overlapping_paths"]


def test_copy_forward_save_invalid_base_ref_rejected(tmp_path, monkeypatch):
    """A base_ref that doesn't match the NNNN pattern returns invalid_base_ref."""
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    d, tx, ws = "d1", "t1", "ws-cfs-5"
    _minimal_run_layout(root, d, tx)

    out = copy_forward_save(
        dossier_id=d,
        transcription_id=tx,
        run_id=ws,
        base_ref="transcript_edit:working",
        copy_forward_paths=["payload.x"],
        set_paths={},
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "invalid_base_ref"
    assert "repair_hint" in out["outputs"]


def test_copy_forward_save_via_executor_produces_new_revision(tmp_path, monkeypatch):
    """copy_forward_save_workspace_artifact tool binding works end-to-end via executor."""
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    d, tx, ws = "d1", "t1", "ws-cfs-ex"
    _minimal_run_layout(root, d, tx)

    bindings = runtime_composition.build_transcript_edit_tool_bindings(
        dossier_id=d, transcription_id=tx, workspace_key=ws
    )
    ex = ExecutionExecutor()
    for b in bindings:
        ex.register(b.tool_id, b.handler)

    r_save = ex.execute(
        ExecutionStepRequest(
            session_id="s1",
            action_id="save_workspace_artifact",
            inputs={"draft_payload": _base_draft_payload()},
        )
    )
    assert r_save.executed is True
    base_ref = r_save.outputs["working_draft_ref"]

    r_copy = ex.execute(
        ExecutionStepRequest(
            session_id="s1",
            action_id="copy_forward_save_workspace_artifact",
            inputs={
                "base_ref": base_ref,
                "copy_forward_paths": [
                    "payload.source_transcript_verbatim",
                    "payload.normalized_or_mapping_transcript",
                ],
                "set_paths": {"payload.issues": [{"id": "i1"}]},
                "rationale": "evidence refresh",
            },
        )
    )
    assert r_copy.executed is True
    assert r_copy.outputs["revision"] == 2
    assert r_copy.artifact_refs == (
        "transcript_edit:working:rev:0002",
        "transcript_edit:working",
    )

    rev2 = json.loads(
        transcript_edit_revision_path(d, tx, ws, "0002").read_text(encoding="utf-8")
    )
    assert rev2["payload"]["source_transcript_verbatim"] == _base_draft_payload()["source_transcript_verbatim"]
    assert rev2["payload"]["issues"] == [{"id": "i1"}]


def test_copy_forward_save_ancestor_overlap_copy_parent_set_child_rejected(tmp_path, monkeypatch):
    """Copying payload.parcel_metadata and setting payload.parcel_metadata.forwardability is rejected."""
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    d, tx, ws = "d1", "t1", "ws-cfs-anc1"
    _minimal_run_layout(root, d, tx)

    base = save_transcript_edit(
        dossier_id=d, transcription_id=tx, run_id=ws,
        draft_payload={"parcel_metadata": {"forwardability": "blocked"}},
    )
    base_ref = base["outputs"]["working_draft_ref"]

    out = copy_forward_save(
        dossier_id=d,
        transcription_id=tx,
        run_id=ws,
        base_ref=base_ref,
        copy_forward_paths=["payload.parcel_metadata"],
        set_paths={"payload.parcel_metadata.forwardability": "ready"},
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "overlapping_paths"
    assert "payload.parcel_metadata" in out["outputs"]["overlapping_paths"]
    assert "payload.parcel_metadata.forwardability" in out["outputs"]["overlapping_paths"]


def test_copy_forward_save_ancestor_overlap_copy_child_set_parent_rejected(tmp_path, monkeypatch):
    """Copying payload.parcel_metadata.forwardability and setting payload.parcel_metadata is rejected."""
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    d, tx, ws = "d1", "t1", "ws-cfs-anc2"
    _minimal_run_layout(root, d, tx)

    base = save_transcript_edit(
        dossier_id=d, transcription_id=tx, run_id=ws,
        draft_payload={"parcel_metadata": {"forwardability": "blocked"}},
    )
    base_ref = base["outputs"]["working_draft_ref"]

    out = copy_forward_save(
        dossier_id=d,
        transcription_id=tx,
        run_id=ws,
        base_ref=base_ref,
        copy_forward_paths=["payload.parcel_metadata.forwardability"],
        set_paths={"payload.parcel_metadata": {"forwardability": "ready"}},
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "overlapping_paths"
    assert "payload.parcel_metadata" in out["outputs"]["overlapping_paths"]
    assert "payload.parcel_metadata.forwardability" in out["outputs"]["overlapping_paths"]


def test_copy_forward_save_disjoint_paths_accepted(tmp_path, monkeypatch):
    """Copying payload.source_transcript_verbatim and setting payload.issues is accepted (no overlap)."""
    root = _dossiers_root(tmp_path)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    d, tx, ws = "d1", "t1", "ws-cfs-dis"
    _minimal_run_layout(root, d, tx)

    base = save_transcript_edit(
        dossier_id=d, transcription_id=tx, run_id=ws,
        draft_payload={"source_transcript_verbatim": {"text": "verbatim"}, "issues": []},
    )
    base_ref = base["outputs"]["working_draft_ref"]

    out = copy_forward_save(
        dossier_id=d,
        transcription_id=tx,
        run_id=ws,
        base_ref=base_ref,
        copy_forward_paths=["payload.source_transcript_verbatim"],
        set_paths={"payload.issues": [{"id": "i1"}]},
    )
    assert out["executed"] is True
    assert out["outputs"]["revision"] == 2
