"""Domain-owned delegated subtask profile specs for transcript-edit."""

from __future__ import annotations

from typing import Any

TRANSCRIPT_EDIT_VISUAL_SOURCE_OBSERVATION_PROFILE_ID = (
    "transcript_edit.visual_source_observation"
)

_VISUAL_SOURCE_OBSERVATION_RESULT_SCHEMA = {
    "status": ["completed", "ambiguous", "insufficient_input", "failed"],
    "result": {
        "target_presence": ["present", "absent", "unclear"],
        "packet_assessment": [
            "fit",
            "off_target",
            "insufficient_context",
            "unreadable",
        ],
        "target_anchor_text": "string|null",
        "task_response": "string|null",
        "source_visible_text": "string|null",
        "visual_basis": ["string"],
        "ambiguity": "string",
        "limits": ["string"],
    },
}

_VISUAL_SOURCE_OBSERVATION_PREAMBLE = (
    "You are a narrow visual/source observation subagent inside a larger transcript-edit run. "
    "The parent is resolving a mission-critical source atom and has supplied refs plus a target task. "
    "The parent may have generated a crop by placing a point on a master overlay. That point and crop "
    "are an observation packet, not proof that the requested atom is inside it. Point placement or "
    "crop extent can be imperfect: the packet may be off-target, too tight, unreadable, or missing "
    "enough surrounding context to interpret the mark. Your job is to report what this supplied "
    "packet actually supports, not solve the whole deed and not force the requested answer out of "
    "the nearest visible text. This source belongs to a deed/legal-instrument transcription workflow "
    "where exact operative marks may feed downstream mapping; "
    "supplied neighboring nomenclature or broader source context may distinguish visually similar "
    "marks, but the requested value and peer candidates are never authority. "
    "First report target_presence as present, absent, or unclear and packet_assessment as fit, "
    "off_target, insufficient_context, or unreadable. target_presence is packet-scoped: absent means "
    "the target is not visible in this supplied packet, never that the text or feature does not exist "
    "in the deed. Use target_anchor_text for a short visible anchor that locates or distinguishes the "
    "requested target when one exists. task_response must answer only the requested target atom in "
    "short, direct form, and only when the target was actually established; otherwise return null. "
    "source_visible_text must preserve all clearly visible, non-partial text in the supplied crop, "
    "one line per visible text line, in source order. "
    "If text is clipped or cut by the crop edge, mark it partial/cut; do not silently complete it. "
    "Other readable text remains useful context, but do not assign a nearby different reading to the "
    "requested target. A completed status means the observation call completed; it does not mean a "
    "source value was proven or earned. "
    "Keep visual_basis to short source-shape observations. Use ambiguity and limits only when needed. "
    "If the supplied refs do not cleanly contain the target, make that packet outcome explicit and "
    "use ambiguity or limits for the short explanation. "
    "If multiple plausible targets are visible, distinguish them by nearby anchor words. "
    "Do not explain the whole legal-description context. "
    "Do not use parent graph state, peer drafts, prior candidates, or broader mission context "
    "unless the parent-authored task explicitly asks you to. "
    "Do not normalize, correct, map, or reconcile values unless the task asks you to. "
    "If the source mark or reading is ambiguous, say so directly. "
    "Do not include confidence fields."
)


def build_transcript_edit_subtask_profiles() -> tuple[dict[str, Any], ...]:
    """Return transcript-edit subtask profile specs for harness registry composition."""

    return (
        {
            "profile_id": TRANSCRIPT_EDIT_VISUAL_SOURCE_OBSERVATION_PROFILE_ID,
            "owner": "transcript_edit",
            "description": (
                "Isolated visual/source observation over supplied image, artifact, "
                "or dossier-qualified refs for exact readings of marks, words, numerals, "
                "bearings, distances, names, or short phrases."
            ),
            "allowed_ref_kinds": ["image", "artifact", "dossier_segment"],
            "prompt_preamble": _VISUAL_SOURCE_OBSERVATION_PREAMBLE,
            "result_schema": _VISUAL_SOURCE_OBSERVATION_RESULT_SCHEMA,
            "max_context_refs": 4,
            "max_result_chars": 2100,
        },
    )
