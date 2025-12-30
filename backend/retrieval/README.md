# `backend/retrieval/`

This package is Plattera’s **shared retrieval engine**.

It provides:

- **Evidence objects** (`EvidenceCard`, `EvidenceSpan`) with consistent provenance/citations
- **Filters** for scoping queries (dossier, view, date ranges, etc.)
- **Retrieval lanes** (lexical, semantic, hybrid merge, optional rerank)
- A single **engine** that runs lanes and merges/dedupes results

## Design promises

- Every lane returns the **same evidence shapes**.
- Callers never depend on lane internals (BM25 vs grep vs embeddings).
- The retrieval system is not bound to any one agent loop.


