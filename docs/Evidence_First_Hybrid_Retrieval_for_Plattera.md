Evidence First: Hybrid Retrieval for Plattera

This document captures the guiding framing for Plattera’s retrieval system, with a bias toward long-term sanity, pivot-friendliness, and correctness under scale.

The core idea

Plattera has two fundamentally different kinds of “knowledge” living side-by-side:

One kind is fuzzy semantic text, where we often do not know the exact words we’re looking for. This includes transcripts, drafts, finalized narrative text, and other natural language that benefits from semantic similarity.

The other kind is structured provenance, where the relationships are explicit and correctness matters more than “semantic closeness.” This includes things like: which transcript produced which final, which final produced which schema, which schema produced which polygon, which polygon produced which georeference, and what validator outputs were produced. This is already graph-like.

The mistake is treating embeddings as the entire retrieval strategy. Embeddings are useful, but they should be one lane in a broader system.

So the “highest” retrieval stance is:

Embeddings are for fuzzy entry points. Provenance traversal is for correctness.

Why this matters

At small scale, a simple vector search often feels magical. At larger scale, many chunks become “close enough,” and retrieval can get mushy. This doesn’t mean nearest-neighbor search is broken; it means we shouldn’t build a system that depends on it being perfect.

Plattera has a natural advantage: it already contains stable identity and lineage. Instead of trying to brute-force everything through semantic similarity, we can use semantic retrieval to find the right region, then use explicit provenance relationships to pull the correct evidence.

That makes the system more reliable, more explainable, and less sensitive to “semantic collapse” dynamics.

Architecture stance

The retrieval system should be designed around a single unifying currency:

Evidence is the common output, regardless of how it was found.

We want multiple retrieval lanes (lexical, semantic, rerank, provenance/graph), but they must converge into a consistent evidence shape so the agent loop and API don’t care how the evidence was retrieved.

This preserves degrees of freedom. You can add, remove, or upgrade retrieval methods without rewriting the agent loop.

The three retrieval layers
One: Corpus as substrate

Corpus is a read-oriented projection of Plattera’s source-of-truth datastore. It answers:

“What content exists, and how do I hydrate it into a consistent shape?”

Corpus does not embed, search, or rank. It only enumerates and hydrates.

This lets us evolve storage (virtual now → materialized later) without destabilizing retrieval semantics.

Two: Retrieval as multi-lane evidence production

Retrieval is a multi-lane system that consumes Corpus and outputs EvidenceCards. Lanes can include:

Lexical search for exact string / keyword hits.

Semantic search for fuzzy meaning-based discovery.

Reranking to sharpen results when candidate neighborhoods are dense.

Provenance/graph retrieval for deterministic “give me the connected artifacts and lineage.”

The key is that every lane produces comparable evidence objects so downstream systems stay stable.

Three: Provenance as navigation fabric

Plattera’s “graph retrieval” is not some exotic next-gen technique; it’s simply formalizing what is already true in the product.

Given an anchor entity (often a dossier or schema), provenance retrieval should deterministically assemble the canonical bundle:

finalized narrative text, latest schema, latest georeference, validation summary, and relevant lineage pointers.

This lane is robust because it does not depend on similarity. It depends on explicit relationships.

What “hybrid” means in Plattera

Hybrid does not mean “always run everything for every query.”

Hybrid means:

Use the right lane for the job, and allow layering when needed.

Semantic search is often a good first step when you don’t know where you are.

Provenance traversal is the right second step once you’ve found the right anchor.

Reranking is the “zoom lens” that resolves ambiguity when many candidates are near each other.

Lexical search is cheap and precise when you know the word or phrase.

The system becomes “magical” because the agent handles these choices, not because there’s only one entry door.

Development strategy

This framing implies a sane build order:

First, make a vertical slice where provenance retrieval is strong and deterministic, because Plattera’s correctness-heavy artifacts live here.

Second, add lexical retrieval over the virtual corpus to reliably locate anchors via keywords.

Third, add semantic embeddings later, once the rest of the evidence and provenance pathway is proven, so semantic search becomes a high-value “finder” rather than a single point of failure.

Reranking and hierarchical retrieval remain future upgrades, but the interfaces should allow them from day one.

The main acceptance test

Plattera retrieval is succeeding when it can do this reliably:

Given a vague question, it can locate the correct dossier region, then assemble the exact canonical artifact bundle with strong provenance and show it as evidence.

If embeddings degrade at scale, Plattera still works because the provenance lane carries the correctness workload.

North star

Embeddings help you find the neighborhood. Provenance tells you what’s true. Evidence is what the system returns.