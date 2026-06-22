"""Procedural guidance for deed-to-IR foundation tools."""

from __future__ import annotations

from domains.prompting import PromptBlock

from ..branch import DEED_TO_IR_DOMAIN_ID

DEED_TO_IR_PROCEDURAL_GUIDANCE_SOURCE_REF = (
    "backend/domains/mapping/deed_to_ir/prompting/surfaces/procedural_guidance.py"
)
DEED_TO_IR_PROCEDURAL_GUIDANCE_VERSION = "v5"

DEED_TO_IR_PROCEDURAL_GUIDANCE_TEXT = """\
Use this guidance to orient deed-to-IR work. This is **guidance**, not a hard script.

## Startup orientation
- Read the startup handoff: normalized lane, verbatim lane, parcel metadata, issues, HITL decisions, evidence refs, and resolution-state counts/summary.
- Inventory **forwardable vs blocked scopes** from inherited `parcel_metadata` without re-adjudicating transcript-edit truth in harness code.
- Full `resolution_state` is available through bounded upstream input hydration — startup shows counts and bounded summary only.

## Foundation workflow (bound)
- Bound tool contracts live in tool specs — treat those as authoritative; this guidance does not duplicate exact tool IDs or request shapes.
- Typical flow: hydrate upstream inputs and feature-graph capabilities; persist agent-authored IR; submit saved IR for mapping when ready; inspect returned mapping, compile, judge, and sidecar artifacts through bounded listing and hydration.
- Attach exact upstream links through `ProvenanceAttachment.source_entity_links` when authoring IR nodes/edges.
- Do not guess schema, operation parameters, units, operand shapes, support status, or provenance contracts. Hydrate capability details in the same orientation batch before the first non-trivial IR save when details are not already in context.

## What not to do
- Do not parse deed text into IR in bulk prose without durable IR artifacts.
- Do not treat startup handoff or resolution summary as closure or earned geometry truth.
- Do not expect deterministic code to infer atom-to-feature associations or source-entity links.
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
