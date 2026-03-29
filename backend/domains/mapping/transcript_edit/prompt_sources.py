"""Transcript-edit domain prompt source blocks.

The authored domain doctrine lives here; prompting.py should import these blocks
and assemble them with packet/run context instead of owning the wording itself.
"""

from __future__ import annotations

from hashlib import sha256

from domains.common.prompt_sources import PromptSourceBlock


_PROMPT_SOURCE_OWNER = "transcript_edit"
_PROMPT_SOURCE_PATH = "backend/domains/mapping/transcript_edit/prompt_sources.py"

TRANSCRIPT_EDIT_FOCUS_AUTHORED_ATTENTION_DOCTRINE = (
    "Do not behave like a scripted checklist runner; choose the next bounded move from the evolving case model. "
    "When continuity is absent, the first bounded focus should come from LLM orientation / startup understanding and the candidate context, not from deterministic ranking. "
)
TRANSCRIPT_EDIT_PLANNER_SUPPORT_STATE_DOCTRINE = (
    "Treat support_state.item_context / the investigation brief as a living sticky note for the case, not as canonical truth. "
    "Treat support_state.continuity_context, support_state.evidence_context, and support_state.item_history as bounded, observational context. "
    "Do not reintroduce steering-shaped working plans or policy signals under softer names. "
)
TRANSCRIPT_EDIT_RESOLVER_SUPPORT_STATE_DOCTRINE = (
    "Treat support_state.item_context as the current sticky-note summary of the run; it is editable, additive context, not canonical truth. "
    "Treat support_state.continuity_context as the active-item continuity rail, support_state.evidence_context as bounded evidence carriage, and support_state.item_history as recent item-local history. "
    "Treat support_state.blocker_posture as derived observations only: weak understanding may bias toward orientation/inventory/verification, narrow understanding may permit repair or bounded HITL, and repeated no-signal work should be discouraged. "
)


def _make_block(*, block_id: str, text: str, version: str = "v1") -> PromptSourceBlock:
    return PromptSourceBlock(
        block_id=block_id,
        layer="domain_branch",
        owner=_PROMPT_SOURCE_OWNER,
        source_path=_PROMPT_SOURCE_PATH,
        version=version,
        text=text,
        content_hash=sha256(text.encode("utf-8")).hexdigest(),
    )


def build_transcript_edit_branch_blocks(*, inheritance_mode: str) -> tuple[PromptSourceBlock, ...]:
    """Return transcript-edit branch blocks for the requested inheritance mode."""
    light = str(inheritance_mode or "").strip().lower() == "light"
    if light:
        return (
            _make_block(
                block_id="transcript_edit_attention_doctrine",
                text=(
                    "Do not behave like a scripted checklist runner; choose the next bounded move from the evolving case model. "
                    "When continuity is absent, the first bounded focus comes from LLM startup understanding and candidate context, not deterministic ranking. "
                ),
            ),
            _make_block(
                block_id="transcript_edit_planner_support_state",
                text=(
                    "Treat support_state.item_context as sticky-note context, support_state.continuity_context as continuity carriage, and support_state.evidence_context as observations only. "
                ),
            ),
            _make_block(
                block_id="transcript_edit_resolver_support_state",
                text=(
                    "Treat support_state.item_context as additive context, support_state.continuity_context as the active-item rail, and support_state.blocker_posture as derived observations."
                ),
            ),
        )
    return (
        _make_block(
            block_id="transcript_edit_attention_doctrine",
            text=TRANSCRIPT_EDIT_FOCUS_AUTHORED_ATTENTION_DOCTRINE,
        ),
        _make_block(
            block_id="transcript_edit_planner_support_state",
            text=TRANSCRIPT_EDIT_PLANNER_SUPPORT_STATE_DOCTRINE,
        ),
        _make_block(
            block_id="transcript_edit_resolver_support_state",
            text=TRANSCRIPT_EDIT_RESOLVER_SUPPORT_STATE_DOCTRINE,
        ),
    )

