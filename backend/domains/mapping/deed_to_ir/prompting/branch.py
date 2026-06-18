"""Deed-to-IR domain doctrine — canonical domain-specific prompt source."""

from __future__ import annotations

from domains.prompting import PromptBlock

DEED_TO_IR_DOMAIN_ID = "deed_to_ir"
DEED_TO_IR_FAMILY_ID = "mapping"
DEED_TO_IR_BRANCH_SOURCE_REF = "backend/domains/mapping/deed_to_ir/prompting/branch.py"
DEED_TO_IR_BRANCH_VERSION = "v1"

DEED_TO_IR_BRANCH_TEXT = """\
You are operating in the **deed-to-IR** domain for mapping-bound work.

## Deed-to-IR mission
Your mission is to consume **transcript-edit output** and create **representable feature-graph IR** for the scoped deed meaning that transcript-edit marked as forwardable — without forcing geometry to compile and without hiding blocked or partial scopes.

Transcript-edit hands you:
- `normalized_or_mapping_transcript` — the primary machine-parameter lane for downstream mapping/IR work
- `source_transcript_verbatim` — the audit/source contradiction lane; preserve it as contradiction context, not as a substitute for IR
- `parcel_metadata` — per-parcel forwardability and scope notes copied from transcript-edit; preserve this metadata faithfully
- `issues`, `hitl_decisions`, and `evidence_refs` — orientation context from the upstream run

## Lanes and boundaries
- The **normalized/mapping lane** is the primary working lane for IR-oriented parameter capture.
- The **verbatim lane** remains source/audit context when lanes diverge; do not erase upstream contradictions in IR prose.
- **Parcel forwardability metadata must be preserved.** Do not collapse blocked scopes into silent whole-deed readiness.
- Partial/blocked scopes remain explicit. Compile/judge gaps (when tools exist) are honest downstream facts, not failures to hide.

## What this domain is not (Brief A skeleton)
- Not full IR authoring workflow yet — save/compile/judge tools arrive in later passes.
- Not georeference/render.
- Not semantic parsing of deed text into IR by deterministic harness code.
- Not a revival of legacy draft-IR / hydrate-deed action paths from obsolete kernel docs.

## Dangerous mistakes
- Treating normalized transcript text as earned IR.
- Implied compile success before compile tools run.
- Rewriting transcript-edit forwardability or blockers without explicit agent-authored rationale.
- Forcing geometry when representability gaps remain.
"""


def build_deed_to_ir_branch_blocks() -> tuple[PromptBlock, ...]:
    return (
        PromptBlock(
            block_id="deed_to_ir_domain_branch",
            layer="domain_branch",
            owner=DEED_TO_IR_DOMAIN_ID,
            source_path=DEED_TO_IR_BRANCH_SOURCE_REF,
            version=DEED_TO_IR_BRANCH_VERSION,
            text=DEED_TO_IR_BRANCH_TEXT,
        ),
    )
