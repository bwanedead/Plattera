from __future__ import annotations

import json
import tempfile
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agent_kernel.actions import ActionExecutor, ActionExecutorDeps
from backend.agent_kernel.session import KernelSessionManager
from backend.agent_kernel.tooling import (
    TranscriptAuditTool,
    TranscriptEditPlanApplyTool,
    TranscriptMappingPromoterTool,
    TranscriptSpanSeedsSaverTool,
    TranscriptSpanOpenerTool,
)
from backend.agents.transcript_edit.controller import (
    _critical_disagreement_findings,
    _image_checks_from_disagreement_hints,
    run_transcript_edit_controller_loop,
)
from backend.agents.transcript_edit.contracts import TranscriptEditAgentRunRequest
from backend.transcript_edit.contracts import EditPlanV0


class _InMemoryPersistence:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], Any] = {}

    def save_run_artifact(self, run_artifact):  # type: ignore[no-untyped-def]
        key = (run_artifact.request_id, run_artifact.run_id)
        self._store[key] = run_artifact
        return {"path": f"in-memory://{run_artifact.request_id}/{run_artifact.run_id}.json"}

    def get_run_artifact(self, request_id: str, run_id: str):  # type: ignore[no-untyped-def]
        return self._store.get((request_id, run_id))


class _ImageVerifierStub:
    def verify_transcript_with_image(self, inputs):  # type: ignore[no-untyped-def]
        del inputs
        return {
            "artifact_ref": {"artifact_path": "in-memory://tx/image_verify.json"},
            "reason_codes": ["tx_image_verified"],
            "tx_image_verify_summary": {"total_checks": 1, "match_count": 1, "mismatch_count": 0, "unclear_count": 0},
            "tx_image_verify_results": [{"check_id": "c1", "status": "match", "confidence": "high"}],
        }


class _ImageVerifierUnclearStub:
    def verify_transcript_with_image(self, inputs):  # type: ignore[no-untyped-def]
        del inputs
        return {
            "artifact_ref": {"artifact_path": "in-memory://tx/image_verify_unclear.json"},
            "reason_codes": ["tx_image_verified"],
            "tx_image_verify_summary": {"total_checks": 2, "match_count": 1, "mismatch_count": 0, "unclear_count": 1},
            "tx_image_verify_results": [{"check_id": "c1", "status": "unclear", "confidence": "low"}],
        }


class _PlannerSuccess:
    def propose_plan(self, **kwargs):  # type: ignore[no-untyped-def]
        source_ref = kwargs["source_transcript_ref"]
        source_hash = kwargs["source_transcript_hash"]
        old_excerpt = "Beginning at NW corner."
        plan = EditPlanV0.model_validate(
            {
                "plan_version": "edit_plan_v0",
                "source_transcript_ref": source_ref,
                "source_transcript_hash": source_hash,
                "plan_id": "p1",
                "summary": "close call chain",
                "ops": [
                    {
                        "op_id": "op-1",
                        "op_type": "replace_span",
                        "change_class": "normalization",
                        "confidence": "high",
                        "review_required": False,
                        "reason": "add explicit close phrase",
                        "evidence_refs": [source_ref],
                        "target": {"locator_type": "offsets", "start_char": 0, "end_char": len(old_excerpt)},
                        "expected_old": {"old_excerpt": old_excerpt},
                        "new_text": "Beginning at Northwest corner to point of beginning.",
                    }
                ],
                "global_flags": {"review_required": False},
            }
        )
        return plan, "ok", json.dumps(plan.model_dump(mode="json"))


class _PlannerInvalid:
    def propose_plan(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        return None, "planner_invalid_response", "{bad}"


class _PlannerNoOps:
    def propose_plan(self, **kwargs):  # type: ignore[no-untyped-def]
        source_ref = kwargs["source_transcript_ref"]
        source_hash = kwargs["source_transcript_hash"]
        plan = EditPlanV0.model_validate(
            {
                "plan_version": "edit_plan_v0",
                "source_transcript_ref": source_ref,
                "source_transcript_hash": source_hash,
                "plan_id": "noop",
                "summary": "no safe edits",
                "ops": [],
                "global_flags": {"review_required": True, "rationale": "conflicting evidence"},
            }
        )
        return plan, "ok", json.dumps(plan.model_dump(mode="json"))


class _PlannerRaises:
    def propose_plan(self, **kwargs):  # type: ignore[no-untyped-def]
        del kwargs
        raise RuntimeError("simulated network error")


def _session_manager(image_verifier=None) -> KernelSessionManager:
    executor = ActionExecutor(
        deps=ActionExecutorDeps(
            transcript_auditor=TranscriptAuditTool(),
            transcript_span_opener=TranscriptSpanOpenerTool(),
            transcript_image_verifier=image_verifier or _ImageVerifierStub(),
            transcript_plan_applier=TranscriptEditPlanApplyTool(),
            transcript_span_seeds_saver=TranscriptSpanSeedsSaverTool(),
            transcript_promoter=TranscriptMappingPromoterTool(),
        )
    )
    return KernelSessionManager(action_executor=executor, persistence_service=_InMemoryPersistence())


def test_transcript_controller_audit_plan_apply_audit_promote() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(json.dumps({"sections": [{"id": "s1", "body": "Beginning at NW corner."}]}), encoding="utf-8")
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=3,
                auto_promote=True,
            ),
            request_id_prefix="tx-test-ok",
            planner=_PlannerSuccess(),
        )
        assert result.status == "completed"
        assert result.reason_code in {"tx_agent_clean_promoted", "tx_agent_clean_no_promote"}
        assert result.review_required is False
        assert isinstance(result.latest_refs.get("tx_span_seeds_ref"), dict)


def test_transcript_controller_invalid_planner_stops_needs_review_no_promote() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(json.dumps({"sections": [{"id": "s1", "body": "Beginning at NW corner."}]}), encoding="utf-8")
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=2,
                max_invalid_plan_attempts=2,
                auto_promote=True,
            ),
            request_id_prefix="tx-test-bad",
            planner=_PlannerInvalid(),
        )
        assert result.status == "needs_review"
        assert result.review_required is True
        assert result.reason_code.startswith("tx_agent_plan_invalid")


def test_transcript_controller_redundancy_conflict_blocks_autopromote() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(json.dumps({"sections": [{"id": "s1", "body": "Simple legal heading only."}]}), encoding="utf-8")
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=2,
                auto_promote=True,
                candidate_texts=[
                    "Range seventy-five (75) West",
                    "Range seventy-four (74) West",
                    "Range seventy-five (75) West",
                ],
            ),
            request_id_prefix="tx-test-disagreement",
            planner=_PlannerNoOps(),
        )
        assert result.status == "needs_review"
        assert result.review_required is True
        assert result.reason_code.startswith("tx_agent_no_safe_plan_for_findings")


def test_transcript_controller_planner_exception_degrades_to_needs_review() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(json.dumps({"sections": [{"id": "s1", "body": "Beginning at NW corner."}]}), encoding="utf-8")
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=2,
                max_invalid_plan_attempts=1,
                auto_promote=True,
                candidate_texts=[
                    "Range seventy-five (75) West",
                    "Range seventy-four (74) West",
                ],
            ),
            request_id_prefix="tx-test-planner-exc",
            planner=_PlannerRaises(),
        )
        assert result.status == "needs_review"
        assert result.review_required is True
        assert result.reason_code.startswith("tx_agent_plan_invalid:planner_exception")


def test_transcript_controller_blocks_promote_when_final_image_sanity_unclear() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(json.dumps({"sections": [{"id": "s1", "body": "Simple heading and legal text."}]}), encoding="utf-8")
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(image_verifier=_ImageVerifierUnclearStub()),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=2,
                auto_promote=True,
            ),
            request_id_prefix="tx-test-final-image-gate",
            planner=_PlannerSuccess(),
        )
        assert result.status == "needs_review"
        assert result.review_required is True
        assert result.reason_code.startswith("tx_agent_final_image_verify_failed")


def test_disagreement_findings_include_bearing_conflict() -> None:
    findings = _critical_disagreement_findings(
        {
            "bearing_values": [
                {"value": "n 4 e", "count": 2},
                {"value": "n 2 e", "count": 1},
            ]
        }
    )
    ids = {str(item.get("finding_id")) for item in findings if isinstance(item, dict)}
    assert "candidate_disagreement_bearing_conflict_001" in ids


def test_image_checks_include_bearing_check_when_disagreement_present() -> None:
    checks = _image_checks_from_disagreement_hints(
        {
            "bearing_values": [
                {"value": "n 4 e", "count": 2},
                {"value": "n 2 e", "count": 1},
            ]
        }
    )
    check_ids = {str(item.get("check_id")) for item in checks if isinstance(item, dict)}
    assert "image_check_bearing_tokens" in check_ids


def test_transcript_controller_hitl_prompt_is_non_blocking_without_feedback() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(json.dumps({"sections": [{"id": "s1", "body": "Simple legal heading only."}]}), encoding="utf-8")
        progress_events: list[dict[str, Any]] = []
        result = run_transcript_edit_controller_loop(
            session_manager=_session_manager(),
            request=TranscriptEditAgentRunRequest(
                dossier_id="D1",
                source_transcript_ref=str(source),
                mode="audit_then_repair_then_promote",
                max_iterations=1,
                auto_promote=False,
                candidate_texts=[
                    "Range seventy-five (75) West",
                    "Range seventy-four (74) West",
                ],
                hitl_enabled=True,
            ),
            request_id_prefix="tx-agent-hitl-nonblocking",
            planner=_PlannerNoOps(),
            progress_cb=lambda evt: progress_events.append(evt if isinstance(evt, dict) else {}),
        )
        assert result.status == "needs_review"
        assert result.reason_code.startswith("tx_agent_no_safe_plan_for_findings")
        assert result.reason_code != "human_feedback_timeout"
        assert any(isinstance(evt, dict) for evt in progress_events)
