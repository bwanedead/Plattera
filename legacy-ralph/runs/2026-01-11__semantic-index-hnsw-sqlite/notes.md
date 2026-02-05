# Notes — Brain dump (semantic indexing runway)

This file is intentionally redundant and long. It exists so the Ralph loop has durable context without relying on chat memory.

## Brief summary
- Build persistent local semantic retrieval: embed corpus chunks, persist vectors + ANN index, retrieve nearest chunks quickly across sessions.
- Use HNSW via `hnswlib` + SQLite metadata mapping.
- Start with `CorpusView.FINAL_SEGMENTS` (truth pool).
- Lifecycle: append for new content; replace-slice per dossier/view for mutations.
- Keep `chunk_id` as external ID; use internal HNSW int labels behind a SQLite mapping.
- Use cosine-equivalent similarity (normalize vectors; dot/inner product).
- Persist index artifacts under the app’s asset roots with a manifest for mismatch detection.

## Full “brain-dump brief” (source)

Plattera Semantic Indexing Runway Brief

Status: Chunking + local embeddings provider exist. Next is persistent vector index + indexing pipeline + semantic retrieval hits.

1) What we’re building (high-level)

We are turning the semantic lane from:
- “I can embed a query locally”
into
- “I can embed the corpus chunks, persist them, and retrieve nearest chunks quickly, locally, across sessions.”

That requires:
1. Index builder pipeline: enumerate → hydrate → chunk → embed → write
2. Persistent vector store: vectors + ANN index structure + query API
3. Metadata mapping: vector hit → CorpusEntryRef + selector → EvidenceCard
4. Lifecycle triggers: append new stuff; replace-slice when existing content changes

2) Vocabulary and mental model (no ambiguity)

Definitions
- Vector: an embedding of a text chunk (a fixed-length float array).
- Similarity metric: dot product on normalized vectors (cosine similarity effectively).
- ANN index (HNSW): a graph-based data structure built over vectors so we don’t compare a query vector to every stored vector.
- Vector store: component that persists vectors + index and answers “top K nearest.”
- Index builder: job that produces vectors and inserts them into the vector store + metadata store.

Where things live (explicit)
- Vectors + HNSW graph live in the hnswlib index file (persisted to disk).
- Metadata lives in a separate store (recommended: SQLite).

At query time:
1) embed query →
2) HNSW search returns labels + scores →
3) labels map to chunk_id / metadata →
4) metadata maps to CorpusEntryRef + selector →
5) build EvidenceCards

3) What we decided

We chose: HNSW graph ANN via hnswlib
- headroom to ~100k chunks, CPU-only, local
- embedded/self-contained
- supports incremental adds + “live product” feel

We explicitly do NOT want:
- re-embed everything each session
- heavy always-on services
- anything that phones home

4) Why replace-slice per dossier/view still exists

Append handles new eligible content.
Replace-slice is required for correctness when content mutates:
- final selection flips to a different draft
- a draft is edited after being final-selected
- a transcript is deleted
- chunking policy changes
- embedding model revision changes

Implementation detail:
- Use hnswlib mark_deleted for tombstones, then add new labels/vectors.
- Defer compaction until needed.

5) What we’re vectorizing (scope)

Pool strategy
- Pool A / Truth pool: CorpusView.FINAL_SEGMENTS

Chunk text
- Use structured_json.sections boundaries when present, else fallback chunking from entry.text.

Similarity metric choice
- Normalize vectors and use dot product (cosine-equivalent).

6) System components to implement next

A) Vector Store Implementation (replace NoopVectorStore)
- New: HnswVectorStore implementing VectorStore protocol.
- Add, knn_query, mark_deleted, save/load.
- Explicit config: M, ef_construction, ef.

B) Metadata Store (SQLite)
- New: VectorMetadataStore mapping label ↔ chunk_id and storing chunk metadata:
  - CorpusEntryRef fields, selector JSON, content_hash, policy_id, model revision, embedding_dim, timestamps.
  - Queries: get labels for dossier/view (replace-slice), get metadata by label (evidence build).

C) Index Builder Pipeline
- New: SemanticIndexBuilder:
  - enumerate refs → hydrate → chunk → embed → assign labels → write vectors → write metadata
  - modes: append-only vs replace-slice

D) Semantic Lane Query → Hits → EvidenceCards
- embed query → vector store top K → fetch metadata → build EvidenceCards including score.

7) Storage layout

Store artifacts under a deterministic assets directory, per pool:
- hnsw index file
- metadata sqlite
- manifest.json

Manifest fields:
- embedding_dim
- embedding model revision/hash
- chunking policy_id
- metadata schema version
- timestamps

If manifest mismatch: surface stale status and require explicit reindex (no silent rebuild on query).

8) Definition of Done
- Index FINAL_SEGMENTS for a dossier
- Restart app and query semantic lane → real hits (EvidenceCards)
- Append new final-selected segment and index it → searchable
- Change truth content and replace-slice → stale hits disappear
- All local-only, deterministic, explicit debug traces

9) Deliberately deferred
- reranking
- hybrid fusion
- artifact pool indexing
- compaction job
- full evaluation harness


