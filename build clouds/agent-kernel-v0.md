## Agent Kernel v0 — Cloud Brief + Repo-Aware Review (Plattera)

### Context / why this exists
This doc captures:
- the **implementation-driving “cloud brief”** for the Agent Kernel v0 (as authored in brainstorming)
- a **repo-aware sanity check** against Plattera’s current system reality (Feature Graph IR, RAG/retrieval, semantic worker, mapping/georef)
- a few **sharp-edge notes** that prevent common implementation mismatches

Related system rebase:
- `docs/feature-graph-rag-agent-loop-technical-rebase.md`

---

## A) Brainstorm agent: Agent Kernel v0 Cloud Brief (verbatim)

Below is a **single “cloud brief”** for the **Agent Kernel v0** we’ve settled on — written to be **implementation-driving**, **repo-aligned**, and easy for your planning agent to sanity-check.

---

### 0) North-star / non-negotiables

* **Kernel is deterministic orchestration above probabilistic cognition** (LLM). The system’s correctness must not depend on “model vibes.”
* **Persistence as truth**: important state lives as durable artifacts; UI/flows hydrate from disk, not memory.
* **Evidence-first retrieval**: retrieval returns *EvidenceCards / EvidenceSpans* as the currency; provenance is correctness.
* **Deterministic judges + typed gaps**: “no silent failure”; failures are explicit, typed, routable.
* **Explicit state machine bias** (boringly correct, diagnosable).

---

## 1) What the kernel is (and is not)

### Kernel = **mechanical run harness**

Owns:

* State machine + transition rules
* Budgets + backoff
* Action execution (calls deterministic tools + LLM tools)
* Run/step logging + artifact ref bookkeeping
* Stop reasons + terminal outcomes
* Convergence / “no progress” detection (kernel-level invariant)

Does *not* own:

* Domain semantics (deed meaning, mapping rules, OCR rules, etc.)
* Ad-hoc behavior per gap type
* Any “smart” heuristics that belong in a policy plug-in

This matches repo ethos: stable scaffolding, weight-bearing layers, explicit flows.

---

## 2) Policy split (reusability boundary)

We explicitly split:

### A) **Kernel mechanics** (domain-agnostic)

Reusable for future loops (image→text, etc.).

### B) **Domain policy plug-in** (FeatureGraphDeedToMapPolicy v0)

Defines domain-specific:

* Gap taxonomy interpretation + routing table
* Readiness gates (e.g., what “READY_TO_MAP” means)
* Patch safety classes + constraints
* Retrieval “modes” (query packs / lanes / views/pools)
* Cost/benefit weights for convergence scoring

This is the “kernel + policy” boundary the planning agent called out as the key sharpening move.

---

## 3) Inputs / outputs

### KernelRequest (v0)

* `dossier_id: str`
* `policy_id: str` (e.g., `feature_graph_deed_to_map_v0`)
* `goal`:
  * `requires_global_placement: bool` (drives anchor requirements)
  * `render_required: bool = false` (optional future)
* `budgets` (kernel-level):
  * `max_steps: int`
  * `max_wall_ms: int`
  * `max_retrieval_calls: int`
  * `max_semantic_calls: int` (subset of retrieval calls allowed to use semantic lane)
  * `max_patch_calls: int` (LLM patch proposals)
* initial one-of:
  * `initial_ir_artifact_id` OR `initial_graph_json` OR `source_entry_ref`

Budgets must be first-class.

### KernelResult (v0)

* `terminal_outcome: SUCCESS | PARTIAL | NEEDS_USER_CHOICE | NEEDS_UPLOAD | FAILED`
* `stop_reason: enum` (see below)
* `run_artifact_id: str`

---

## 4) Durable artifacts (refs-not-blobs)

### RunArtifact (source of truth for the run)

* stores **refs to canonical artifacts**, not duplicated blobs (avoid ambiguity + bloat)
* minimal step summaries + digests/hashes + gap signatures
* pointers to:
  * IR artifacts
  * compile artifacts
  * judge artifacts
  * bundle artifacts (if created)
  * retrieval run artifacts
  * georef + validation artifacts (when applicable)

This matches “persistence as truth” and “artifact store is ultimate truth.”

---

## 5) State machine (minimal, explicit)

Kernel states (v0):

1. `INIT`
2. `HAVE_IR`
3. `HAVE_COMPILE` *(optional order)*
4. `HAVE_JUDGE` *(optional order)*
5. `REPAIRING` *(loop state)*
6. `READY_TO_MAP`
7. `MAPPED`
8. `DONE`

Key repo-realities:

* **Compile and Judge are separate truth streams**: compile emits best-effort geometry + gaps; judge emits deterministic validation + typed gaps.
* **Judge does not logically depend on compile**; kernel may run them in either order or in parallel from IR (kernel convention chooses sequencing).

---

## 6) Action menu (v0 “toolbox”)

Kernel executes actions; policy decides *when*.

Deterministic tool actions (existing/endorsed surfaces):

* `RETRIEVE_EVIDENCE(...)` → retrieval returns EvidenceCards/Spans
* `COMPILE(ir_ref)` → best-effort geometry + compile gaps
* `JUDGE(ir_ref)` → deterministic judge report + typed gaps
* `BUNDLE(ir_ref)` → portable dependency-closed bundle (optional)
* `GEOREFERENCE(local_geom_ref, anchor)` → low-level georef primitive
* `VALIDATE(georef_ref)` → deterministic mapping QA

LLM-mediated actions (bounded, policy-constrained):

* `PROPOSE_PATCH(patch_class, context_refs...)` → produces **new IR artifact**
* `SUMMARIZE_STATUS(...)` → produces human-facing diagnosis summary (refs + gap explanations)

---

## 7) Goal flags / metadata management (first-class)

Kernel must explicitly apply goal-required graph metadata early:

* `SET_GRAPH_REQUIREMENTS(goal)`:
  * if `goal.requires_global_placement == true`, set `graph.metadata["global_placement_required"]=true` (or equivalent)
  * avoid late “missing anchor surprise” by making this a *front-loaded invariant*

This follows the “request global placement only when needed” guidance.

---

## 8) Routing order (FeatureGraphDeedToMapPolicy v0)

Fixed priority order (policy invariant):

1. **Cheapest deterministic normalization first**
2. **Compile/Judge** (as needed to surface gaps)
3. **Targeted retrieval** to fill missing evidence/params
4. **LLM patch proposal** (only in safe classes; smallest change)
5. **User choice** if ambiguity is irreducible
6. **Upload request** if dependency missing from corpus
7. **Capability gap** if unsupported operation blocks semantics

This aligns with “iterate based on deterministic gaps” and “smallest change” posture.

---

## 9) Terminal outcomes + stop reasons

### Terminal outcomes (external-facing)

Use the repo’s classification exactly:

* `SUCCESS`: judged acceptable + (if required) georef + validate + persisted
* `PARTIAL`: local geometry exists; explicit gaps block global placement
* `NEEDS_USER_CHOICE`: ambiguity requires a selection
* `NEEDS_UPLOAD`: dependency missing from corpus
* `FAILED`: budget exceeded, contradictions, worker unavailable, internal error, etc.

### StopReason enum (internal-facing; diagnosability)

* `budget_exceeded`
* `no_progress` *(convergence exhausted)*
* `needs_user_choice`
* `needs_upload`
* `needs_capability` *(unsupported operation / missing compiler support)*
* `worker_unavailable` *(semantic lane down/backoff/port issues)*
* `validation_failed` *(georef validator rejects / bounds fail)*
* `internal_error`

**Anchor handling decision (resolved by best judgment):**

* Do **not** add a special `needs_anchor` stop reason.
* Treat anchor absence as a **typed gap** that routes to:
  * `needs_user_choice` (multiple plausible anchors) OR
  * `needs_upload` (no anchor evidence exists) OR
  * `PARTIAL` (goal doesn’t require placement)
    …and include **stop metadata** like `{gap_kind: "missing_anchor", details: ...}` rather than expanding stop enums.

This keeps stop reasons stable while letting gaps carry nuance.

---

## 10) READY_TO_MAP gate (explicit, not vibes)

`READY_TO_MAP` is true only when **concrete inputs required by deterministic georef/validate exist**, not merely because “judge passed.”

Requires (v0):

* compiled region geometry exists in an artifact form the kernel can pass/translate (or an adapter exists)
* if `requires_global_placement=true`, an anchor choice exists (or an explicit policy-approved fallback exists)
* any required fields for georef payload assembly are present (or policy routes to repair)

This matches the repo “global placement is correct when…” contract.

---

## 11) Patch safety classes (explicit constraints)

Policy restricts `PROPOSE_PATCH` to these classes:

1. **Normalization-only**
* IDs, ordering, missing defaults, metadata flags, operand shape normalization
* No semantic changes

2. **Evidence-fill**
* Fill/replace a parameter **only when backed by retrieved EvidenceSpans**
* Patch must attach provenance refs (EvidenceCard/Span IDs)

3. **Decomposition (semantics-preserving)**
* Replace unsupported op with supported ops only if semantics-preserving is clear
* Otherwise it becomes class 4

4. **Approximation (explicitly marked)**
* Allowed only if policy decides it’s acceptable, and must produce a typed “approximation” gap
* Often routes to `NEEDS_USER_CHOICE` (accept approximation?) or `PARTIAL`

This prevents “PATCH” becoming a dumping ground.

---

## 12) Convergence / “no progress” (kernel-owned, LLM-assisted)

### Kernel-level no-progress detection (primary)

Kernel maintains a rolling window of **progress signals**:

* `gap_signature` (kinds + counts + key details) from judge + compile
* `artifact_digests` (hashes of IR, compile, judge)
* `readiness_flags` (e.g., moved into READY_TO_MAP, produced georef artifact)

Define **progress** as any of:

* strict reduction in “gap_score”
* elimination of any **blocking** gaps (policy marks which are blocking)
* new required artifact produced (e.g., first valid compile polygon)
* transition into a later state (e.g., READY_TO_MAP)

If none occur for `N` repair iterations → `stop_reason=no_progress`.

### Gap scoring (simple v0; policy-owned weights)

A minimal scoring model to drive “is it improving?”:

* Each gap kind gets a weight:
  * capability gaps (unsupported op) = very high
  * missing required anchor when global placement required = high
  * missing parameter = medium
  * minor normalization issues = low
* `gap_score = Σ weight(kind) * count(kind)` (+ optional severity multipliers)

LLM can *comment* on whether remaining work is meaningful, but kernel’s default stop should be explainable via the score + signatures.

---

## 13) Retrieval modes (intentionally deferred, but not vague)

We’re explicitly doing what you asked: **don’t decide the exact modes now**, but *do* pin the responsibility:

* Policy defines “retrieval query packs” as combinations of:
  * corpus view(s) (e.g., FINAL_SEGMENTS vs EVERYTHING vs ARTIFACTS)
  * lane selection (lexical/semantic/provenance)
  * required filters (e.g., dossier_id for provenance lane)
* Implementation must be chosen by the coding agent based on repo reality and existing retrieval footguns.

This satisfies: “frame it, don’t prematurely lock it.”

---

## 14) Library-first implementation (confirmed)

v0 is **library-first**:

* Kernel is a Python module callable from CLI/tests and later wrapped by an API endpoint if needed.
* This keeps initial iteration tight, testable, and aligned with “co-located tests protect invariants.”

API wiring is a later layer, not the core.

---

## 15) Checkpoint/replay semantics (resolved)

We are **not** building “branch/rewind” as a workflow requirement.

But we *do* get practical replay benefits automatically because:

* runs persist step records and artifact refs,
* which enables debugging, audit, reproduction, and “re-run from artifact X” if needed.

So: **no checkpoint UX**, but **durable run lineage exists**.

---

## B) Repo-aware review / “green light” notes (implementation gotchas)

### Green light
This brief is **consistent with Plattera’s current architecture and contracts** and is safe to use as a reference for implementation.

### Small repo-reality gotchas to preserve (do not overfit v0)
1) **Validation persistence**
   - `POST /api/mapping/validate-georef` returns a dict, but there is not yet an explicit “validation artifact store” like feature graphs or georefs.
   - v0 can store validation outputs as run step outputs (refs to a small JSON blob in the run artifact), and add a dedicated validator persistence service later if needed.

2) **Evidence references**
   - Retrieval returns EvidenceCards/Spans in API responses and the CLI persists run artifacts under `assets/rag_runs/`.
   - v0 can treat the retrieval run artifact path + (card_id/span indices) as the durable “evidence ref,” rather than inventing a new evidence database.

3) **Semantic budgeting**
   - The retrieval API does not take a “semantic budget” parameter; `max_semantic_calls` should be enforced by the kernel by limiting how many retrieval calls include semantic lanes.
   - Worker-level budgets are already enforced by supervisor/env knobs; record worker reason codes in step logs.

4) **Approximation gap kind**
   - Feature Graph `GapKind` does not currently include a dedicated `approximation` kind.
   - v0 approximations can be recorded as:
     - `unsupported_operation` / `precondition_failed` with metadata indicating approximation was proposed, and/or
     - warnings + explicit “needs_user_choice” if approximation is a policy decision.

5) **Judge input**
   - `/api/feature-graph/judge` judges the graph; it is not currently wired to consume compiled geometry as an input.
   - The “compile vs judge separate streams” stance is correct; don’t assume judge validates compile outputs unless you extend it later.

6) **Log worker reason codes**
   - Semantic retrieval failures should capture stable reason codes (backoff, port_in_use, manifest_mismatch, timeout, unavailable) in the RunArtifact/StepRecord so ops debugging is straightforward.

