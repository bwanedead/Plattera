"""Transcript-edit scoped action_batch_policy for launch context (mechanical caps only)."""

from __future__ import annotations

from typing import Any

from harness.runtime.orchestration.subtasks.contracts import DELEGATE_SUBTASK_ACTION_TYPE

# Visual source observation delegate waves may batch one delegate per point-crop ref.
TRANSCRIPT_EDIT_VISUAL_DELEGATE_MAX_BATCH = 15


def build_transcript_edit_action_batch_policy() -> dict[str, Any]:
    """Raise delegate_subtask batch ceiling for transcript-edit runs only."""

    return {
        "max_batch_size": TRANSCRIPT_EDIT_VISUAL_DELEGATE_MAX_BATCH,
        "max_resolved_actions": TRANSCRIPT_EDIT_VISUAL_DELEGATE_MAX_BATCH,
        "tool_caps": {
            DELEGATE_SUBTASK_ACTION_TYPE: TRANSCRIPT_EDIT_VISUAL_DELEGATE_MAX_BATCH,
        },
    }
