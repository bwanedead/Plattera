"""MAPDEP-BR-038: apply_transcript_edits nesting refusals and corrected writes."""

from __future__ import annotations

import json

import config.paths as paths_mod
import tooling.mapping.transcript_edit.paths as te_paths

from domains.mapping.transcript_edit.payloads.startup_inventory import (
    T0DraftDescriptor,
    TranscriptEditDraftInventory,
    TranscriptEditScope,
    TranscriptEditStartupInventory,
)
from domains.mapping.transcript_edit.runtime_adapter.dossier_tool_bindings import (
    build_dossier_transcript_edit_tool_bindings,
)
from domains.mapping.transcript_edit.runtime_adapter.tool_refusal_boundary import (
    apply_tool_refusal_boundary,
)
from services.dossier.segment_topology import TopologyRunInput, TopologySegmentInput
from tooling.mapping.transcript_edit._apply_transcript_edits_test_helpers import (
    decision,
    root,
    save_base,
    seed_run,
)
from tooling.mapping.transcript_edit.apply_transcript_edits import apply_transcript_edits
from tooling.mapping.transcript_edit.dossier_action_result_refs import (
    project_dossier_leaf_failure,
)
from tooling.mapping.transcript_edit.dossier_artifact_refs import (
    DossierArtifactRefTarget,
    qualify_leaf_ref,
)
from tooling.mapping.transcript_edit.dossier_startup_inventory import (
    build_dossier_transcript_edit_startup_inventory_from_segments,
)
from tooling.mapping.transcript_edit.dossier_workspace_actions import (
    make_dossier_apply_transcript_edits_handler,
    make_dossier_save_workspace_artifact_handler,
)
from tooling.mapping.transcript_edit.paths import (
    transcript_edit_latest_pointer_path,
    transcript_edit_manifest_path,
    transcript_edit_revision_path,
)

_NESTING_HINT = (
    "Move lane, expected_text, and replacement_text into a decision's nonempty "
    "edits[] rows. Keep determination, uncertainty reasons, verification basis, "
    "and evidence refs on the decision."
)
_SYNTH_SOURCE = "SYNTH_TOKEN_ALPHA"
_SYNTH_REPLACEMENT = "SYNTH_TOKEN_BETA"
_SYNTH_NORM = "SYNTH_NORM_ALPHA"
_SYNTH_NORM_REPL = "SYNTH_NORM_BETA"


def _seed_dossier_apply_workspace(
    tmp_path,
    monkeypatch,
    *,
    ws: str,
    source: str = _SYNTH_SOURCE,
):
    """Synthetic-text dossier apply workspace (BR-038; not the historical Range fixture)."""
    dossiers = tmp_path / "dossiers_data"
    dossiers.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: dossiers)
    monkeypatch.setattr(te_paths, "dossiers_root", lambda: dossiers)
    d = "d1"
    run = dossiers / "views" / "transcriptions" / d / "tx_a"
    raw = run / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "tx_a_draft_1.json").write_text(
        json.dumps({"sections": [{"body": "t0 for tx_a"}]}),
        encoding="utf-8",
    )
    (run / "run.json").write_text(
        json.dumps({"completed_drafts": ["tx_a_draft_1"]}),
        encoding="utf-8",
    )

    def leaf_builder(**kwargs):
        tid = kwargs["transcription_id"]
        return TranscriptEditStartupInventory(
            scope=TranscriptEditScope(
                dossier_id=kwargs["dossier_id"],
                transcription_id=tid,
                segment_id=kwargs.get("segment_id"),
                workspace_id=ws,
            ),
            t0_drafts=(
                T0DraftDescriptor(
                    ref_id="t0:raw:draft_1",
                    variant_label="draft 1",
                    source_file_stem=f"{tid}_draft_1",
                ),
            ),
            transcript_edit_drafts=TranscriptEditDraftInventory(working_draft_exists=False),
        )

    bundle = build_dossier_transcript_edit_startup_inventory_from_segments(
        dossier_id=d,
        workspace_id=ws,
        segments=(TopologySegmentInput("seg_a", 0, (TopologyRunInput("tx_a", 0),)),),
        association_positions={"tx_a": 1},
        leaf_inventory_builder=leaf_builder,
    )
    save = make_dossier_save_workspace_artifact_handler(
        dossier_id=d, ref_index=bundle.ref_index, workspace_key=ws
    )
    target = qualify_leaf_ref(
        segment_id="seg_a", transcription_id="tx_a", leaf_ref="t0:raw:draft_1"
    )
    seeded = save(
        {
            "target_ref": target,
            "draft_payload": {
                "source_transcript_verbatim": source,
                "issues": [],
            },
        }
    )
    assert seeded["executed"] is True
    base_ref = seeded["outputs"]["working_draft_ref"]
    apply = make_dossier_apply_transcript_edits_handler(
        dossier_id=d, ref_index=bundle.ref_index, workspace_key=ws
    )
    return d, ws, base_ref, apply, bundle


def _nesting_decision(*, with_lane: bool) -> dict:
    row: dict = {
        "decision_id": "synth-decision-1",
        "determination": "provisional",
        "uncertainty_reasons": ["source_ambiguous"],
        "verification_basis": "synthetic observation basis",
        "evidence_refs": [],
        "expected_text": _SYNTH_SOURCE,
        "replacement_text": _SYNTH_REPLACEMENT,
    }
    if with_lane:
        row["lane"] = "source_transcript_verbatim"
    return row


def _assert_nesting_refusal(out: dict) -> None:
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "unknown_decision_fields"
    assert out["refusal"].get("retryable") is False
    error = out["outputs"]["error"]
    assert isinstance(error, dict)
    assert error["repair_hint"] == _NESTING_HINT
    boundary = apply_tool_refusal_boundary("apply_transcript_edits", out)
    assert boundary["refusal"]["retryable"] is True
    assert boundary["outputs"]["error"]["repair_hint"] == _NESTING_HINT
    blob = json.dumps(boundary)
    assert _SYNTH_SOURCE not in blob
    assert _SYNTH_REPLACEMENT not in blob


def test_br038_a_dossier_text_fields_on_decision_refuse_with_nesting_hint(
    tmp_path, monkeypatch
) -> None:
    _d, _ws, base_ref, apply, _bundle = _seed_dossier_apply_workspace(
        tmp_path, monkeypatch, ws="ws-br038-a"
    )
    out = apply(
        {
            "base_revision_ref": base_ref,
            "decisions": [_nesting_decision(with_lane=False)],
        }
    )
    _assert_nesting_refusal(out)


def test_br038_b_dossier_lane_plus_text_on_decision_refuse_with_nesting_hint(
    tmp_path, monkeypatch
) -> None:
    _d, _ws, base_ref, apply, _bundle = _seed_dossier_apply_workspace(
        tmp_path, monkeypatch, ws="ws-br038-b"
    )
    out = apply(
        {
            "base_revision_ref": base_ref,
            "decisions": [_nesting_decision(with_lane=True)],
        }
    )
    _assert_nesting_refusal(out)


def test_br038_c_repeated_malformed_does_not_mutate_working_files(
    tmp_path, monkeypatch
) -> None:
    d, ws, base_ref, apply, _bundle = _seed_dossier_apply_workspace(
        tmp_path, monkeypatch, ws="ws-br038-c"
    )
    latest = transcript_edit_latest_pointer_path(d, "tx_a", ws)
    manifest = transcript_edit_manifest_path(d, "tx_a", ws)
    rev = transcript_edit_revision_path(d, "tx_a", ws, "0001")
    before = {
        "latest": latest.read_bytes(),
        "manifest": manifest.read_bytes(),
        "rev": rev.read_bytes(),
    }
    for _ in range(3):
        out = apply(
            {
                "base_revision_ref": base_ref,
                "decisions": [_nesting_decision(with_lane=True)],
            }
        )
        assert out["executed"] is False
        assert out["refusal"]["reason_code"] == "unknown_decision_fields"
    assert latest.read_bytes() == before["latest"]
    assert manifest.read_bytes() == before["manifest"]
    assert rev.read_bytes() == before["rev"]
    assert not transcript_edit_revision_path(d, "tx_a", ws, "0002").exists()


def test_br038_d_corrected_nested_edits_advances_rev0001_to_rev0002(
    tmp_path, monkeypatch
) -> None:
    d, ws, base_ref, apply, _bundle = _seed_dossier_apply_workspace(
        tmp_path, monkeypatch, ws="ws-br038-d"
    )
    out = apply(
        {
            "base_revision_ref": base_ref,
            "decisions": [
                {
                    "decision_id": "synth-fix-1",
                    "determination": "provisional",
                    "uncertainty_reasons": ["source_ambiguous"],
                    "verification_basis": "synthetic corrected nesting",
                    "evidence_refs": [],
                    "edits": [
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": _SYNTH_SOURCE,
                            "replacement_text": _SYNTH_REPLACEMENT,
                        }
                    ],
                }
            ],
        }
    )
    assert out["executed"] is True, out
    working = out["outputs"]["working_draft_ref"]
    assert working.endswith("transcript_edit:working:rev:0002")
    assert "dossier_segment:" in working
    assert transcript_edit_revision_path(d, "tx_a", ws, "0002").is_file()


def test_br038_e_both_lanes_under_one_decision_id(tmp_path, monkeypatch) -> None:
    dossiers = root(tmp_path, monkeypatch)
    monkeypatch.setattr(te_paths, "dossiers_root", lambda: dossiers)
    d, tx, ws = "d1", "t1", "ws-br038-e"
    seed_run(dossiers, d, tx)
    save_base(
        d=d,
        tx=tx,
        ws=ws,
        source=_SYNTH_SOURCE,
        normalized=_SYNTH_NORM,
    )
    out = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [
                {
                    "decision_id": "synth-dual-lane",
                    "determination": "provisional",
                    "uncertainty_reasons": ["source_ambiguous"],
                    "verification_basis": "same determination covers both lanes",
                    "evidence_refs": [],
                    "edits": [
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": _SYNTH_SOURCE,
                            "replacement_text": _SYNTH_REPLACEMENT,
                        },
                        {
                            "lane": "normalized_or_mapping_transcript",
                            "expected_text": _SYNTH_NORM,
                            "replacement_text": _SYNTH_NORM_REPL,
                        },
                    ],
                }
            ],
        },
    )
    assert out["executed"] is True, out
    assert out["outputs"]["working_draft_ref"] == "transcript_edit:working:rev:0002"
    rev = json.loads(
        transcript_edit_revision_path(d, tx, ws, "0002").read_text(encoding="utf-8")
    )
    assert rev["payload"]["source_transcript_verbatim"] == _SYNTH_REPLACEMENT
    assert rev["payload"]["normalized_or_mapping_transcript"] == _SYNTH_NORM_REPL
    decisions_doc = rev["payload"]["transcript_edit_decisions"]
    decisions = decisions_doc["decisions"] if isinstance(decisions_doc, dict) else decisions_doc
    assert len(decisions) == 1
    assert decisions[0]["decision_id"] == "synth-dual-lane"
    assert len(decisions[0]["edits"]) == 2


def test_br038_f_missing_required_field_not_mislabeled_as_nesting(
    tmp_path, monkeypatch
) -> None:
    _d, _ws, base_ref, apply, _bundle = _seed_dossier_apply_workspace(
        tmp_path, monkeypatch, ws="ws-br038-f"
    )
    out = apply(
        {
            "base_revision_ref": base_ref,
            "decisions": [
                {
                    "decision_id": "synth-missing-basis",
                    "determination": "provisional",
                    "uncertainty_reasons": ["source_ambiguous"],
                    "evidence_refs": [],
                    "edits": [
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": _SYNTH_SOURCE,
                            "replacement_text": "x",
                        }
                    ],
                }
            ],
        }
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "verification_basis_required"
    assert out["refusal"].get("retryable") is False
    error = out["outputs"]["error"]
    assert isinstance(error, dict)
    assert error["repair_hint"] == "Provide a nonblank verification_basis on the decision."
    assert error["repair_hint"] != _NESTING_HINT
    assert "Move lane" not in error["repair_hint"]
    boundary = apply_tool_refusal_boundary("apply_transcript_edits", out)
    assert boundary["refusal"]["retryable"] is True
    assert boundary["outputs"]["error"]["repair_hint"] == error["repair_hint"]


def test_br038_g_leaf_request_shape_still_succeeds(tmp_path, monkeypatch) -> None:
    dossiers = root(tmp_path, monkeypatch)
    monkeypatch.setattr(te_paths, "dossiers_root", lambda: dossiers)
    d, tx, ws = "d1", "t1", "ws-br038-g-leaf"
    seed_run(dossiers, d, tx)
    save_base(d=d, tx=tx, ws=ws, source=_SYNTH_SOURCE)
    leaf = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [
                decision(
                    edits=[
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": _SYNTH_SOURCE,
                            "replacement_text": _SYNTH_REPLACEMENT,
                        }
                    ]
                )
            ],
        },
    )
    assert leaf["executed"] is True, leaf


def test_br038_g_dossier_rejects_unqualified_base_revision_ref(
    tmp_path, monkeypatch
) -> None:
    _d, _ws, _base, apply, _bundle = _seed_dossier_apply_workspace(
        tmp_path, monkeypatch, ws="ws-br038-g-dos"
    )
    refused = apply(
        {
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [
                {
                    "decision_id": "synth-unqualified",
                    "determination": "provisional",
                    "uncertainty_reasons": ["source_ambiguous"],
                    "verification_basis": "ok",
                    "evidence_refs": [],
                    "edits": [
                        {
                            "lane": "source_transcript_verbatim",
                            "expected_text": _SYNTH_SOURCE,
                            "replacement_text": "x",
                        }
                    ],
                }
            ],
        }
    )
    assert refused["executed"] is False
    assert refused["refusal"]["reason_code"] in {
        "dossier_base_revision_invalid",
        "dossier_ref_required",
        "dossier_ref_invalid",
    }


def test_br038_dossier_binding_nesting_hint_and_canonical_retryable(
    tmp_path, monkeypatch
) -> None:
    """Production dossier binding: nesting hint survives; boundary owns retryable."""
    _d, _ws, base_ref, _apply, bundle = _seed_dossier_apply_workspace(
        tmp_path, monkeypatch, ws="ws-br038-bind"
    )
    bindings = build_dossier_transcript_edit_tool_bindings(bundle=bundle)
    handler = next(b.handler for b in bindings if b.tool_id == "apply_transcript_edits")
    out = handler(
        {
            "base_revision_ref": base_ref,
            "decisions": [_nesting_decision(with_lane=True)],
        }
    )
    assert out["executed"] is False
    assert out["refusal"]["reason_code"] == "unknown_decision_fields"
    assert out["refusal"]["retryable"] is True
    assert out["refusal"]["blocked_by_invariant"] is False
    assert out["outputs"]["error"]["repair_hint"] == _NESTING_HINT
    blob = json.dumps(out)
    assert _SYNTH_SOURCE not in blob
    assert _SYNTH_REPLACEMENT not in blob


def test_br038_hint_cannot_make_non_allowlisted_refusal_retryable() -> None:
    """A repair_hint must not confer retryability on a terminal reason code."""
    from tooling.mapping.transcript_edit.dossier_artifact_refs import (
        build_dossier_artifact_ref_index,
    )

    q = qualify_leaf_ref(
        segment_id="seg_a",
        transcription_id="tx_a",
        leaf_ref="transcript_edit:working:rev:0001",
    )
    index = build_dossier_artifact_ref_index(
        dossier_id="d1",
        topology_fingerprint="fp",
        entries=(
            (
                q,
                DossierArtifactRefTarget(
                    segment_id="seg_a",
                    transcription_id="tx_a",
                    leaf_ref="transcript_edit:working:rev:0001",
                ),
            ),
        ),
        run_bindings=frozenset({("seg_a", "tx_a")}),
    )
    target = DossierArtifactRefTarget(
        segment_id="seg_a",
        transcription_id="tx_a",
        leaf_ref="transcript_edit:working:rev:0001",
    )
    projected = project_dossier_leaf_failure(
        result={
            "executed": False,
            "refusal": {
                "reason_code": "storage_failure",
                "retryable": False,
                "blocked_by_invariant": True,
                "blocked_by_budget": False,
                "missing_inputs": [],
            },
            "outputs": {
                "error": {
                    "code": "storage_failure",
                    "message": "Unable to acquire working write lock.",
                    "repair_hint": "This hint must not flip retryability.",
                }
            },
        },
        ref_index=index,
        target=target,
    )
    assert projected["refusal"]["retryable"] is False
    assert projected["outputs"]["error"]["repair_hint"] == (
        "This hint must not flip retryability."
    )
    bounded = apply_tool_refusal_boundary("apply_transcript_edits", projected)
    assert bounded["refusal"]["retryable"] is False
    assert bounded["refusal"]["blocked_by_invariant"] is True
    assert bounded["outputs"]["error"]["repair_hint"] == (
        "This hint must not flip retryability."
    )


def test_br038_leaf_refuse_stays_terminal_until_boundary(tmp_path, monkeypatch) -> None:
    dossiers = root(tmp_path, monkeypatch)
    monkeypatch.setattr(te_paths, "dossiers_root", lambda: dossiers)
    d, tx, ws = "d1", "t1", "ws-br038-leaf-term"
    seed_run(dossiers, d, tx)
    save_base(d=d, tx=tx, ws=ws, source=_SYNTH_SOURCE)
    raw = apply_transcript_edits(
        dossier_id=d,
        transcription_id=tx,
        workspace_id=ws,
        request={
            "base_revision_ref": "transcript_edit:working:rev:0001",
            "decisions": [_nesting_decision(with_lane=True)],
        },
    )
    assert raw["refusal"]["reason_code"] == "unknown_decision_fields"
    assert raw["refusal"]["retryable"] is False
    assert raw["outputs"]["error"]["repair_hint"] == _NESTING_HINT
    after = apply_tool_refusal_boundary("apply_transcript_edits", raw)
    assert after["refusal"]["retryable"] is True
