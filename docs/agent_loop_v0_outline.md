## Plattera Agent Loop v0 Outline

### North Star

Turn a finalized dossier into a schema that **compiles + validates**, by running a bounded loop that can **detect what’s missing**, **retrieve supporting evidence from the user’s corpus**, and **patch** until success or a clear “needs user input” outcome.

---

## Reef Map: the main v0 pillars

### 1) Corpus Layer (what exists + what’s allowed)

Everything the system can draw from (in-corpus only), exposed as **views/channels**:

* **Finalized High-Signal View**

  * finalized stitched dossier text (canonical)
  * user final selections per segment
  * “best known” artifacts (schemas/georefs) when they exist

* **Everything View**

  * all transcriptions (raw, redundancy variants, consensus, edits)
  * unfinalized/incomplete dossiers
  * job outputs/history (optional)

* **Artifact View**

  * schemas (with outcomes/metrics if known)
  * georefs + validator results
  * case library entries (pattern → fragment → success/failure) (optional in v0)

Key idea: one universe of items, multiple views for higher-signal routing.

---

### 2) RAG Layer (how retrieval works)

The pipeline that makes the corpus searchable and returns grounded evidence.

Conceptual subparts:

* **Ingest/Index** (chunk + metadata + lexical + embeddings)
* **Query Builder** (gap → query pack + filters)
* **Retrievers** (lexical + vector + artifact search)
* **Rerank/Verify** (ensure candidates actually contain the missing element)
* **Evidence Packaging** (compact, citeable evidence objects)

Output: `EvidenceSet` — not just text, but source pointers + spans + confidence.

---

### 3) Compile Contract (what “success” means)

A stable interface between “schema” and your deterministic mapping engine.

At a high level the schema must provide:

* **Local geometry** sufficient to produce a polygon (courses/vertices)
* **Anchor** sufficient to georeference (PLSS + optional tie-to-corner)
* **Exceptions/dependencies** representable as imports, carveouts, or unresolved flags

This contract is the invariant; vocabulary/macros can evolve as long as they reduce to it.

---

### 4) Deterministic Judge (compiler + validator)

Existing Plattera pipelines act as the truth test:

* schema → local polygon (closure/sanity)
* schema PLSS + tie → POB resolution (tie vs centroid fallback)
* local polygon + POB → geographic polygon (geodesic)
* validator → diagnostics (reasonable location, precision, closure)

Produces a normalized `CompileReport`.

---

### 5) Gap Detector (turn failures into needs)

Takes:

* schema attempt
* CompileReport
* source text spans

Outputs:

* `GapList[]` with typed needs (missing anchor, non-closure, exception unresolved, dependency missing/ambiguous, tie parse failure, centroid fallback, etc.)

This is how the system knows *what to retrieve*.

---

### 6) Patch / Synthesis Layer (evidence → schema change)

Given a gap + evidence:

* fill missing anchor fields
* repair/add boundary calls
* import exception definitions / carveouts (materialize or reference)
* resolve dependency edges (or mark ambiguous/missing)
* annotate schema with citations + confidence

Key rule: patches must be grounded (evidence-linked) and contract-compilable.

---

### 7) Orchestrator (the loop controller)

A bounded controller that runs:

1. Draft schema
2. Compile + validate
3. Detect gaps
4. Retrieve evidence
5. Patch
6. Repeat

Owns:

* iteration limits / budgets
* stop conditions
* outcome classification:

  * **SUCCESS**
  * **PARTIAL (local-only / centroid-anchored)**
  * **NEEDS_UPLOAD**
  * **NEEDS_USER_CHOICE**
  * **FAILED (budget exceeded)**

---

### 8) Memory / Hardening Layer (optional v0, core v1)

A compounding store of “what worked”:

* successful fragments + triggers
* failure modes + fixes
* ranked priors for future retrieval/patching

You can ship v0 without it, but it’s the path to “holy shit”.

---

## The minimal v0 loop behavior (one paragraph)

Start with the finalized dossier as canonical input. Generate a schema draft. Run it through the deterministic mapping judge to get a compile report. Convert that report into a small set of typed gaps. For each gap, use RAG over the corpus views (finalized first, then everything, plus artifacts) to retrieve grounded evidence. Apply the smallest patch that addresses the gaps while staying within the compile contract. Iterate until validation passes, or the system can clearly explain what is missing/ambiguous and what the user must provide next.

---

## The one mental sentence to hold it all

**Corpus defines what exists; RAG finds what matters; Contract defines “done”; Judge scores reality; Gaps define questions; Patches change schema; Orchestrator loops; Memory makes it compound.**
