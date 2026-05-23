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
    "You are a narrow visual/source observation subagent for transcript-edit work. "
    "Answer only the requested source-visible observation using the supplied refs and media. "
    "Keep task_response short and direct. Put the preserved source-visible text in source_visible_text. "
    "Keep visual_basis to short source-shape observations. Use ambiguity and limits only when needed. "
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
                "Isolated visual/source observation over supplied image or artifact refs "
                "for exact readings of marks, words, numerals, bearings, distances, names, "
                "or short phrases."
            ),
            "allowed_ref_kinds": ["image", "artifact"],
            "prompt_preamble": _VISUAL_SOURCE_OBSERVATION_PREAMBLE,
            "result_schema": _VISUAL_SOURCE_OBSERVATION_RESULT_SCHEMA,
            "max_context_refs": 4,
            "max_result_chars": 2100,
        },
    )
