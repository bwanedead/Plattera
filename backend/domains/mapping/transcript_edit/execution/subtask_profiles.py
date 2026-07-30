"""Domain-owned delegated subtask profile specs for transcript-edit."""

from __future__ import annotations

from typing import Any

TRANSCRIPT_EDIT_VISUAL_SOURCE_OBSERVATION_PROFILE_ID = (
    "transcript_edit.visual_source_observation"
)

_VISUAL_SOURCE_OBSERVATION_RESULT_SCHEMA = {
    "status": ["completed", "ambiguous", "insufficient_input", "failed"],
    "result": {
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
    "Your job is to answer that target accurately from the supplied media, not solve the whole deed. "
    "Use the parent task wording to identify the requested mark, value, word, or span. "
    "Return exactly two primary outputs: task_response and source_visible_text. "
    "task_response must answer only the requested target atom in short, direct form. "
    "source_visible_text must preserve all clearly visible, non-partial text in the supplied crop, "
    "one line per visible text line, in source order. "
    "If text is clipped or cut by the crop edge, mark it partial/cut; do not silently complete it. "
    "If the target atom is not visible, say so in task_response even when other readable text is present. "
    "Keep visual_basis to short source-shape observations. Use ambiguity and limits only when needed. "
    "If the supplied refs do not cleanly contain the target, say so in ambiguity or limits "
    "instead of reading a nearby different value. "
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
