"""Production-shaped integration tests for transcript-edit refusal boundary."""

from __future__ import annotations

import json
from pathlib import Path

import config.paths as paths_mod
import tooling.mapping.transcript_edit.paths as te_paths

from domains.mapping.transcript_edit.execution.tool_specs import build_transcript_edit_tool_specs
from domains.mapping.transcript_edit.payloads.startup_inventory import (
    T0DraftDescriptor,
    TranscriptEditDraftInventory,
    TranscriptEditScope,
    TranscriptEditStartupInventory,
)
from domains.mapping.transcript_edit.runtime_adapter.composition import (
    build_transcript_edit_tool_bindings,
)
from domains.mapping.transcript_edit.runtime_adapter.dossier_tool_bindings import (
    build_dossier_transcript_edit_tool_bindings,
)
from harness.execution.contracts import (
    ExecutionState,
    ExecutionStepRequest,
    ExecutionStepResult,
    SessionExecutionRecord,
)
from harness.execution.executor import ExecutionExecutor
from harness.runtime.memory.result_delivery import (
    admit_pending_result_delivery,
    project_latest_action_results,
)
from harness.runtime.orchestration.action_sequence_hooks import _finalize_single_action_turn
from harness.runtime.memory import LoopMemoryState
from harness.runtime.orchestration.action_sequence import (
    ActionPlanAction,
    action_plan_with_canonical_actions,
)
from services.dossier.segment_topology import TopologyRunInput, TopologySegmentInput
from tooling.mapping.transcript_edit.dossier_artifact_refs import qualify_leaf_ref
from tooling.mapping.transcript_edit.dossier_startup_inventory import (
    build_dossier_transcript_edit_startup_inventory_from_segments,
)


def _dossiers_root(tmp_path: Path) -> Path:
    root = tmp_path / "dossiers_data"
    root.mkdir(parents=True)
    return root


def _patch_roots(monkeypatch, root: Path) -> None:
    monkeypatch.setattr(paths_mod, "dossiers_root", lambda: root)
    monkeypatch.setattr(te_paths, "dossiers_root", lambda: root)


def _minimal_run_layout(root: Path, dossier_id: str, transcription_id: str) -> None:
    run = root / "views" / "transcriptions" / dossier_id / transcription_id
    raw = run / "raw"
    raw.mkdir(parents=True)
    (raw / f"{transcription_id}_draft_1.json").write_text(
        json.dumps({"sections": [{"body": f"t0 {transcription_id}"}]}),
        encoding="utf-8",
    )
    (run / "run.json").write_text(
        json.dumps({"completed_drafts": [f"{transcription_id}_draft_1"]}),
        encoding="utf-8",
    )


def _leaf_builder(**kwargs):
    tid = kwargs["transcription_id"]
    return TranscriptEditStartupInventory(
        scope=TranscriptEditScope(
            dossier_id=kwargs["dossier_id"],
            transcription_id=tid,
            segment_id=kwargs.get("segment_id"),
            workspace_id=kwargs.get("workspace_id"),
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


def _two_segment_bundle(tmp_path, monkeypatch, *, workspace_id: str = "ws-bind"):
    root = _dossiers_root(tmp_path)
    _patch_roots(monkeypatch, root)
    d = "d1"
    _minimal_run_layout(root, d, "tx_a")
    _minimal_run_layout(root, d, "tx_b")
    bundle = build_dossier_transcript_edit_startup_inventory_from_segments(
        dossier_id=d,
        workspace_id=workspace_id,
        segments=(
            TopologySegmentInput("seg_a", 0, (TopologyRunInput("tx_a", 0),)),
            TopologySegmentInput("seg_b", 1, (TopologyRunInput("tx_b", 0),)),
        ),
        association_positions={"tx_a": 1, "tx_b": 2},
        leaf_inventory_builder=_leaf_builder,
    )
    return root, d, workspace_id, bundle


def _binding(bindings, tool_id: str):
    return next(b for b in bindings if b.tool_id == tool_id).handler


def _executor_for_bindings(bindings) -> ExecutionExecutor:
    executor = ExecutionExecutor()
    for binding in bindings:
        executor.register(binding.tool_id, binding.handler)
    return executor


def _step_result_from_executor(
    executor: ExecutionExecutor,
    *,
    session_id: str,
    action_id: str,
    inputs: dict,
    alias: str = "a1",
) -> ExecutionStepResult:
    request = ExecutionStepRequest(
        session_id=session_id,
        action_id=action_id,
        inputs=inputs,
        idempotency_key=f"{session_id}:{alias}",
    )
    dispatch = executor.execute(request)
    record = SessionExecutionRecord(
        session_id=session_id,
        run_id="run-1",
        request=request,
        result=dispatch,
    )
    exec_state = ExecutionState.EXECUTED if dispatch.executed else ExecutionState.REFUSED
    return ExecutionStepResult(
        session_id=session_id,
        idempotency_key=request.idempotency_key,
        execution_state=exec_state,
        dashboard=None,  # type: ignore[arg-type]
        refusal=dispatch.refusal,
        record=record,
    )


def test_leaf_and_dossier_bindings_retain_same_five_action_ids(tmp_path, monkeypatch) -> None:
    _, _, _, bundle = _two_segment_bundle(tmp_path, monkeypatch)
    leaf_bindings = build_transcript_edit_tool_bindings(
        dossier_id="d-leaf",
        transcription_id="tx-leaf",
        workspace_key="ws-leaf",
    )
    dossier_bindings = build_dossier_transcript_edit_tool_bindings(bundle=bundle)

    expected = [s.tool_id for s in build_transcript_edit_tool_specs()]
    assert [b.tool_id for b in leaf_bindings] == expected
    assert [b.tool_id for b in dossier_bindings] == expected


def test_leaf_hydration_wrong_field_is_retryable_and_admitted(tmp_path, monkeypatch) -> None:
    root = _dossiers_root(tmp_path)
    _patch_roots(monkeypatch, root)
    d, tx, ws = "d-hydrate", "tx-hydrate", "ws-hydrate"
    _minimal_run_layout(root, d, tx)

    bindings = build_transcript_edit_tool_bindings(
        dossier_id=d,
        transcription_id=tx,
        workspace_key=ws,
    )
    executor = _executor_for_bindings(bindings)

    wrong = executor.execute(
        ExecutionStepRequest(
            session_id="s1",
            action_id="hydrate_artifact_refs",
            inputs={"refs": ["t0:raw:draft_1"]},
        )
    )
    assert wrong.executed is False
    assert wrong.refusal is not None
    assert wrong.refusal.reason_code == "ref_ids_required"
    assert wrong.refusal.retryable is True
    assert wrong.refusal.blocked_by_invariant is False

    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=wrong,
        source_turn_index=1,
        action_index=1,
        action_alias="hydrate",
        execution_state="retryable_error",
    )
    projection = project_latest_action_results(deliveries)
    assert projection.latest_action_results
    assert projection.latest_action_results[0]["refusal"]["reason_code"] == "ref_ids_required"
    assert projection.latest_action_results[0]["execution_state"] == "retryable_error"

    fixed = executor.execute(
        ExecutionStepRequest(
            session_id="s1",
            action_id="hydrate_artifact_refs",
            inputs={"ref_ids": ["t0:raw:draft_1"]},
        )
    )
    assert fixed.executed is True


def test_dossier_hydration_wrong_field_is_retryable_and_admitted(tmp_path, monkeypatch) -> None:
    _, _, _, bundle = _two_segment_bundle(tmp_path, monkeypatch)
    bindings = build_dossier_transcript_edit_tool_bindings(bundle=bundle)
    executor = _executor_for_bindings(bindings)

    wrong = executor.execute(
        ExecutionStepRequest(
            session_id="s1",
            action_id="hydrate_artifact_refs",
            inputs={"refs": ["dossier_segment:seg_a:run:tx_a:t0:raw:draft_1"]},
        )
    )
    assert wrong.executed is False
    assert wrong.refusal is not None
    assert wrong.refusal.reason_code == "ref_ids_invalid_type"
    assert wrong.refusal.retryable is True
    assert wrong.refusal.blocked_by_invariant is False

    deliveries: list[dict] = []
    admit_pending_result_delivery(
        deliveries,
        result=wrong,
        source_turn_index=1,
        action_index=1,
        action_alias="hydrate",
        execution_state="retryable_error",
    )
    assert project_latest_action_results(deliveries).latest_action_results

    fixed = executor.execute(
        ExecutionStepRequest(
            session_id="s1",
            action_id="hydrate_artifact_refs",
            inputs={
                "ref_ids": [
                    qualify_leaf_ref(
                        segment_id="seg_a",
                        transcription_id="tx_a",
                        leaf_ref="t0:raw:draft_1",
                    )
                ]
            },
        )
    )
    assert fixed.executed is True


def test_leaf_hydration_refusal_does_not_terminalize_turn(tmp_path, monkeypatch) -> None:
    root = _dossiers_root(tmp_path)
    _patch_roots(monkeypatch, root)
    d, tx, ws = "d-term", "tx-term", "ws-term"
    _minimal_run_layout(root, d, tx)

    bindings = build_transcript_edit_tool_bindings(
        dossier_id=d,
        transcription_id=tx,
        workspace_key=ws,
    )
    executor = _executor_for_bindings(bindings)
    step = _step_result_from_executor(
        executor,
        session_id="s1",
        action_id="hydrate_artifact_refs",
        inputs={"refs": ["t0:raw:draft_1"]},
    )

    loop_memory = LoopMemoryState()
    action_plan = action_plan_with_canonical_actions(
        actions=(
            ActionPlanAction(
                action_type="hydrate_artifact_refs",
                action_inputs={"refs": ["t0:raw:draft_1"]},
                alias="hydrate",
            ),
        )
    )
    sequence_result = {
        "items": [
            {
                "execution_state": "retryable_error",
                "error": {
                    "reason_code": step.refusal.reason_code if step.refusal else "",
                    "retryable": True,
                },
            }
        ]
    }

    outcome = _finalize_single_action_turn(
        loop_memory=loop_memory,
        action_plan=action_plan,
        actions=action_plan.actions,
        iteration=1,
        last_step=None,
        sequence_result=sequence_result,
        tracer=type("T", (), {"emit_execution_result": lambda *a, **k: None})(),
        turn_completion_observer=None,
        patch_present=False,
        run_ctx=None,
    )

    assert outcome.terminal_class is None
    assert outcome.terminal_reason_code is None


def test_incorrect_save_request_is_retryable_without_write(tmp_path, monkeypatch) -> None:
    root = _dossiers_root(tmp_path)
    _patch_roots(monkeypatch, root)
    d, tx, ws = "d-save", "tx-save", "ws-save"
    _minimal_run_layout(root, d, tx)

    bindings = build_transcript_edit_tool_bindings(
        dossier_id=d,
        transcription_id=tx,
        workspace_key=ws,
    )
    save = _binding(bindings, "save_workspace_artifact")
    before = list((root / "views" / "transcriptions" / d / tx).rglob("transcript_edit/*"))

    refused = save({"evidence_refs": "not-a-list"})
    assert refused["executed"] is False
    assert refused["refusal"]["reason_code"] == "invalid_request"
    assert refused["refusal"]["retryable"] is True

    after = list((root / "views" / "transcriptions" / d / tx).rglob("transcript_edit/*"))
    assert before == after


def test_invalid_copy_forward_path_is_retryable_without_write(tmp_path, monkeypatch) -> None:
    root = _dossiers_root(tmp_path)
    _patch_roots(monkeypatch, root)
    d, tx, ws = "d-copy", "tx-copy", "ws-copy"
    _minimal_run_layout(root, d, tx)

    bindings = build_transcript_edit_tool_bindings(
        dossier_id=d,
        transcription_id=tx,
        workspace_key=ws,
    )
    save = _binding(bindings, "save_workspace_artifact")
    copy_forward = _binding(bindings, "copy_forward_save_workspace_artifact")

    saved = save(
        {
            "draft_payload": {
                "source_transcript_verbatim": "A",
                "normalized_or_mapping_transcript": "AN",
            }
        }
    )
    assert saved["executed"] is True
    base = saved["outputs"]["working_draft_ref"]
    rev_count_before = len(list((root / "views" / "transcriptions" / d / tx).rglob("rev_*")))

    refused = copy_forward(
        {
            "base_ref": base,
            "copy_forward_paths": ["bad.without.payload.prefix"],
            "set_paths": {"payload.transcript": "x"},
        }
    )
    assert refused["executed"] is False
    assert refused["refusal"]["reason_code"] == "invalid_path_syntax"
    assert refused["refusal"]["retryable"] is True

    rev_count_after = len(list((root / "views" / "transcriptions" / d / tx).rglob("rev_*")))
    assert rev_count_after == rev_count_before


def test_invalid_publication_selection_is_retryable_without_publication(
    tmp_path, monkeypatch
) -> None:
    _, d, ws, bundle = _two_segment_bundle(tmp_path, monkeypatch)
    bindings = build_dossier_transcript_edit_tool_bindings(bundle=bundle)
    save = _binding(bindings, "save_workspace_artifact")
    publish = _binding(bindings, "publish_workspace_artifact")

    refs = []
    for sid, tid, text in (("seg_a", "tx_a", "A"), ("seg_b", "tx_b", "B")):
        out = save(
            {
                "target_ref": qualify_leaf_ref(
                    segment_id=sid, transcription_id=tid, leaf_ref="t0:raw:draft_1"
                ),
                "draft_payload": {
                    "source_transcript_verbatim": text,
                    "normalized_or_mapping_transcript": f"{text}N",
                },
            }
        )
        assert out["executed"] is True
        refs.append(out["outputs"]["working_draft_ref"])

    refused = publish({"source_revision_refs": refs[:1]})
    assert refused["executed"] is False
    assert refused["refusal"]["reason_code"] == "incomplete_segment_coverage"
    assert refused["refusal"]["retryable"] is True

    replay = publish({"source_revision_refs": refs[:1]})
    assert replay["executed"] is False
    assert replay["refusal"]["reason_code"] == "incomplete_segment_coverage"


def test_invalid_scope_remains_terminal(tmp_path, monkeypatch) -> None:
    root = _dossiers_root(tmp_path)
    _patch_roots(monkeypatch, root)
    d, tx = "d-scope", "tx-scope"
    _minimal_run_layout(root, d, tx)

    bindings = build_transcript_edit_tool_bindings(
        dossier_id=d,
        transcription_id=tx,
        workspace_key="ws/../bad",
    )
    save = _binding(bindings, "save_workspace_artifact")
    refused = save({"draft_payload": {"source_transcript_verbatim": "x"}})
    assert refused["executed"] is False
    assert refused["refusal"]["reason_code"] == "invalid_scope_path"
    assert refused["refusal"]["retryable"] is False


def test_existing_retryable_transform_parameter_refusal_unchanged() -> None:
    bindings = build_transcript_edit_tool_bindings(
        dossier_id="d1",
        transcription_id="tx-1",
        workspace_key="ws-key",
    )
    transform = _binding(bindings, "transform_artifact")
    result = transform(
        {
            "ref_id": "image:assoc:tx-1:original",
            "sub_action": "crop",
            "params": {"not": "valid"},
        }
    )
    assert result["executed"] is False
    assert result["refusal"]["reason_code"] == "invalid_transform_params"
    assert result["refusal"]["retryable"] is True
    assert result["refusal"]["blocked_by_invariant"] is False


def test_dossier_storage_corruption_publication_remains_terminal(tmp_path, monkeypatch) -> None:
    _, _, ws, bundle = _two_segment_bundle(tmp_path, monkeypatch)
    bindings = build_dossier_transcript_edit_tool_bindings(bundle=bundle)
    save = _binding(bindings, "save_workspace_artifact")
    publish = _binding(bindings, "publish_workspace_artifact")

    refs = []
    for sid, tid, text in (("seg_a", "tx_a", "A"), ("seg_b", "tx_b", "B")):
        out = save(
            {
                "target_ref": qualify_leaf_ref(
                    segment_id=sid, transcription_id=tid, leaf_ref="t0:raw:draft_1"
                ),
                "draft_payload": {
                    "source_transcript_verbatim": text,
                    "normalized_or_mapping_transcript": f"{text}N",
                },
            }
        )
        refs.append(out["outputs"]["working_draft_ref"])

    published = publish({"source_revision_refs": refs})
    assert published["executed"] is True

    from tooling.mapping.transcript_edit.dossier_publication_paths import (
        dossier_transcript_edit_dossier_output_latest_pointer_path,
    )

    pointer_path = dossier_transcript_edit_dossier_output_latest_pointer_path(
        bundle.inventory.scope.dossier_id,
        ws,
    )
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["extra_compat_field"] = "residue"
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")

    corrupt = publish({"source_revision_refs": refs})
    assert corrupt["executed"] is False
    assert corrupt["refusal"]["reason_code"] == "dossier_publication_pointer_invalid"
    assert corrupt["refusal"]["retryable"] is False
