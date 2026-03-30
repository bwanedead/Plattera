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

## 3. Current Diagnosis

The current harness is no longer transcript-corrupted, but it is still under-shaped.

### 3.1 Orchestration is conceptually right, but packaged poorly

Current location:

- `backend/harness/orchestration_kernel/`

What is right:

- the harness owns a bounded per-run loop
- the loop rhythm is sane:
  - initialize loop-local context
  - hydrate current shared understanding
  - check terminal posture
  - choose one bounded next action
  - execute it
  - repeat or stop

What is wrong:

- `kernel.py` is a bad, non-descriptive name
- `orchestration_kernel/` is heavier and more legacy-coded than needed
- `kernel.py` carries too many concerns in one file
- orchestration-local memory is embedded too tightly inside the orchestration layer
- some orchestration seam types are duplicated between `kernel.py` and `contracts.py`

### 3.2 Memory is missing as a real first-class subsystem

Current location:

- `backend/harness/orchestration_kernel/loop_memory.py`

Problem:

This file is currently a mixed bag of:

- continuity state
- transport posture
- telemetry
- anti-spin / brake counters
- stale loop-shaped residue

That is not a real memory system.

The harness still needs a generic memory subsystem for things like:

- bounded recent iteration history
- rolling continuity summary
- last pursued item / current working locus
- recent action and outcome continuity
- prompt observability continuity if needed

This is distinct from mission state.

### 3.3 Mission state is not memory and should remain separate

Current location:

- `backend/harness/mission_state/`

Mission state is the shared understanding of the work:

- what items exist
- what status they have
- what dependencies or relations exist
- what supporting payload is attached

Mission state should not be collapsed into generic memory and should not be treated as the harness's whole continuity substrate.

### 3.4 Prompt-facing carriage is in the wrong place

Current location:

- `backend/harness/orchestration_kernel/run_progress_frame.py`

Problem:

This file builds a small prompt-facing packet.
That means it is not really orchestration.

If this packet is genuinely needed, it belongs under a clearly named shared prompting/context surface.
If it is leftover from older framing mechanics, it should be deleted.

Do not leave prompt-context shaping hidden inside orchestration helpers.

### 3.5 Mission runtime naming is misleading

Current location:

- `backend/harness/mission_runtime/`

The responsibilities in this area are mostly reasonable:

- mission-level cycles
- mode transitions
- resumability
- terminal posture
- mission-level observability

But several names are misleading:

- `mission_runtime` sounds lower-level than what it is
- `MissionLedger` sounds like semantic ledger truth and carries unwanted legacy associations
- `ModeRecommendation` sounds like a scripted planner/controller voice

This area is closer to **mission flow / mission coordination** than to low-level runtime mechanics.

### 3.6 Inspection surfaces are useful but under-named

Current locations:

- `backend/harness/run_state.py`
- `backend/harness/tracing/service.py`
- `backend/harness/review/tool.py`

Problem:

- `run_state.py` is not active runtime state; it is a derived inspection envelope
- `tool.py` is really a review-bundle assembler
- some files are functionally coherent but named too vaguely to teach the architecture cleanly

### 3.7 Trace collection still carries stale loop-era emitters

Current location:

- `backend/harness/orchestration_kernel/trace_collector.py`

Problem:

Even after the transcript purge, trace collection still carries old-world event methods and phase framing that imply heavier semantic staging than the current harness should own.

Trace collection should describe what happened mechanically.
It should not preserve stale semantic stage vocabulary.

---

## 4. Target Shape

The harness should converge toward something closer to:

```text
backend/harness/
  orchestration/
    orchestrator.py
    contracts.py
    context.py
    progress_detection.py
    step_execution.py          # only if earned
  memory/
    contracts.py              # only if earned
    continuity.py
    iteration_capsule.py
    rolling_summary.py
    telemetry.py              # only if earned
  mission_state/
    contracts.py
  mission_flow/
    contracts.py
    mission_coordinator.py
    registry.py
    observability.py
    transition.py             # or capabilities/transition.py if that still earns a seat
  tracing/
    ...
  review/
    ...
```

This is directional, not a rigid checklist.
Do not create files that do not earn a seat.

But the folder boundaries should become real:

- orchestration
- memory
- mission state
- mission flow
- tracing
- review

---

## 5. Naming Direction

The following naming moves are favored.

### 5.1 Orchestration

- `orchestration_kernel/` -> `orchestration/`
- `kernel.py` -> `orchestrator.py`

The file is not “a kernel” in any explanatory sense.
It is the bounded per-run orchestrator.

### 5.2 Mission flow

- `mission_runtime/` -> `mission_flow/` or `mission_orchestration/`

Preferred bias:

- use `mission_flow/` unless a better name becomes clearly superior

This subsystem coordinates mission-level cycles and transitions.
It is not the lowest-level runtime substrate.

### 5.3 Mission coordination record

- `MissionLedger` -> `MissionRecord` or `MissionCoordinationState`

Preferred bias:

- `MissionRecord`

The data structure is a mission-level coordination record, not a semantic ledger.

### 5.4 Mode cycle result naming

- `ModeRecommendation` -> `ModeCycleOutcome`

This reduces the feel of controller scripting and better matches what the object really is:

- the outcome/disposition of one mode cycle

### 5.5 Inspection envelope naming

- `run_state.py` -> `run_summary.py` or `run_envelope.py`

Preferred bias:

- `run_summary.py` if the emphasis is inspection
- `run_envelope.py` if the emphasis is normalized carriage

Do not keep `run_state.py` if the file is not representing active live state.

### 5.6 Prompt carriage naming

If `run_progress_frame.py` survives, it should be renamed around what it actually is:

- prompt context snapshot
- run snapshot
- prompt run snapshot

But the default bias is:

- delete it unless it clearly earns a seat

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

## 7. What Should Probably Be Deleted

The following surfaces should be treated as guilty until proven necessary:

- `backend/harness/orchestration_kernel/run_progress_frame.py`
- stale phase-shaped emitters or helpers inside `trace_collector.py`
- orchestration-local counters/fields in `loop_memory.py` that no longer express generic mechanical necessity
- duplicated seam models that exist both in `kernel.py` and `contracts.py`

Do not preserve a helper just because it has tests or because it was useful under the older shape.

---

## 8. What Should Probably Be Split

### 8.1 Orchestrator file

`kernel.py` should not continue to own:

- context definition
- memory state definition
- result building
- execution coercion helpers
- tracing callback wiring

Those should move to explicit files if they remain necessary.

### 8.2 Inspection summary file

`run_state.py` should likely split into:

- summary/envelope models
- orchestration payload adapter
- mission-flow payload adapter

Only split once the intended boundaries are clear.
Do not split blindly.

### 8.3 Trace collector

`trace_collector.py` should be reduced to generic emitted events that match the current harness shape.

If separate event-building helpers are needed, use focused helpers rather than one growing collector monolith.

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

---

## 10. Recommended Working Sequence

1. Create the target folder boundaries:
   - orchestration
   - memory
   - mission flow (if renaming from mission runtime in this leg)
2. Move only the cleanly-understood files first.
3. Rename the primary seams:
   - `kernel.py`
   - `MissionLedger`
   - `ModeRecommendation`
   - `run_state.py`
4. Delete `run_progress_frame.py` unless a clear live need remains.
5. Redesign loop memory into a minimal real memory subsystem.
6. Strip stale trace-collector emitters and stale phase-shaped assumptions.
7. Re-run targeted tests after each coherent batch.
8. Keep the domain layer untouched unless a harness seam change genuinely requires a corresponding rename.

---

## 11. Definition Of Done For This Leg

This refactor leg is complete when:

- orchestration is a clearly named subsystem, not `kernel.py`
- memory is a distinct shared harness subsystem
- mission state remains separate from memory
- mission flow/coordinator naming is explicit and non-legacy
- prompt-facing packet shaping is either deleted or clearly placed in a prompt/context ownership area
- trace collection no longer carries stale semantic phase vocabulary
- inspection/read-model surfaces have names that describe what they actually are
- the harness teaches its own architecture correctly through folder structure and file names

The win condition is not “tests still pass.”
The win condition is:

- the harness now has a shape that a fresh coding agent can read and extend without inheriting confusion

---

## 12. One-Line Operating Rule

Bring the harness into a structure where every shared subsystem is named for what it actually does, every responsibility has an honest home, memory is separate from mission understanding, and no leftover helper teaches the wrong architecture through naming or placement.

---

## 13. Structural status snapshot (repo reality)

Legs completed in-repo (for readers matching this brief to the tree):

- **Runtime (mechanical substrate):** `backend/harness/runtime/` umbrella — **`run/`** single-cycle loop (`orchestrator.py`, contracts, trace collector, `hitl_transport.py`, `loop_memory.py`); **`mission/`** multi-cycle coordination (`mission_coordinator.py`, `contracts.py`, HITL CLI helpers, …); **`memory/`** continuity + prompt-contact telemetry (`continuity.py`, `telemetry.py`). Wire tokens include `loop_family="orchestration_kernel"` and JSON key `mission_flow` (native payloads only; no alternate legacy keys in harness parsers).
- **Run inspection read model:** `backend/harness/run_summary/` (`models.py`, `build.py` — derived envelope + payload adaptation); registry `backend/harness/run_summary_registry.py` (`register_run_summary_builder`, …). Review bundles expose the derived envelope under `run_summary` only.
- **Removed:** `run_progress_frame.py` (dead builder); compatibility paths remain where payloads must still parse.

---

## 14. Why remaining cleanup still matters (coding-agent context)

Names, file placement, and leftover helpers are **not cosmetic** in this harness: they are part of the architecture. A helper is harmful when it either **preserves an old semantic theory of how the loop works** or **teaches the wrong ownership boundary** to the next person (human or agent).

This section explains *why* specific remaining items are called out in strict reviews—not only that they exist.

### 14.1 Trace collector: stale semantic staging vocabulary

`trace_collector` (under `backend/harness/runtime/run/`) must describe **mechanics**, not a universal agent “grammar.”

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

### 14.3 `run_summary/`: honest name, responsibilities split across modules

`backend/harness/run_summary/` is well-named (derived inspection/read model, not live state). Models live in `models.py`; adaptation and registration live in `build.py`. The package can still grow — treat new summary concerns as a boundary decision, not a default add to `build.py`.

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
- **Compatibility** exists to **read old things**, not to **define** new architecture.
- **Inspection** code (`run_summary`, review) must not become an unbounded monolith.
- **Repository structure and names** are part of the architecture story—residue teaches as much as code does.
