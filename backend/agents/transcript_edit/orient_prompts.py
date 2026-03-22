"""Transcript-edit domain prompts for orientation (deed / legal-description hints — not generic harness truth)."""
from __future__ import annotations

import json
from typing import Any

from agents.common.identity_composer import (
    Domain,
    InheritanceMode,
    Surface,
    compose_identity_header,
)


def build_transcript_edit_orient_system_message(
    *,
    run_link_id: str = "",
    mission_objective: str = "",
    model: str = "",
) -> str:
    identity = compose_identity_header(
        run_link_id=run_link_id,
        mission_objective=mission_objective,
        domain=Domain.TRANSCRIPT_EDIT,
        surface=Surface.TX_ORIENT_BASELINE,
        inheritance_mode=InheritanceMode.LIGHT,
        model=model,
    )
    leaf = (
        "You are running orientation for a legal-transcript / deed editing mission. "
        "Do not propose edits or execution plans. Respond with JSON only. "
        "The shared runtime exposes generic containers only; you choose titles, tags, optional suggested keys, "
        "and priorities. "
        "For deed-style work, common concerns often include legal-description identity, PLSS calls, ties, closure, "
        "and acreage — situational hints only, not a mandatory checklist. "
        "You may optionally emit legacy ``items`` rows keyed for the transcript-edit checklist read model when helpful; "
        "prefer ``candidate_work_items`` for exploratory work. "
        "When emitting optional checklist ``items``, layer_tag / operational_impact / state follow transcript-edit conventions."
    )
    return identity.header_text + leaf


def build_transcript_edit_orient_user_message(*, transcript_text: str, candidate_texts: list[str]) -> str:
    payload: dict[str, Any] = {
        "task": "orient_and_baseline",
        "output_contract": {
            "orientation_brief": "string (>=20 chars recommended) — what this case is and what matters now",
            "startup_rationale": "string — why you prioritized startup work this way",
            "orientation_notes": "string — optional scratch / caveats",
            "artifact_inventory": [
                {"ref": "optional id or path", "label": "string", "kind": "string", "note": "string"}
            ],
            "candidate_work_items": [
                {
                    "title": "string",
                    "summary": "string",
                    "status": "optional string",
                    "importance": "optional string or number",
                    "mission_impact": "mapping_blocking|mapping_critical|transcript_quality_only|quality|none|...",
                    "mapping_blocking": "optional boolean — overrides mission_impact when present",
                    "evidence_refs": ["string"],
                    "tags": ["string"],
                    "suggested_key": "optional advisory hint for downstream linkage",
                    "suggested_next_actions": ["string"],
                    "span_seed": {
                        "label": "pob|call_chain|plss|tie_to_corner|closure|exception|acreage|misc",
                        "confidence": "low|medium|high",
                        "notes": "string",
                        "start_anchor": "string",
                        "end_anchor": "string",
                        "occurrence": 1,
                    },
                }
            ],
            "candidate_blockers": [
                {
                    "title": "string",
                    "reason": "string",
                    "blocker_kind": "archetype_id or custom:slug",
                    "blocking_class": "mapping_blocking|closure_blocking|source_blocking|quality_only",
                }
            ],
            "candidate_dependencies": ["string"],
            "candidate_focus_candidates": [
                {"title": "optional", "decision_key": "optional", "rationale": "string", "priority": 1}
            ],
            "initial_uncertainties": ["string"],
            "initial_dependencies": ["string"],
            "items": [
                {
                    "comment": "OPTIONAL transcript-edit checklist seeds only — township/range/section/tie_* / acreage / closure_or_pob",
                    "key": "optional canonical checklist key",
                    "state": "unknown|candidate_found|verified|disputed|accepted_with_risk",
                    "operational_impact": "mapping_blocking|transcript_quality_only",
                    "layer_tag": "layer1_canonical_recovery|...",
                    "span_seed": {"start_anchor": "string", "end_anchor": "string"},
                }
            ],
        },
        "schema_notes": [
            "Startup fields may appear under startup_understanding or as top-level siblings; the runtime merges them.",
        ],
        "candidate_texts": candidate_texts,
        "transcript_text": transcript_text,
    }
    return json.dumps(payload, ensure_ascii=False)


def build_transcript_edit_orient_repair_message(*, error_reason: str, raw_content: str) -> str:
    payload = {
        "task": "repair_invalid_orient_response",
        "error_reason": error_reason,
        "previous_output_excerpt": raw_content[:1000],
        "instruction": (
            "Return a single JSON object. Include a non-empty startup signal: either startup_understanding "
            "(or top-level orientation fields) with orientation_brief (>=20 chars) or candidate_work_items / "
            "initial_ledger_items / uncertainties / dependencies / blockers / artifacts, "
            "and/or optional transcript-edit checklist ``items`` when applicable."
        ),
    }
    return json.dumps(payload, ensure_ascii=False)
