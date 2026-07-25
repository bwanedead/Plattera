"""Dossier-scale transcript-edit guidance layered over the common domain doctrine."""

from __future__ import annotations

from domains.prompting import PromptBlock

from ..branch import TRANSCRIPT_EDIT_DOMAIN_ID


TRANSCRIPT_EDIT_DOSSIER_GUIDANCE_VERSION = "v1"
_DOSSIER_GUIDANCE_SOURCE_PATH = (
    "backend/domains/mapping/transcript_edit/prompting/surfaces/dossier_guidance.py"
)

TRANSCRIPT_EDIT_DOSSIER_GUIDANCE_TEXT = """\
## Dossier-scale transcript editing

This run covers one instrument across an ordered dossier of source segments. Treat it as one continuous semantic job with one holistic work universe. Segment boundaries identify source/evidence scope and independent save lineages; they do not divide the instrument's meaning and do not imply a fresh inventory, closure cycle, or agent run for each page.

Work through bounded evidence windows while retaining the dossier-wide inventory. Choose each window from the actual continuity problem: one segment may be enough, or the end of one segment and the beginning of the next may need joint review. A sentence, call, table, or numbered sequence that reaches a segment boundary is not missing merely because it continues elsewhere. Hydrate the adjacent segment and follow the source before declaring an omission or blocker. These windows are attention slices inside one run, not independent transcript-edit jobs.

Every transcription run listed under a segment is a peer candidate. No run is automatically best, longest, consensus, or authoritative. Compare and select from evidence. Save authored work to the chosen segment/run lineage using dossier-qualified refs, and repair every affected segment when a boundary review exposes a split, duplicate, omission, or contradiction.

Before dossier publication, reconcile the full ordered instrument: every topology segment must have one explicitly chosen exact working revision, adjacent boundaries must be coherent, and unresolved material must remain honestly open, blocked, or sent to HITL. Publish with the plural `source_revision_refs` contract. Missing coverage or unsafe source content is not permission to substitute a different run or silently drop a segment.

This dossier represents one instrument. A reference to another deed or external instrument is a dependency fact, not another segment of this dossier; do not merge separate instruments into this transcript-edit output.
"""


def build_transcript_edit_dossier_guidance_block() -> PromptBlock:
    return PromptBlock(
        block_id="transcript_edit_dossier_guidance",
        layer="domain_guidance",
        owner=TRANSCRIPT_EDIT_DOMAIN_ID,
        source_path=_DOSSIER_GUIDANCE_SOURCE_PATH,
        version=TRANSCRIPT_EDIT_DOSSIER_GUIDANCE_VERSION,
        text=TRANSCRIPT_EDIT_DOSSIER_GUIDANCE_TEXT,
    )
