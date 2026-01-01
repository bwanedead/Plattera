# Retrieval Vision: Evidence-First Hybrid Retrieval for Plattera

## Purpose

`backend/retrieval/` is Plattera’s **evidence factory**.

Given a user question (or an agent goal), retrieval produces a set of **EvidenceCards** that the agent can:
- cite,
- reason over,
- and use to assemble correct outputs.

Retrieval does *not* own storage truth. It consumes Corpus.

---

## Core stance

Plattera has two kinds of “knowledge” living side-by-side:

1. **Fuzzy semantic text**
   - transcripts, drafts, narrative descriptions
   - best found by semantic similarity / embeddings
   - good for *finding the neighborhood*

2. **Structured provenance (explicit relationships)**
   - lineage: transcript → final → schema → polygon → georef → validation outputs
   - best found by deterministic traversal
   - good for *what is true / canonical*

**Embeddings are a lane, not the strategy.**
Provenance traversal carries correctness when scale grows and semantic neighborhoods get mushy.

---

## Unifying currency: Evidence

All retrieval lanes must converge into the same output shape:

- `EvidenceSpan`: a citeable snippet tied to a `CorpusEntryRef` (+ optional chunk offsets)
- `EvidenceCard`: a ranked “unit of evidence” with provenance and score
- `RetrievalResult`: the full set of evidence cards + debug diagnostics

This makes retrieval **pivot-friendly**:
- lanes can be added/removed/upgraded without changing the agent loop API.

---

## Module boundaries

### Corpus (substrate)
Corpus answers:
- “What content exists?”
- “How do I hydrate it into a consistent shape?”

Corpus does **not** embed, search, or rank.

Retrieval should only touch corpus through `CorpusProvider` (today: `VirtualCorpusProvider`).

### Retrieval (lanes + engine)
Retrieval owns:
- search strategies (“lanes”),
- merging/deduping,
- scoring and ranking into EvidenceCards,
- debug outputs and diagnostics.

Retrieval should not reach into dossiers/artifacts directly.

---

## Lanes (plural, intentional)

Retrieval is multi-lane by design.

Typical lanes:
- **Lexical lane**
  - exact substring / keyword search
  - cheap, precise when you know the wording
- **Semantic lane**
  - embeddings + vector store
  - best for vague queries / “meaning”
- **Rerank lane**
  - expensive “zoom lens” that improves ordering of candidates
- **Provenance lane (graph / deterministic)**
  - given an anchor (often a dossier), assemble the canonical artifact bundle:
    finalized text, latest schema, latest georef, validation summary, and lineage pointers

Important: “Hybrid” does NOT mean “run everything every time.”
Hybrid means:
- choose the lane(s) appropriate to the query,
- layer lanes when needed (semantic → provenance is a common pattern).

---

## Engine responsibilities

`RetrievalEngine` is the orchestrator that:
1. Accepts a query + filters + requested lanes.
2. Invokes lanes to produce candidate EvidenceCards.
3. Merges + dedupes + sorts (and optionally reranks).
4. Returns a stable `RetrievalResult` with debug info.

The engine’s contract should remain stable even as implementations evolve.

---

## Build order (sanity-first)

1. **Provenance lane first**
   - deterministic correctness
   - uses existing identity + lineage already present in Plattera
2. **Lexical lane**
   - cheap anchor discovery (“find dossier mentioning X”)
3. **Semantic lane**
   - embeddings become a high-value finder, not a single point of failure
4. **Reranking**
   - only once candidate density becomes a real problem

---

## Acceptance test (north-star)

Retrieval is “working” when it can do this reliably:

Given a vague question:
1. locate the correct dossier region (lexical or semantic),
2. then deterministically assemble the canonical artifact bundle (provenance),
3. return it as EvidenceCards with clear provenance and citeable spans.

Embeddings help you find the neighborhood.
Provenance tells you what’s true.
Evidence is what the system returns.
