"""Transcript-edit domain identity and prompt-branch declaration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptEditManifest:
    domain_id: str = "transcript_edit"
    family_id: str = "mapping"
    display_name: str = "Transcript Edit"
    prompt_branch_source_ref: str = "domains.mapping.transcript_edit.prompting.branch"


def build_transcript_edit_manifest() -> TranscriptEditManifest:
    return TranscriptEditManifest()

