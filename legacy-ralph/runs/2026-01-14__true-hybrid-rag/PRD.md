# PRD: True Hybrid Retrieval (Fusion + Rerank + Maintenance Controller)

## Context
The retrieval stack already has lexical and semantic lanes, but the existing `"hybrid"` path is lexical → provenance anchoring, not lexical + semantic fusion. We need a true hybrid candidate pool so downstream agent loops can treat retrieval as dependable, while preserving retrieve-vs-read separation and lane purity.

## Goal
Add a deterministic, evidence-preserving fusion lane (lexical + semantic), optional rerank integration, and a small maintenance controller that orchestrates existing primitives without hidden rebuilds.

## Non-goals
- Do not change the semantics of the existing `"hybrid"` lane (lexical → provenance).
- Do not add BM25/FTS or new external dependencies.
- Do not implement agent-loop orchestration or UI triggers.
- Do not auto-rebuild indexes on query paths.

## Users / Use cases
- As an agent/orchestrator, I want a single candidate list from lexical + semantic so I can reason over evidence consistently.
- As an operator, I want an explicit maintenance controller that can rebuild or compact indexes without manual file fiddling.
- As a developer, I want rerank to be optional and bounded so retrieval remains fast by default.

## Scope
- `backend/retrieval/engine/` (fusion policy, rerank hook, maintenance controller)
- `backend/retrieval/tools/` (new tool wrapper for fusion)
- `backend/retrieval/lanes/rerank/` (wire existing lane)
- `backend/retrieval/lanes/lexical/` (v0+ scoring heuristics)
- Tests in `backend/retrieval/engine/`, `backend/retrieval/tools/`, `backend/retrieval/lanes/lexical/`

## Constraints / invariants
- Evidence shape stays `EvidenceCard`/`EvidenceSpan`; no breaking schema changes.
- Retrieve vs read separation stays intact; rerank must use previews or bounded read-service calls only.
- Lanes remain pure; orchestration stays in the engine.
- Maintenance controller is never invoked from `RetrievalEngine.search()`; it must be called explicitly.
- Deterministic ordering and debug output must be preserved.
- Minimal diffs; no repo restructuring.

## Success criteria
- `RetrievalEngine.search(... lanes=["hybrid_semantic"])` returns a unified candidate list from lexical raw + normalized + semantic.
- Fusion results are deterministic, deduped by `EvidenceCard.id`, and include lane-specific provenance in debug.
- Rerank can be enabled explicitly and reorders candidates without breaking evidence contracts.
- Maintenance controller can detect missing/stale indexes and recommend or run rebuild/compact actions explicitly.
- Lexical lane adds lightweight scoring heuristics with tests for ordering/density.

## Edge cases
- Empty query returns no cards with clear debug notes.
- Semantic lane unavailable or missing index yields graceful fallback.
- Filters (view, dossier_id) still apply to fusion.
- Duplicate cards across lanes dedupe correctly.
- Rerank disabled does not alter ordering or scores.

## Implementation notes (optional)
- Add a new lane name (e.g., `"hybrid_semantic"`) and keep `"hybrid"` behavior unchanged.
- Prefer a fusion helper in `engine/merge.py` for per-lane caps and deterministic ordering.
- Use `EvidenceCard.provenance["sources"]` only if multi-source per-card is needed (additive, non-breaking).
- Deterministic ordering policy: take per-lane top-K in fixed order (lexical.raw, lexical.normalized, semantic), concatenate, dedupe by `card.id` (first wins), then sort by score with stable tie-breaker (lane order + card.id).

