"""Provider-agnostic prompt construction for the agent controller loop."""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class PromptBundle:
    developer_message: str
    user_message: str


_DEVELOPER_MESSAGE = (
    "Mission: convert deed context into a FeatureGraph IR, then run deterministic physics gates "
    "(compile, judge, bundle) and only attempt DECLARE_DONE when claimability is likely ready.\n"
    "Protocol: call exactly one tool from the provided tools list. Never output prose.\n"
    "Continuity memory:\n"
    "- Read memory.run_summary_log as condensed history.\n"
    "- If you provide iteration_summary (Memory Docket v0), describe only what happened this iteration (delta-only).\n"
    "- Timing rule: actual_observation = what you just observed from the latest kernel result/current Context Packet.\n"
    "- Timing rule: expected_observation = what you expect to observe next iteration if the proposed action succeeds.\n"
    "- Repetition is OK only if it happened again this iteration.\n"
    "- Do not restate the entire run_summary_log and never paste deed text into iteration_summary.\n"
    "- iteration_summary is optional and best-effort; controller may truncate/ignore it.\n"
    "- Suggested iteration_summary keys: action, intent, actual_observation, expected_observation, state_delta, open_issues, next_move, confidence, do_not_repeat.\n"
    "User-facing narration (optional):\n"
    "- Optionally include display_delta as one plain-language sentence (about what you are doing or what changed).\n"
    "- Keep display_delta deed-relevant and <= ~180 chars.\n"
    "- Describe only what is supported by the current Context Packet and latest observed results; do not add new claims.\n"
    "- Do not include tool/module names, file paths, reason codes, or internal jargon.\n"
    "- Omit display_delta for routine/repetitive steps (especially repeated inspections or routine reruns with no new gap/change).\n"
    "- Prefer display_delta when drafting, judging/repairing, bundling, georeferencing, validating, or after a refusal changes the plan.\n"
    "Tool discipline:\n"
    "- HYDRATE_DEED: use when deed text ref/excerpt is missing.\n"
    "- OPEN_ARTIFACT: bounded summary/debug inspection only; requires one of artifact_ref | artifact_path | corpus_entry_ref. Prefer judge_ref/compile_ref repair views over reopening IR/deed when physics gaps already exist.\n"
    "- DRAFT_IR: always include graph (top-level tool parameter, FeatureGraph JSON); deed refs are provenance only. Draft minimal valid graph first, then iterate based on judge gaps.\n"
    "- OPEN_TEXT_SPANS: canonical bounded verbatim deed recall; use raw spans [{start_char,end_char}] or span_ids + deed_span_index_ref.\n"
    "- UPSERT_DEED_SPAN_INDEX: save/update span bookmarks with stable span_id, ranges, and bounded intended_verbatim_text.\n"
    "- RETRIEVE_EVIDENCE: optional; requires a non-empty query.\n"
    "- COMPILE/JUDGE: immediately run after each IR change to refresh deterministic gaps before more inspection.\n"
    "- BUNDLE: run after compile/judge when preparing completion package.\n"
    "Done semantics: kernel claimability indicates structural readiness; you are semantic arbiter. "
    "DECLARE_DONE must include concise justification with artifact refs and evidence/assumptions.\n"
    "Refs-not-blobs: prefer artifact refs, avoid large inline payloads.\n"
    "Deed span bookmarks:\n"
    "- Canonical deed remains available by inputs.deed_text_artifact_ref.\n"
    "- For repeated source verification on long deeds, use span bookmarks: UPSERT_DEED_SPAN_INDEX -> OPEN_TEXT_SPANS -> confirm/adjust.\n"
    "- Prefer reopening bookmarked spans by span_id instead of reloading the whole deed repeatedly.\n"
    "FeatureGraph IR cheatsheet (v0):\n"
    "- Use ContextPacket.ir_ops_menu.supported_compilable_ops as the current allowed op vocabulary for compilable op_expr authoring.\n"
    "- If an operation is registered but not compilable yet, prefer direct geometry + annotation metadata over invented ops.\n"
    "- Shape: {graph_id, nodes[], edges[], metadata{}}.\n"
    "- Node shape: {id, kind, label?, metadata?, one-of: geometry | op_expr | feature_ref}.\n"
    "- kind vocabulary: point, curve, region, frame, constraint, annotation, unknown.\n"
    "- Rule: node content is mutually exclusive (geometry XOR op_expr XOR feature_ref).\n"
    "- Edges: {source_id, target_id, edge_type?}; edge IDs must reference existing nodes.\n"
    "- Prefer op_expr over large coordinate blobs when possible.\n"
    "Micro example 1:\n"
    '{"graph_id":"g_min_1","nodes":[{"id":"start","kind":"point","geometry":{"type":"Point","coordinates":[0.0,0.0]}},{"id":"boundary_curve","kind":"curve","geometry":{"type":"LineString","coordinates":[[0.0,0.0],[100.0,0.0]]}}],"edges":[{"source_id":"start","target_id":"boundary_curve","edge_type":"anchored_to"}],"metadata":{"source":"deed"}}\n'
    "Micro example 2:\n"
    '{"graph_id":"g_min_2","nodes":[{"id":"boundary_curve","kind":"curve","geometry":{"type":"LineString","coordinates":[[0.0,0.0],[10.0,0.0],[10.0,10.0],[0.0,10.0],[0.0,0.0]]}},{"id":"parcel_region","kind":"region","op_expr":{"op_name":"Close","operands":["boundary_curve"]}}],"edges":[{"source_id":"boundary_curve","target_id":"parcel_region","edge_type":"depends_on"}],"metadata":{"source":"deed"}}'
)


def build_developer_message() -> str:
    return _DEVELOPER_MESSAGE


def build_user_message(*, context_packet: dict[str, object]) -> str:
    return (
        "Call exactly one tool from the provided tools list. "
        "Use top-level tool parameters (do not wrap fields in a `kernel_step` envelope or nested `args`). "
        "Respect tool_menu and refs-not-blobs. Use the Context Packet below. "
        f"ContextPacket JSON: {json.dumps(context_packet, sort_keys=True)}"
    )


def build_repair_user_message(*, parse_error: str | None) -> str:
    return (
        "Your prior proposal was invalid. Call exactly one provided tool using its top-level parameters (no `kernel_step` envelope). "
        "Use only the provided repair tool and follow last_refusal.fix.required_fields exactly. "
        "Use tool_cheatsheet[].minimal_working_example as the canonical repair skeleton and fill placeholders. "
        f"Prior parse error: {parse_error or 'unknown'}."
    )


def build_refusal_repair_user_message(
    *,
    reason_code: str,
    required_fields: list[str],
    minimal_working_example: dict[str, object] | None,
) -> str:
    return (
        "Retryable refusal repair. Call exactly one tool and repair the previous refusal.\n"
        "Copy the minimal working example args verbatim first, then only fill placeholders.\n"
        f"Refusal reason_code: {reason_code}\n"
        f"Required fields: {json.dumps(required_fields, ensure_ascii=True)}\n"
        f"Minimal working example: {json.dumps(minimal_working_example or {}, ensure_ascii=True)}\n"
        "Do not return empty args. Do not change to a different tool unless the example requires it."
    )
