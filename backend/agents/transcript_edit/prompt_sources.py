"""Transcript-edit domain prompt source blocks.

The authored domain doctrine lives here; prompting.py should import these blocks
and assemble them with packet/run context instead of owning the wording itself.
"""

from __future__ import annotations

from hashlib import sha256

from agents.common.prompt_sources import PromptSourceBlock


_PROMPT_SOURCE_OWNER = "transcript_edit"
_PROMPT_SOURCE_PATH = "backend/agents/transcript_edit/prompt_sources.py"

TRANSCRIPT_EDIT_FOCUS_AUTHORED_ATTENTION_DOCTRINE = (
    "Do not behave like a scripted checklist runner; choose the next bounded move from the evolving case model. "
    "When continuity is absent, the first bounded focus should come from LLM orientation / startup understanding and the candidate context, not from deterministic ranking. "
)
TRANSCRIPT_EDIT_PLANNER_SUPPORT_STATE_DOCTRINE = (
    "Treat support_state.investigation_brief / the investigation brief as a living sticky note for the case, not as canonical truth. "
    "Treat support_state.working_plan as advisory case context, not as doctrine. "
    "Treat support_state.policy_signals as derived runtime observations, not as doctrine or truth. "
)
TRANSCRIPT_EDIT_RESOLVER_SUPPORT_STATE_DOCTRINE = (
    "Treat support_state.investigation_brief as the current sticky-note summary of the run; it is editable, additive context, not canonical truth. "
    "Treat support_state.working_plan as advisory context; it may be adjusted when the case understanding changes. "
    "Treat support_state.policy_signals as derived observations: weak understanding should bias toward orientation/inventory/verification, narrow understanding may permit repair or bounded HITL, and repeated no-signal work should be discouraged. "
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
                    "Treat support_state.investigation_brief as sticky-note context, support_state.working_plan as advisory, and support_state.policy_signals as observations only. "
                ),
            ),
            _make_block(
                block_id="transcript_edit_resolver_support_state",
                text=(
                    "Treat support_state.investigation_brief as additive context, working_plan as advisory, and policy_signals as derived observations."
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
