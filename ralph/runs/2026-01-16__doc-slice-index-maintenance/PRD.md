# PRD: Doc-Level Index Maintenance + Draft-Aware Identity (FINAL first)

## Context
We have hardened semantic indexing primitives (manifest/fingerprint/schema mismatch/compaction) but we lack an operational layer that keeps the index coherent with corpus truth in a deterministic, auditable way.

This run adds the missing “operational glue”:
**Inventory → Diagnose → Plan → Execute**

## Goal
Implement doc-slice (“entry slice”) maintenance for semantic indexes so we can detect missing/stale slices and rebuild exactly one slice deterministically, without silently burning compute.

## Non-goals
- UI implementation (badges/panels) beyond minimal backend surfaces if needed later.
- Auto-light / auto-aggressive scheduling logic (backend should be deterministic; scheduling can live in UI later).
- Full EVERYTHING pool maintenance in v0 beyond making EVERYTHING draft-aware for future expansion.

## Users / Use cases
- As the system, if a single doc changes, I want diagnose to mark exactly that doc slice stale.
- As a user, I want to see what is missing/stale and explicitly trigger heavy work.
- As an agent, I want a deterministic plan and execution log so I can iterate safely.

## Scope
Backend-first, targeting semantic retrieval/index maintenance:
- `backend/retrieval/lanes/semantic/*` (metadata + persistent store + builder integration)
- `backend/retrieval/engine/*` (maintenance controller + inventory)
- `backend/corpus/*` (draft-aware identity/hydration enabling step)

## Locked decisions / invariants
- **Slice resolution**: doc-level slices (one slice per doc artifact per pool).
- **Replace-all per slice**: tombstone all vectors for (pool, dossier_id, entry_id) then rebuild the slice.
- **Stored index identity** must include:
  - embedding model fingerprint
  - chunking policy id (or hash/version)
  - indexed signature (prefer `content_hash` of hydrated entry)
- **No silent rebuild on query path**: heavy work only via explicit maintenance execution.

## Success criteria
- If one FINAL segment doc changes, diagnose reports exactly that slice as stale (content signature changed).
- Execute rebuilds only that stale slice (delete/tombstone old labels, rebuild, update indexed state).
- Indexed state persists per slice in SQLite (missing/stale/healthy becomes cheap and deterministic).
- EVERYTHING is draft-aware at the identity level (entry_id aligns with canonical draft_id) and can hydrate head-form draft ids deterministically.

## Edge cases
- Unavailable slice (hydration failure, missing artifact, schema mismatch) is reported as `unavailable` with a reason (no crash).
- Stale identity (model/policy mismatch) is distinguishable from stale content.
- Tombstones accumulate safely; compaction remains explicit.


