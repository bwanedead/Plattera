# Corpus module vision (Virtual → Materialized)

## Purpose

`backend/corpus/` is the **read-model** / **document projection** layer over Plattera’s existing file-backed datastore (`dossiers_data/`).

The dossier store is optimized for **workflow truth** (drafts, heads, edits, final selection, provenance, artifacts, job history). Retrieval and agents need a different surface: a stable concept of **documents** with **text payloads**, **metadata**, and **references** back into the dossier system.

This module exists to answer:

- “What searchable documents exist in this workspace?”
- “Given a doc reference, what is its current text payload (and provenance)?”
- “How do we present multiple corpus views (finalized-only vs everything vs artifacts) consistently?”

`corpus/` should remain generic and agent-agnostic. Agents and retrieval lanes consume it, but it does not embed agent logic.

---

## Two modes: Virtual corpus vs Materialized corpus

### Mode A — Virtual corpus (v0 / initial implementation)

In v0, the corpus is **virtual**:

- We do **not** store duplicate copies of documents.
- Documents are enumerated as lightweight references (`CorpusDocRef`) backed by the existing dossier filesystem.
- Text is loaded on demand via `hydrate(doc_ref)`.

This keeps early development simple and avoids committing too early to:
- document identity/version rules
- invalidation/rebuild policies
- second-datastore migration/cleanup semantics

In virtual mode, retrieval may still maintain its own index structures (semantic embeddings, lexical indexes), but those indexes should reference `CorpusDocRef` + a version identifier (see below).

---

### Mode B — Materialized corpus (future target)

Ultimately, we want a **materialized corpus** for performance and determinism:

- Persist normalized text snapshots and chunk maps into a dedicated corpus store.
- Retrieval can serve evidence/snippets without reading dossier files at query time.
- Supports stable provenance and reproducible “what the agent saw” behavior.

Materialized corpus unlocks:
- faster query-time access (no dossier hydration fan-out)
- stable snippet offsets and chunk boundaries
- reliable hybrid retrieval (BM25 + embeddings + rerank) with consistent doc versions
- auditable/replayable agent citations (why did it cite this?)

Materialization is not required for correctness, but becomes important for “holy shit” responsiveness, stability, and scale.

---

## Bridging strategy (Virtual-first, but version-aware)

To ensure a smooth migration from virtual → materialized, we adopt this invariant early:

**Every hydrated document produces a `content_hash` (doc version id).**

When `hydrate(doc_ref)` returns a document payload, it also returns:

- `doc_id`: stable identity (derived from dossier/transcription/artifact identity)
- `content_hash`: hash of the hydrated text payload (version identity)
- optional: `source_refs` (where it came from)

Retrieval indexes should store `(doc_id, content_hash, chunk_id, offsets, metadata)`.

This prevents stale-index bugs and makes materialization a mechanical upgrade:
materialized storage can simply persist snapshots keyed by `(doc_id, content_hash)`.

---

## Corpus “views”

The corpus supports multiple views, each of which enumerates `CorpusDocRef`s and provides consistent metadata.

Examples:
- `finalized`: high-signal, context-aware documents (final stitched dossier text)
- `everything`: includes non-finalized transcriptions/drafts for broader recall
- `artifacts`: schemas, georefs, and other derived artifacts (often useful as retrieval targets)

Views should remain composable. Retrieval and agents can select views explicitly.

---

## Boundaries & responsibilities

### corpus/ is responsible for:
- defining document identity and references (`CorpusDocRef`, etc.)
- enumerating documents per view
- hydrating text and metadata reliably from existing storage
- computing `content_hash` for hydrated content
- providing stable doc metadata filters (state, county, TRS, dates, etc. if available)

### corpus/ is NOT responsible for:
- embeddings or vector database details (lives in `backend/retrieval/`)
- lexical search implementations (lives in `backend/retrieval/`)
- reranking models (lives in `backend/retrieval/`)
- agent orchestration or planning logic (lives in `backend/agents/`)
- workflow truth mutation (remains in `backend/services/` and `dossiers_data/`)

---

## Migration to materialized corpus (future outline)

When we flip to materialized mode, we add:
- a corpus store location under dev/frozen-safe roots (similar to PLSS approach)
- a materializer job that writes `(doc_id, content_hash) → snapshot + chunk map`
- an invalidation/rebuild policy driven by dossier events (finalize/edit/schema update)
- optional caching layers to keep rebuilds incremental

But the public interface to retrieval/agents should remain stable:
`list_docs(view, filters)` + `hydrate(doc_ref)` and (later) `fetch_snapshot(doc_id, content_hash)`.

---

## Design ethos

- **Keep workflow truth separate from query truth.**
  The dossier store remains the authoritative workflow record. Corpus is the query surface.

- **Stay generic and extensible.**
  Corpus is reusable for other agent loops, not just schema mapping.

- **Be version-aware from day one.**
  `content_hash` prevents stale citations and makes the virtual→materialized transition safe.

- **Prefer mechanical upgrades.**
  The future migration should be an implementation swap, not a redesign.
