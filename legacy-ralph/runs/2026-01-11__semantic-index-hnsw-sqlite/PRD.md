# PRD: Semantic Index Backbone — HNSW + SQLite (FINAL_SEGMENTS)

## Context
We already have deterministic chunking and a local embeddings provider. The missing backbone is a persistent local vector index that can be built once, saved to disk, loaded across app restarts, and queried to return EvidenceCards pointing back into the Corpus.

We will start with a single semantic pool:
- `CorpusView.FINAL_SEGMENTS` (the “truth” pool)

## Goal
Enable persistent, local-only semantic retrieval over `FINAL_SEGMENTS` that returns real EvidenceCards with correct `CorpusEntryRef` + selector, and supports append + replace-slice lifecycle.

## Non-goals
- Reranking (cross-encoder / LLM rerank).
- Hybrid fusion (RRF / dedupe / cross-lane orchestration changes).
- Indexing other pools (schema/georef artifacts) or multi-index federation.
- Compaction/rebuild job for tombstones (deferred).
- UI work; this milestone is backend retrieval/indexing only.

## Users / Use cases
- As a user, I want to ask a question and get semantically relevant evidence from final-selected content.
- As a developer, I want indexing to be deterministic, inspectable, and stable across restarts.
- As the system, when a dossier’s truth content changes, I want stale vectors to disappear (replace-slice) so retrieval stays correct.

## Scope
- Backend only:
  - `backend/retrieval/lanes/semantic/` (vector store + semantic lane wiring)
  - `backend/corpus/` (views/refs/entry hydration already exist; index builder consumes them)
  - Local artifact storage under the existing assets roots (no new always-on services).

## Constraints / invariants
- Local-only (no network service requirement for the index itself).
- Deterministic:
  - chunk IDs must remain stable given the same source + policy.
  - index artifacts must be reproducible and explainable (manifest).
- Correctness-first lifecycle:
  - append for brand new eligible content
  - replace-slice per dossier/view for mutations (tombstone old labels, add new)
- Do not leak HNSW integer labels into the semantic lane’s public API:
  - public IDs remain `chunk_id` strings
  - label mapping is an internal/persistence detail
- Failure modes must be explicit and safe (no mystery rebuilds on query):
  - manifest mismatch should surface as “stale / needs reindex”
  - corrupted/missing artifacts should yield an explicit reason, not a crash

## Success criteria
Objective checks proving the feature works:
- Build an index for `CorpusView.FINAL_SEGMENTS` for a dossier, save it, restart, load it, and query it; results are consistent.
- Semantic lane query returns real EvidenceCards (with correct ref + selector) from the persistent index.
- Append: add a new final-selected segment, index it, and it becomes searchable.
- Replace-slice: change truth content for a dossier/view, reindex slice, and stale hits no longer appear.
- Manifest mismatch is detected and surfaced as “stale index / needs reindex” (no silent auto-rebuild on query).

## Edge cases
- Empty index (no eligible FINAL segments) returns an explicit “no evidence” result, not an exception.
- Missing metadata row for a returned label is handled safely and logged (and the hit is skipped).
- Corrupted index file / unreadable sqlite DB yields an explicit “index unavailable” reason.
- Tombstoned labels do not surface as hits (and are auditable in metadata).
- Embedding dim/model revision or chunk policy mismatch triggers a stale index status.

## Implementation notes (optional)
- ANN backend: HNSW (`hnswlib==0.8.0` already pinned).
- Metadata store: SQLite mapping:
  - external ID: `chunk_id` (string)
  - internal ID: `label` (int64)
- Similarity metric: cosine-equivalent (normalize vectors + dot product / inner product).
- Store artifacts under existing asset roots (consistent with Windows packaging expectations).


