# PRD: Yellow Zone Audit and Final Hardening

## Context
Following the successful completion of the semantic-index-polish run (S1-S8), we have a production-ready semantic retrieval system. A "yellow zone cloud" brief was provided identifying 10 critical correctness/invariants/ops clarity points that should be verified before building the next layers (hybrid fusion, reranking, agent loop).

Initial sanity check revealed that **8 out of 10 points are already complete** from the previous run. However, we need to:
1. Formally audit all 10 points against the current implementation
2. Document or address any remaining gaps (primarily: model identity semantics and tombstone compaction strategy)
3. Ensure all invariants are explicitly documented for future maintainers

## Goal
Verify that all 10 "yellow zone" correctness points are satisfied in the current implementation, and document/address any gaps to ensure a solid foundation for the next development phase.

## Non-goals
- Implementing new features beyond the yellow zone scope
- Changing existing working implementations unnecessarily
- Implementing tombstone compaction itself (only documenting the strategy)
- Hybrid fusion, reranking, or agent loop work (future phase)

## Users / Use cases
- As a developer, I need confidence that all 10 yellow-zone invariants are satisfied before building on this foundation
- As an operator, I need clear documentation of model identity semantics and compaction strategy
- As a future maintainer, I need explicit documentation of design decisions and operational strategies

## Scope
- Backend retrieval system:
  - `backend/retrieval/lanes/semantic/` (primary focus)
  - `backend/retrieval/read_service.py`
  - `backend/corpus/` (hydration contracts)
- Documentation:
  - Local `agents.md` files in relevant directories
  - Inline code documentation where helpful

## Constraints / invariants
- Do not modify working implementations unless addressing a genuine gap
- Preserve all ethos principles (evidence-first, deterministic, safe failure modes)
- Documentation must be concise and factual, not verbose
- Any code changes must maintain backward compatibility
- All existing tests must continue to pass

## Success criteria
- All 10 yellow-zone points are either verified complete or explicitly addressed
- Model identity semantics are documented with clear rationale
- Tombstone compaction strategy is documented with clear triggers/conditions
- Audit findings are recorded in a durable artifact
- All existing tests pass (`pytest backend/retrieval/lanes/semantic/`)

## Edge cases
- Point may be "complete" but lack explicit documentation (document it)
- Point may be "partially complete" (identify gap and address minimally)
- Multiple points may share a solution (consolidate documentation)

## Implementation notes
The 10 yellow-zone points to audit:
1. Retrieval-time evidence should be readable (preview excerpts)
2. Retrieval vs reading separation explicit and clean
3. Manifest must be "truth" (written by builder)
4. Model identity semantics consistent (no false staleness)
5. Index load failure modes operationally unambiguous
6. Update semantics provably safe and deterministic
7. Tombstones acceptable short-term, cleanup strategy needed
8. HNSW tests reliable and not silently skipped
9. Hydration fidelity for FINAL_SEGMENTS complete
10. "Why this matched" trace standardized and stable
