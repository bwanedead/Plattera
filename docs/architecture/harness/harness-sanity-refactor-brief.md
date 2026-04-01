# Harness Sanity Refactor Brief

This brief defines the next refactor leg for the Plattera harness.

Its purpose is simple:

- bring the harness into a high-sanity architectural shape
- remove leftover under-shaped seams and misleading names
- separate mechanics, memory, mission understanding, prompting, tracing, and review cleanly
- prepare the harness to host fresh Raptor 3 domain shells without hidden legacy pressure

This is not an anti-corruption purge of transcript-edit anymore.
That purge already happened.

This is now a **sanity and shape pass** on the shared harness itself.

---

## 1. North Star

The harness should read like a clean generic mission machine.

It should have clearly separated subsystems for:

- orchestration
- memory
- mission state
- mission flow / mission coordination
- tracing
- review
- prompting support only where shared prompting support truly earns a seat

The harness must provide rails, continuity, execution, and observability.
It must not hide semantic process machinery behind vague or overloaded names.

The desired result is:

- the harness is easy to read
- responsibilities are obvious from file and folder names
- the domain layer can remain minimal without being forced to inherit sloppy trunk seams

---

## 2. Spirit Of This Refactor

This leg is not about adding new capability.
It is about making the shared system intelligible and structurally honest.

The bias for this leg should be:

- rename vague things
- separate mixed responsibilities
- delete stale helper strata
- introduce folders where a subsystem is clearly bigger than one file
- keep deterministic logic mechanical only

Do not preserve a bad shape because it currently works.
Do not invent new abstractions just to look clean.
Do not create wrapper museums.

The target is **clarity by separation**, not abstraction for its own sake.

---

## 3. Repo reality (authoritative)

**Supersedes** older §3–§5 path names (`orchestration_kernel/`, `mission_runtime/`, top-level `run_state.py`, etc.). If anything here disagrees with §13, prefer §13 and the tree on disk.

### 3.1 Layout today

```text
backend/harness/
  mission_state/              # MissionState, ResolutionState (shared work-understanding model)
  runtime/                    # mechanical substrate (umbrella package)
    memory/                   # continuity + prompt-contact telemetry
    orchestration/            # single-cycle orchestration kernel loop
      orchestrator.py         # run_orchestration_kernel_loop
      contracts.py            # OrchestratorContext, OrchestrationAdapter (Protocol), KernelLoopResult, …
      trace_collector.py, progress.py, mission_orchestrator.py
    mission/                  # multi-cycle coordination; wire family name: mission_flow
      mission_contracts.py, mode_registry.py, mode_transition.py, …
      capabilities/transition.py
  observability/summary/      # inspection envelope (models.py + build.py)
  tracing/                    # canonical traces, service, registry, persistence, rationale strip
  review/                     # reporting + review-bundle assembler
  terminal_taxonomy.py, agents.md, test_*.py, test_fixtures/
```

There is **no** `backend/harness/orchestration_kernel/` or `backend/harness/mission_runtime/` directory. The **wire token** `loop_family="orchestration_kernel"` still names the single-cycle family in traces and run summaries; Python code lives under `runtime/orchestration/`.

### 3.2 Sanity legs already landed (summary)

- **Runtime umbrella:** `run/` vs `mission/` vs `memory/` separation is in place.
- **Inspection:** `observability/summary/` replaces the old monolithic “run_state” story; review bundles use `run_summary` only.
- **Parsers:** harness no longer merges legacy wire keys (`domain_payload`, `mission_runtime`, …); native payloads only—product migration belongs outside `harness/`.
- **Boundary repair:** shared read models avoid product semantics (`RequestSummary` has no dossier field; `VerificationSummary` has no mapping-specific readiness); `OrchestratorContext` + trace `request_start` use **`opaque_run_context`** for caller-owned context.
- **Dead inspection paths:** `run_progress_frame` fallbacks removed from `observability/summary/build.py`.
- **Traces:** collector documents mechanical phases, not a universal cognitive staging model.

### 3.3 Optional hardening (not blockers)

- Split **`observability/summary/build.py`** when the next large change touches it (orchestration vs mission-flow builders).
- Add tests for **tracing / review / run_summary** when those modules churn (core mission-flow tests already exist).
- **`OrchestrationAdapter`** types **`run_orchestration_kernel_loop`**; optional hooks like **`wire_identity_trace_cb`** stay duck-typed (`hasattr`) and are **not** part of the Protocol.

### 3.4 Open design questions (for the next coding agent)

These are **explicitly not closed**—they are small, visible follow-ups:

1. **Mechanical status surface** — Iteration and host-visible progress belong on **`KernelTraceCollector`** and **`KernelLoopResult.trace_events`** (then canonical trace / persistence), not a parallel callback on the loop driver. The unused **`progress_cb`** parameter on **`run_orchestration_kernel_loop`** was removed for that bias; do not reintroduce a duplicate status channel unless tracing proves insufficient.

2. **Protocol display name** — The typed seam is **`OrchestrationAdapter`** in **`runtime/orchestration/contracts.py`**. This is the clearer seam language for “implementation behind the orchestrator.”

---

## 4. Target shape (reconciled with the tree)

Original brief targets map to the **current** tree as follows:

| Intent | Current location |
|--------|------------------|
| Single-cycle orchestration | `runtime/orchestration/` (`orchestrator.py`, `contracts.py`) |
| Continuity / observability telemetry | `runtime/memory/` |
| Shared mission understanding | `mission_state/` |
| Multi-cycle mission coordination | `runtime/orchestration/mission_orchestrator.py` + mission-flow support surfaces |
| Canonical tracing | `tracing/` |
| Human review bundles | `review/` |
| Derived run inspection | `observability/summary/` |

Further file splits (e.g. moving coercion helpers out of `orchestrator.py`) are optional polish.

---

## 5. Naming (settled vs historical)

Moves from the **original** brief that are **done or superseded**:

- Driver file: **`orchestrator.py`** in `runtime/orchestration/` (no `kernel.py` under harness).
- Multi-cycle orchestration lives in **`runtime/orchestration/mission_orchestrator.py`**; canonical **wire name `mission_flow`** remains for traces/summaries/review.
- Inspection package: **`observability/summary/`** with `models.py` + `build.py`.
- **`run_progress_frame`:** removed from harness; no builders read that snapshot shape.

Older type renames (`MissionLedger`, `ModeRecommendation`, …) are historical; see **`runtime/orchestration/mission_contracts.py`** for current coordination types.

**Run-loop seam (Protocol):** today’s name is **`OrchestrationAdapter`**.

---

## 6. Explicit Ownership Boundaries

### 6.1 Orchestration owns

- per-run loop rhythm
- bounded iteration control
- stop / continue mechanics
- single-step execution cadence
- interaction with session/action execution
- mechanical anti-spin support if truly needed
- orchestration-local context only

### 6.2 Memory owns

- bounded recent iteration history
- rolling continuity summary
- continuity carriage across iterations
- recent action/outcome context
- observability continuity if needed

Memory does not define work semantics.
It carries continuity.

### 6.3 Mission state owns

- shared mission understanding
- identified work items
- statuses
- dependencies / relations
- domain payload attached to those items

Mission state is not the same thing as memory.

### 6.4 Mission flow owns

- mission-level cycles
- active mode tracking
- mission transitions
- resumability posture
- mission-level status summaries
- mission-level observability output

### 6.5 Tracing owns

- canonical trace schema
- trace normalization
- trace persistence helpers
- trace adaptation for supported shared families

### 6.6 Review owns

- human inspection bundles
- summary/aggregate reporting
- review artifact assembly

### 6.7 Prompting owns

Only shared prompt/context shaping that clearly belongs to the harness trunk.

Do not let orchestration become the hiding place for prompt packet builders.

---

## 7. Deletion / cleanup posture (updated)

**Already removed (harness):** `run_progress_frame`-style builders; legacy wire-key merges in parsers; product-specific fields on shared inspection models (see §3.2).

**Still treat as guilty until necessary:**

- Any **new** prompt-facing packet builders hiding under `runtime/orchestration/` instead of an explicit prompt/context area.
- **Stale phase vocabulary** reappearing on trace emitters (mechanical-only policy; see §14.1).

---

## 8. Splits and file weight (updated)

### 8.1 `orchestrator.py`

Still hosts coercion helpers (`_coerce_projection`, `_coerce_action_plan`, …) alongside the loop. **Seam types and `OrchestrationAdapter` live in `contracts.py`.** Extracting coercion to a small helper module is optional.

### 8.2 `observability/summary/build.py`

Still the largest harness adapter; splitting **orchestration-kernel** vs **mission-flow** builders is the natural next boundary when that file is next heavily edited.

### 8.3 `trace_collector.py`

Keep emitters **mechanical**; add focused helpers instead of growing a monolith if new event shapes are needed.

---

## 9. Guardrails

### 9.1 Do not smuggle semantic work back in through renames

The goal is not to rename `kernel` to `orchestrator` while preserving the same mixed guts.

The goal is:

- better names
- better boundaries
- less mixed responsibility

### 9.2 Do not confuse memory with mission state

Mission state is the shared work-understanding model.
Memory is the continuity carrier across iterations.

They are different harness features.

### 9.3 Do not overbuild the memory subsystem

Start with what is clearly needed:

- bounded iteration capsules
- rolling continuity summary
- recent active-item continuity

Do not create a giant memory framework before the actual needs are proven.

### 9.4 Do not turn prompt-context shaping into hidden orchestration law

If a packet is for the LLM, it should be obviously part of prompt/context shaping.
Do not hide prompt-facing semantics inside vaguely named orchestration helpers.

### 9.5 Do not preserve stale phase vocabulary

If traces or helpers still speak in old focus/move/plan phase language, strip that language unless it is still truly generic and necessary.

### 9.6 Prefer deletion over wrappers

Do not create compatibility wrappers just to soften the cleanup.
Delete first, reconnect cleanly.

### 9.7 Enforce the architecture in tests, not just prose

The harness now has explicit architecture guard tests in:

- `backend/harness/test_architecture_guardrails.py`

Those tests are meant to fail when shared harness drift returns. They currently cover:

- banned vocabulary and deleted concepts reappearing in live harness Python
- removed paths reappearing (`orchestration_kernel/`, `mission_runtime/`, `run_state.py`, family adapter residue, etc.)
- generic shared-surface shape for key inspection/runtime types
- file-size budgets on known hotspot modules so structural splits happen before new monoliths form

When a future change establishes a new canonical boundary, update the guard suite in the same batch.

---

## 10. Recommended working sequence (for remaining polish)

The **major structural leg** (runtime umbrella, `observability/summary/`, legacy parser purge, boundary repair on inspection/runtime) is largely complete. Further work is **incremental**:

1. Split **`observability/summary/build.py`** when a change already touches both orchestration and mission-flow adaptation.
2. Add **tests** for tracing/review/run_summary when editing those modules.
3. Keep **domain / composition** layers responsible for product IDs and pipeline readiness signals; do not reintroduce them on shared harness models.
4. Re-run **`pytest backend/harness/`** after each coherent batch and keep **`test_architecture_guardrails.py`** passing as the minimum architecture gate.

---

## 11. Definition of done (this brief’s original leg)

Treat the following as **substantially satisfied** in the current tree:

- Orchestration is a clearly named subsystem: **`runtime/orchestration/orchestrator.py`**, not a vague `kernel.py` under harness.
- Memory is distinct: **`runtime/memory/`** vs **`mission_state/`**.
- Mission coordination is explicit: **`runtime/orchestration/mission_orchestrator.py`** with wire name **`mission_flow`**.
- Prompt/run snapshot **`run_progress_frame`** is gone from harness; inspection uses **`observability/summary`** and trace-derived prompt summaries.
- Trace collection follows **mechanical** phase policy (see §14.1).

**Ongoing** (not a single PR): `observability/summary/build.py` weight, broader tests, and guarding against semantic staging creep.

---

## 12. One-Line Operating Rule

Bring the harness into a structure where every shared subsystem is named for what it actually does, every responsibility has an honest home, memory is separate from mission understanding, and no leftover helper teaches the wrong architecture through naming or placement.

---

## 13. Structural status snapshot (repo reality)

Legs completed in-repo (for readers matching this brief to the tree):

- **Runtime (mechanical substrate):** `backend/harness/runtime/` umbrella — **`orchestration/`** single-run and mission-scope orchestration plus generic mode-support contracts/registry/transition validation (`orchestrator.py`, `mission_orchestrator.py`, `contracts.py`, `mission_contracts.py`, `mode_registry.py`, `mode_transition.py`, trace collector, progress); **`memory/`** continuity + prompt-contact telemetry + loop-local memory (`continuity.py`, `telemetry.py`, `loop_state.py`); **`hitl/`** transport and CLI helpers (`transport.py`, `watch.py`, `inject.py`). Outside runtime, **`cli/`** owns CLI payload shaping and **`observability/`** owns mission payload observation/parsing. Wire tokens include `loop_family="orchestration_kernel"` and JSON key `mission_flow` (native payloads only; no alternate legacy keys in harness parsers).
- **Run inspection read model:** `backend/harness/observability/summary/` (`models.py`, `build.py` — derived envelope + payload adaptation; `registry.py` = builder registry). Review bundles expose the derived envelope under `run_summary` only.
- **Removed:** `run_progress_frame.py` (dead builder); harness parsers accept **native wire only** (product-side migration for old artifacts is outside `backend/harness/`).

---

## 14. Why remaining cleanup still matters (coding-agent context)

Names, file placement, and leftover helpers are **not cosmetic** in this harness: they are part of the architecture. A helper is harmful when it either **preserves an old semantic theory of how the loop works** or **teaches the wrong ownership boundary** to the next person (human or agent).

This section explains *why* specific remaining items are called out in strict reviews—not only that they exist.

### 14.1 Trace collector: stale semantic staging vocabulary

`trace_collector` (under `backend/harness/runtime/orchestration/`) must describe **mechanics**, not a universal agent “grammar.”

Methods or events that encode phases such as **focus selection**, **move resolution**, or **plan compilation** come from an older theory: that every run naturally decomposes into those semantic stages. That is **hidden choreography** expressed as shared harness truth.

**Why that conflicts with the target architecture**

- The harness should own **generic mechanics** (e.g. run started, model contacted, action chosen, step executed or failed, wait/complete/exhausted).
- It must **not** imply that “focus → move → plan” is the canonical staging for all loops.
- Unused or not, **load-bearing API names and phase strings teach future developers** that this vocabulary is normative.

**Direction for changes**

- Remove unused staging APIs, **or**
- Replace them with **mechanical** event types that do not assert a cognitive model of the agent.

### 14.2 Domain / family semantics: not in the harness

The harness must not own **domain logic**, **family logic**, handoff interpretation, or domain-shaped coordination types. Anything product- or domain-specific belongs under **`backend/domains/...`** or another composition layer **outside** `backend/harness/`.

**Concrete rule**

- Mode adapters may attach **opaque** JSON via `MissionModeRunEnvelope.opaque_payload` (harness does not interpret keys).
- Mission-flow observability exposes **`opaque_adapter_payload`** on the wire. Harness parsers do not merge alternate legacy coordination keys; native wire only.

### 14.3 `observability/summary/`: honest name, responsibilities split across modules

`backend/harness/observability/summary/` is the derived inspection/read model, not live state. Models live in `models.py`; adaptation and registration live in `build.py`. The package can still grow — treat new summary concerns as a boundary decision, not a default add to `build.py`.

**Why shape still matters**

- `build.py` still holds orchestration-shaped and mission-flow-shaped extraction side by side; watch for accidental coupling when extending review/observability.

**Direction**

- **Acceptable for now** after the `models` / `build` split; next splits (e.g. separate compat adapters) only if `build.py` keeps growing.
- **Do not** casually add unrelated summary or inspection logic without revisiting boundaries.

### 14.4 Wire identifiers: canonical names

Examples include `loop_family="orchestration_kernel"`, JSON keys `orchestration_kernel` / `mission_flow`, and `pack_id` in prompt metadata. These are **current** harness wire names, not temporary bridges.

**Rule**

- **New** payloads and producers must use these names only—no parallel legacy keys in shared harness code.
- If external systems still emit old keys, normalization belongs **outside** `backend/harness/` (composition or migration layer), not as alternate reads inside generic parsers.

### 14.5 Repo hygiene residue: legibility, not runtime

`__pycache__` trees, and fixtures whose **names** still reflect older mental models, do not usually break execution.

**Why they still matter**

- The tree **teaches** readers; residue increases the odds someone reuses **obsolete mental models** or assumes deprecated concepts are still first-class.

**Direction**

- Clean caches where policy allows; rename or relocate fixtures when touching them so names match current harness language.

### 14.6 Core principle (one sentence)

Stale harness artifacts are failures when they **silently reintroduce semantic staging or family policy as shared truth**—or when **compatibility tokens** stop being clearly temporary and start **defining** new design.

### 14.7 What coding agents should internalize

- Harness surfaces describe **mechanics**, not **hidden semantic choreography**.
- **Shared runtime** must not quietly absorb **family-specific meaning**.
- **Compatibility** for superseded wire keys is **not** reintroduced inside `backend/harness/`; normalization of old artifacts is a **composition** concern.
- **Inspection** code (`observability/summary`, review) must not become an unbounded monolith.
- **Repository structure and names** are part of the architecture story—residue teaches as much as code does.
