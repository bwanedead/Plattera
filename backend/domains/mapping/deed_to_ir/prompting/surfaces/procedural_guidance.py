"""Procedural guidance for deed-to-IR foundation tools."""

from __future__ import annotations

from domains.prompting import PromptBlock

from ..branch import DEED_TO_IR_DOMAIN_ID

DEED_TO_IR_PROCEDURAL_GUIDANCE_SOURCE_REF = (
    "backend/domains/mapping/deed_to_ir/prompting/surfaces/procedural_guidance.py"
)
DEED_TO_IR_PROCEDURAL_GUIDANCE_VERSION = "v7"

DEED_TO_IR_PROCEDURAL_GUIDANCE_TEXT = """\
Use this guidance to orient deed-to-IR work. This is **guidance**, not a hard script.

## Startup orientation
- Read `inherited_handoff_conditions` first — it is the high-salience mechanical copy of upstream parcel metadata, issues, HITL decisions, evidence refs, and transcript lane excerpts.
- Treat inherited resolution rows as **input/provenance**, not as local work inventory to recreate.
- Full `resolution_state` remains available through bounded upstream input hydration when you need exact upstream rows.

## Draft IR lifecycle
- `save_ir_artifact` saves a **draft checkpoint** (`draft_version` such as v0, v1, v2) — not final publication.
- After initial handoff/capability hydration, prefer saving a first bounded draft IR over rereading upstream lanes.
- Compile/judge feedback on draft save is expected mechanical feedback — repair the draft and save again.
- `mechanically_mappable_candidate` means only that no blocking mechanical compile/judge gaps were detected; it is **not** deed-correctness or closure truth.
- If you cannot save a draft after the needed contract is visible, record the exact missing blocker instead of another broad hydrate.
- `submit_ir_for_mapping` is the deliberate mapping attempt from a selected draft IR.
- `publish_deed_to_ir_output` is final scoped handoff only.

## Work inventory means downstream deed-to-IR responsibilities
- Inventory **deed-to-IR responsibilities**, not transcript-edit atoms or covered units.
- Do **not** copy inherited covered units into local covered units just to look complete.
- Local work items should track downstream obligations such as:
  - author Parcel 1 IR
  - represent Parcel 2 as blocked/partial scope
  - encode governing range decision in IR/provenance
  - submit IR for mapping
  - inspect map/compile/judge artifacts
  - repair IR when mapping exposes a real defect
  - publish final output
- Inherited upstream values are **starting inputs**, not blind truth. If mapping/compile/judge exposes a real defect, self-heal by correcting IR and provenance — do not silently trust transcript-edit when earned evidence contradicts it.

## Foundation workflow (bound)
- Bound tool contracts live in tool specs — treat those as authoritative; this guidance does not duplicate exact tool IDs or request shapes.
- Typical flow: hydrate upstream inputs and feature-graph capabilities; persist agent-authored IR; submit saved IR for mapping when ready; inspect returned mapping, compile, judge, and sidecar artifacts through bounded listing and hydration.
- Attach exact upstream links through `ProvenanceAttachment.source_entity_links` when authoring IR nodes/edges.
- Do not guess schema, operation parameters, units, operand shapes, support status, or provenance contracts. Hydrate capability details in the same orientation batch before the first non-trivial IR save when details are not already in context.

## What not to do
- Do not rebuild transcript-edit's resolution graph as local deed-to-IR inventory.
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
