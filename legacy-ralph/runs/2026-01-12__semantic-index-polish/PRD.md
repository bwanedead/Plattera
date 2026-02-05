# PRD: Semantic Index Polish — Readable Hits, Deterministic Read, Truthful State

## Context
We have the correct backbone shape: deterministic chunking, local embeddings, persistent vector index + SQLite metadata, and semantic lane retrieval that can return stable pointers back into the corpus.

The remaining “yellow-zone” work is about making the system trustworthy and ergonomic under real use:
- semantic hits must be readable/evaluable (preview excerpt + “why it matched” trace)
- hit → deterministic “read mode” must work (especially for `FINAL_SEGMENTS`)
- manifest/model identity must be truthful, written by the builder, and compared correctly
- operational failure modes must be explicit (missing vs corrupt vs stale)
- update semantics must be provably safe for the ANN library
- tests must remain reliable (no “ignore the important tests” drift)

## Goal
Make semantic retrieval results triage-readable and deterministically expandable (locate→read), ensure index identity/state is truthful and compatibility-checked, make failure modes explicit, make update semantics obviously safe, and make persistence coverage reliable for CI.

## Non-goals
- Reranking and hybrid fusion policy changes.
- UI/UX changes in the frontend.
- Implementing tombstone compaction (we may document/plan it, but not ship it here).
- Changing the overall retrieval architecture shape (lane remains “locator”; read-service does heavy hydration).

## Users / Use cases
- As a developer, I want semantic hits to include a small preview and debug provenance so I can judge quality quickly and tune later.
- As the system, I want a deterministic locate→read path so a hit can be expanded to full context reliably.
- As an operator, I want clear signals for “index missing” vs “index corrupt/unavailable” vs “index stale/mismatched.”
- As CI, I want weight-bearing persistence tests that don’t destabilize the test runner.

## Scope
- Backend retrieval + corpus hydration integration points:
  - `backend/retrieval/lanes/semantic/` (lane + stores + builder + manifest)
  - `backend/corpus/` (entry hydration contracts; especially `FINAL_SEGMENTS`)
  - a small “read-mode” helper/service in `backend/retrieval/` (new module) to expand evidence to full text deterministically

## Constraints / invariants
- Semantic lane remains a **locator**: it should return light-weight evidence results without hydrating full documents on every query.
- Read-time hydration must be deterministic and use existing corpus contracts (full `CorpusEntryRef` fidelity where required).
- Manifest must be written/updated on successful builds and must reflect the index identity/configuration truthfully.
- Model identity stored must be unambiguous (human-readable model id + immutable revision/fingerprint used for compatibility).
- Failure modes must be explicit and safe:
  - “missing / not initialized” is different from “present but failed to load”
  - “stale / needs reindex” is different from “corrupt”
  - do not silently rebuild on query paths
- Update semantics must not rely on undefined ANN behavior (no risky in-place replacement assumptions).
- Tests must be deterministic and stable; if isolation is needed, it must be explicit and automated (not “ignore tests forever”).

## Success criteria
- Semantic lane returns evidence with non-empty preview/excerpt and debug trace (“why this matched”).
- A semantic hit can be deterministically expanded into full parent entry text via a read-mode service without lane-level full hydration.
- Manifest is written by the builder and compatibility checks correctly detect mismatches (and surface “stale”).
- Lane differentiates missing vs corrupt/unavailable vs stale states with actionable debug.
- Update semantics are provably safe and idempotent (re-indexing/upserting doesn’t corrupt over repeated updates).
- Persistence/ANN tests run reliably (either as part of normal suite or via an explicit isolated invocation).

## Edge cases
- Index missing: returns safe empty result + explicit reason.
- Index present but fails to load (bad sqlite / unreadable hnsw file): returns explicit “unavailable/corrupt”.
- Stale index (manifest mismatch): returns explicit “needs reindex” without rebuilding on query.
- Metadata missing for a returned label: skip hit safely and log reason.
- Replace-slice/update repeated many times does not degrade index integrity.


