"""Runtime bridge from iteration focus packets to the standalone edit planner (`propose_plan`)."""
from __future__ import annotations

from typing import Any

from .planner import TranscriptEditPlanPlanner


def run_standalone_edit_planner_for_focus_packet(
    *,
    planner_client: TranscriptEditPlanPlanner,
    model: str,
    focus_packet: dict[str, Any],
    findings_summary: dict[str, Any],
    top_findings: list[dict[str, Any]],
    span_context: list[dict[str, Any]],
    image_verification: dict[str, Any] | None,
    mapping_priority_focus: dict[str, Any] | None,
    max_attempts: int,
    run_link_id: str = "",
    mission_objective: str = "",
) -> tuple[Any, str, str]:
    """Invoke ``propose_plan`` with the same bounded ``execution_context`` as the resolver path."""
    execution_context = focus_packet.get("execution_context") if isinstance(focus_packet.get("execution_context"), dict) else None
    investigation_brief = focus_packet.get("investigation_brief") if isinstance(focus_packet.get("investigation_brief"), dict) else None
    working_plan = focus_packet.get("working_plan") if isinstance(focus_packet.get("working_plan"), dict) else None
    span_trim = [dict(x) for x in span_context if isinstance(x, dict)][:32]
    findings_trim = [dict(x) for x in top_findings if isinstance(x, dict)][:12]
    return planner_client.propose_plan(
        model=model,
        source_transcript_ref=str(focus_packet.get("source_transcript_ref") or ""),
        source_transcript_hash=str(focus_packet.get("source_transcript_hash") or ""),
        findings_summary=findings_summary if isinstance(findings_summary, dict) else {},
        top_findings=findings_trim,
        span_context=span_trim,
        image_verification=image_verification if isinstance(image_verification, dict) else {},
        candidate_disagreement_hints=None,
        mapping_priority_focus=mapping_priority_focus if isinstance(mapping_priority_focus, dict) else {},
        max_attempts=max_attempts,
        investigation_brief=investigation_brief,
        working_plan=working_plan,
        run_link_id=run_link_id,
        mission_objective=mission_objective,
        execution_context=execution_context,
    )
