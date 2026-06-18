"""Procedural guidance for deed-to-IR (Brief A skeleton — slim doctrine)."""

from __future__ import annotations

from domains.prompting import PromptBlock

from ..branch import DEED_TO_IR_DOMAIN_ID

DEED_TO_IR_PROCEDURAL_GUIDANCE_SOURCE_REF = (
    "backend/domains/mapping/deed_to_ir/prompting/surfaces/procedural_guidance.py"
)
DEED_TO_IR_PROCEDURAL_GUIDANCE_VERSION = "v1"

DEED_TO_IR_PROCEDURAL_GUIDANCE_TEXT = """\
Use this guidance to orient deed-to-IR work. This is **guidance**, not a hard script.

## Startup orientation
- Read the startup handoff: normalized lane, verbatim lane, parcel metadata, issues, HITL decisions, and evidence refs.
- Inventory **forwardable vs blocked scopes** from inherited `parcel_metadata` without re-adjudicating transcript-edit truth in harness code.
- Track IR work per scope; blocked scopes stay blocked until agent-authored state says otherwise.

## Brief A scope
- IR save/compile/judge tools are not bound yet. Do not pretend those tools exist.
- When tools arrive in later passes, compile/judge gaps become explicit downstream facts — not silent failures.

## What not to do
- Do not parse deed text into IR in bulk prose without durable IR artifacts (once tools exist).
- Do not treat startup handoff as closure or earned geometry truth.
"""


def build_deed_to_ir_procedural_guidance_blocks() -> tuple[PromptBlock, ...]:
    return (
        PromptBlock(
            block_id="deed_to_ir_procedural_guidance",
            layer="domain_guidance",
            owner=DEED_TO_IR_DOMAIN_ID,
            source_path=DEED_TO_IR_PROCEDURAL_GUIDANCE_SOURCE_REF,
            version=DEED_TO_IR_PROCEDURAL_GUIDANCE_VERSION,
            text=DEED_TO_IR_PROCEDURAL_GUIDANCE_TEXT,
        ),
    )
