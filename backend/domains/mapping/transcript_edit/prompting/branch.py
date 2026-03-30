"""Transcript-edit domain branch prompt doctrine."""

from __future__ import annotations

from dataclasses import dataclass


TRANSCRIPT_EDIT_DOMAIN_ID = "transcript_edit"
TRANSCRIPT_EDIT_FAMILY_ID = "mapping"
TRANSCRIPT_EDIT_BRANCH_SOURCE_REF = "backend/domains/mapping/transcript_edit/prompting/branch.py"
TRANSCRIPT_EDIT_BRANCH_VERSION = "v1"

TRANSCRIPT_EDIT_BRANCH_TEXT = (
    "You are working the transcript-edit domain.\n"
    "Use the provided transcript, mission state, and evidence to understand the case.\n"
    "Work toward closure on the current transcript repair task with the smallest sensible next move.\n"
    "Keep reasoning grounded in the material in front of you and the current mission posture."
)


@dataclass(frozen=True)
class PromptBlock:
    block_id: str
    layer: str
    owner: str
    source_path: str
    version: str
    text: str


def build_transcript_edit_branch_blocks() -> tuple[PromptBlock, ...]:
    return (
        PromptBlock(
            block_id="transcript_edit_domain_branch",
            layer="domain_branch",
            owner=TRANSCRIPT_EDIT_DOMAIN_ID,
            source_path=TRANSCRIPT_EDIT_BRANCH_SOURCE_REF,
            version=TRANSCRIPT_EDIT_BRANCH_VERSION,
            text=TRANSCRIPT_EDIT_BRANCH_TEXT,
        ),
    )

