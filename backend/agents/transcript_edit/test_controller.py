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
    TranscriptSpanOpenerTool,
)
from backend.agents.transcript_edit.controller import run_transcript_edit_controller_loop
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


def _session_manager() -> KernelSessionManager:
    executor = ActionExecutor(
        deps=ActionExecutorDeps(
            transcript_auditor=TranscriptAuditTool(),
            transcript_span_opener=TranscriptSpanOpenerTool(),
            transcript_plan_applier=TranscriptEditPlanApplyTool(),
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
