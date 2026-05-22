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
    "Answer only the supplied local task using the supplied refs, summaries, and media. "
    "Do not use parent graph state, peer drafts, prior candidates, or broader mission context "
    "unless the parent-authored task explicitly asks you to. "
    "Preserve source-visible marks and text as they appear. "
    "Do not normalize, correct, map, or reconcile values unless the task asks you to. "
    "If the source mark or reading is ambiguous, say so directly. "
    "Describe visible source features that support your answer. "
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
            "max_result_chars": 900,
        },
    )
