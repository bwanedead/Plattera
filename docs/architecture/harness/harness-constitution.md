# Harness Constitution

This document defines the non-negotiable architectural constitution for Plattera's generic harnesses, mission runtimes, and agent loops.

It exists to prevent a specific class of architectural regression:

- deterministic runtime logic quietly reclaiming authorship over the agent's work
- scripted issue taxonomies becoming the real source of work content
- harness layers deciding what matters in the case before the agent has understood the case

The harness exists to provide rails, persistence, execution, observability, and safety.
It does not exist to secretly become the investigator.

---

## 1. Core Rule

The harness may be deterministic in its mechanics.
It may not be deterministic in its semantic authorship.

That means:

- deterministic rails are allowed
- deterministic work authorship is forbidden

The LLM is the engine that understands the case, forms the work, chooses the focus, and decides what unresolved items mean.

The harness is the structure around that engine.

---

## 1.1 Native Shape Rule

The harness is a **generic mission machine**.

Its intended native shape is:

- shared mission runtime
- shared orchestration kernel
- shared execution kernel
- shared generic state surfaces
- pluggable domain packs

Domain packs are the interchangeable **skins** the harness wears for particular missions.

The harness core must be intrinsically capable of hosting radically different missions without rewriting its ontology or shared execution contracts for each mission family.

If a shared layer only makes sense for one concrete mission family, it is not generic enough to live in the harness core.

---

## 2. What The Harness Is Allowed To Do

The harness may:

- persist artifacts, traces, and run state
- dispatch tools and actions
- validate schemas and payload structure
- enforce budgets, retries, and safety limits
- maintain session/run continuity
- store and project decision-ledger state
- shape bounded prompts and focus packets
- expose tool results and evidence to the agent
- enforce execution invariants that are mechanical rather than semantic

These are rails.
They support the run without deciding the case.

---

## 3. What The Harness Must Never Do

The harness must not:

- create the practical work universe through deterministic issue detection
- define the initial problem inventory through validator findings
- create, rank, or resolve decision-ledger items from hard-coded domain logic
- assign blocker meaning through deterministic domain taxonomies
- decide what is mapping-critical through scripted finding types
- generate correction plans from deterministic domain heuristics
- declare semantic closure because a validator says the transcript is clean

If a deterministic component is deciding what work exists or what that work means, the architecture is out of bounds.

---

## 4. Agent Authorship Rule

The following must be agent-authored:

- case orientation
- initial case inventory
- investigation brief content
- decision-ledger items
- blocker formation
- focus selection
- closure posture
- next-step planning
- interpretation of evidence

Valid semantic origins are:

- LLM reasoning
- explicit human feedback
- direct source material interpreted by the LLM

Tools may provide evidence.
They may not provide runtime truth about what the work means.

---

## 4.1 Orientation Contract Rule

Startup and orientation tooling may define **generic containers** only: briefs, candidate work items, blockers, dependencies, artifact inventory, and similar bounded shapes.

The harness must not require a **mission-specific ontology** (fixed decision-key lists, mandatory deed categories, or prescribed semantic slots) as the only valid startup output.

Mission-specific vocabulary may appear in **prompt doctrine** as hints. The LLM chooses the practical work universe within those containers.

**Module ownership (non-negotiable clarity):**

- Generic orientation containers and validation belong on the agent-kernel side (for example ``agent_kernel.orientation``).
- Domain packs own mission prompts, source assembly, optional legacy adapters (such as checklist-shaped seeds), and mapping from generic orientation output into native mission artifacts.
- Optional advisory fields like ``suggested_key`` are model-authored hints interpreted by domain adapters — they are not shared-harness truth.

**Kernel–domain tool seam:** Mission-specific tools (for example transcript-edit orient) live under ``agents/<mission>/`` and are wired into ``ActionExecutor`` / ``KernelSessionManager`` at construction time via **lazy import** or an explicit registration hook. The ``agent_kernel`` package must not eager-import domain tool modules during its own import (circular imports and ownership blur). Generic orientation stays in ``agent_kernel.orientation``; domain orchestration stays in the domain pack.

## 4.2 Generic Ontology Rule

Shared harness and agent-kernel layers must use **mission-agnostic ontology** only.

Allowed in shared layers:

- generic work/process vocabulary like work item, blocker, dependency, evidence, focus, priority, confidence, waiting, resolved, closure, resumability
- generic process posture such as whether something is blocked, waiting on human input, waiting on evidence, or closure-blocking as a process state

Forbidden in shared layers:

- mission-specific impact labels
- mission-specific blocker taxonomies
- mission-specific closure layers
- mission-specific decision-key families
- mission-specific quality classes

Examples of forbidden shared-layer ontology:

- ``mapping_blocking``
- ``transcript_quality_only``
- transcript-edit-specific layer labels
- deed-specific key families such as township/range/section as shared-harness truth

If a label would not make sense for a toaster, a UFO designer, an email assistant, and a finance-doc workflow alike, it does not belong in the shared harness ontology.

Mission-specific ontology belongs in:

- domain packs
- mission prompts
- mission adapters
- mission-specific read models

It does not belong in shared contracts, shared coercion helpers, or shared emergence rules.

**Work-board promotion:** shared ``evaluate_add_item_promotion`` may use generic structural signals only (for example materiality, bounded priority, dependency presence, evidence reference presence, and resolution text length). Optional fields like ``blocking_impact`` may be stored as opaque domain hints, but shared harness code must not branch on mission-specific label values.

**Naming rule:** ``work_board`` is legacy migration vocabulary only. The target generic concepts are:

- ``mission_state`` for the top-level harness continuity surface
- ``resolution_state`` for the generic active problem/work surface inside it

Do not build new architecture around the ``work_board`` metaphor.

## 4.3 Underspecification Rule

When the model leaves semantic posture incomplete or ambiguous, shared layers must preserve that ambiguity rather than silently upgrading it into domain meaning.

Shared layers may:

- normalize structure
- fill empty containers
- use neutral placeholders like ``unknown`` or ``unspecified``
- request repair / retry when required fields are missing

Shared layers must not:

- default a vague work item to a mission-specific impact class
- default a vague blocker to a mission-specific blocker kind
- default a vague item into a mission-specific closure layer
- choose mission-specific next actions on the model's behalf

When ambiguity remains, preserve ambiguity or bounce the payload back for repair.
Do not silently invent mission posture.

---

## 5. Evidence Rule

Deterministic tools are allowed to produce evidence-shaped outputs.

Good examples:

- transcript spans
- image crops
- extracted text regions
- draft-to-draft comparisons
- artifact lineage
- hashes, refs, and provenance
- structural parsing output

Bad examples:

- pre-authored issue classes as the main runtime truth
- deterministic findings like "this is the blocker"
- scripted domain labels that directly become ledger work
- deterministic closure or contradiction verdicts

The distinction is:

- evidence may be deterministic
- semantic authorship may not

---

## 6. Decision Ledger Rule

The decision ledger is the agent's organized-work surface.

The current repo may still carry legacy ``decision_ledger`` naming in transitional code, but the long-term generic harness direction is:

- ``mission_state`` as the top-level continuity object
- ``resolution_state`` as the generic active problem/work surface

The constitution rule is about the **surface's role**, not preserving one transitional metaphor forever.

It must be populated from:

- agent orientation
- agent discovery
- agent interpretation of evidence
- human feedback when present

It must not be populated from:

- deterministic validator findings as the primary source of work
- pre-authored default ontologies hidden behind startup logic
- scripted category mappers that turn findings into durable work items

The ledger may store evidence refs from tools.
The meaning of the item must still come from the agent.

---

## 6.1 Mission State Rule

The harness should converge on a top-level generic continuity object called ``mission_state``.

``mission_state`` may carry only generic harness concerns, such as:

- mission identity
- active pack / active mode
- continuity and resumability
- transition records
- high-signal artifact refs
- bounded blocker / verification / waiting summaries
- terminal posture
- trace refs
- timestamps and ordering anchors

It must not become a sink for domain ontology or domain-local truth stores.

---

## 6.2 Resolution State Rule

The harness should converge on a generic active problem/work surface called ``resolution_state``.

``resolution_state`` may contain:

- active items
- blockers
- dependencies
- evidence links
- ordering hints
- completion conditions
- state transitions
- generic notes and opaque domain payload

It must not require one fixed metaphor such as board, queue, backlog, or ledger.

It must be capable of representing:

- sequential work
- revisited work
- parallelizable work
- convergent work
- dependency-shaped work

If the implementation later becomes graph-explicit, that graph should live inside or beneath ``resolution_state`` rather than redefining the harness around a narrow project-management metaphor.

---

## 7. Focus And Blocker Rule

Focus and blocker semantics must emerge from the agent's understanding of the case.

The harness may:

- ask the agent to choose a focus
- supply bounded context
- store blocker state
- require explicit structured output

The harness must not:

- hard-code which issue type outranks another
- infer blocker truth from deterministic finding categories
- use scripted priority ladders as the practical source of focus

Priority policy may exist as a prompt doctrine.
It must not exist as hidden deterministic authorship.

Generic blocker posture is allowed.
Mission-specific blocker meaning is not.

For example:

- ``closure_blocking`` can be a generic process posture in shared layers
- what counts as closure, and why something blocks it, is domain-owned
- mission-specific blocker classes like mapping-specific or transcript-quality-specific labels belong in domain packs only

---

## 8. Closure Rule

Closure is not a validator verdict.

Closure is the agent's final judgment, grounded in:

- the current transcript state
- the decision ledger state
- available evidence
- remaining contradictions
- remaining dependencies
- mission relevance
- human feedback if present

Deterministic checks may support confidence.
They may not define semantic closure.

**Mechanical audit signals:** Runtime summaries may include mechanical tallies from inspection passes (for example, counts of error-severity observations). Name and document these as **mechanical** or **severity** signals — not as “validator clean” semantic truth. Ledger state, blockers, and LLM-authored rationale carry closure meaning; severity tallies are rails only.

Shared layers may carry a generic notion that something is closure-blocking.
The domain owns the meaning of closure itself.

Transcript-edit may define closure around mapping-readiness and transcript integrity.
Another mission may define closure completely differently.
The harness must not bake one mission's closure doctrine into shared labels.

---

## 9. Prompt And Packet Rule

Focus packets, support state, and prompt rails are allowed.

But the content carried in those structures should be agent-authored wherever it expresses:

- what the case is
- what matters
- what remains unresolved
- what the next move should be

Prompt scaffolding may shape the container.
It must not smuggle in the work content through deterministic doctrine.

---

## 10. Anti-Regression Rule

Any new harness feature, helper, or refactor must be rejected if it causes any of the following:

- the harness begins defining work content through deterministic domain logic
- a validator becomes the practical author of the run's issue inventory
- ledger items originate from scripted category mappers instead of agent reasoning
- focus or closure meaning depends on hard-coded semantic taxonomies

If a change adds semantic convenience by scripting what the case means, that change violates the constitution.

---

## 11. Review Questions

Every substantial harness or loop change should be reviewed with these questions:

1. Is the harness still only rails and infrastructure?
2. Did any deterministic component start authoring the work universe?
3. Are ledger items still agent-authored?
4. Is focus still agent-chosen rather than script-ranked?
5. Is closure still agent-judged rather than validator-declared?
6. Are tool outputs evidence-shaped instead of issue-authorship-shaped?

If any answer is "no", the design is drifting out of bounds.

---

## 12. Summary

The harness must remain:

- deterministic in mechanics
- agentic in semantic authorship
- generic in its core ontology
- domain-specific only through pluggable packs

The model decides what the case means.
The harness makes that process durable, bounded, observable, and safe.

That boundary is not optional.
