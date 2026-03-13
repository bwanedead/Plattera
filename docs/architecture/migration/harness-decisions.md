# Harness Decisions Log

Date: 2026-03-11
Status: Active
Primary sequencing reference: `docs/architecture/migration/harness-convergence-roadmap.md`

## Purpose

Record major architectural decisions and reversals for harness convergence.

This log is practical by design:
- concise decision entries
- explicit rationale and consequences
- explicit revisit triggers

## Entries

### HD-001: Treat convergence as a harness program, not isolated loop refactors
- Status: Accepted
- Decision: Run migration as a phased architecture program with shared contracts and a tracked delta ledger.
- Rationale: Isolated refactors do not reliably converge ownership, vocabulary, or observability across loop families.
- Consequences: Work is sequenced and review-heavy; implementation phases must update migration records.
- When to revisit: If phased program overhead materially blocks delivery or if loop families diverge for justified product reasons.

### HD-002: Normalize traces before broad state convergence
- Status: Accepted
- Decision: Define and adopt a canonical trace schema and adapters before attempting broad continuity/state unification.
- Rationale: Observability normalization is lower-risk and creates the evidence base needed for state ownership decisions.
- Consequences: Early work emphasizes schema/adapters and may allow temporary parallel state models.
- When to revisit: After trace adapters are in place and evidence shows state convergence can proceed safely.

### HD-003: Shared harness framework with domain policies
- Status: Accepted
- Decision: Converge toward one shared harness spine with domain-specific loop policies preserved where weight-bearing.
- Rationale: We need shared infrastructure consistency without flattening domain-specialized behavior that carries real value.
- Consequences: Contract work must define shared vs domain boundaries explicitly in each phase.
- When to revisit: If policy-specific behavior repeatedly forces shared-spine exceptions that imply wrong boundary placement.

### HD-004: Keep docs cleanup light and intentional
- Status: Accepted
- Decision: Establish a clean active architecture/migration spine in `docs/architecture/` without full docs-tree reorganization now.
- Rationale: Improves navigability quickly while avoiding disruptive docs churn during active migration.
- Consequences: Older docs remain in place and are treated as reference/historical unless linked as active.
- When to revisit: If active docs become hard to navigate again or if architecture surface grows enough to justify broader reorganization.

### HD-005: Shared terminal taxonomy is harness-level; reason codes remain granular
- Status: Accepted
- Decision: Use a shared harness terminal class set for cross-loop comparability while preserving loop/domain reason-code granularity.
- Rationale: Cross-loop analysis needs normalized classes, but operational diagnosis still needs detailed reason codes.
- Consequences: Implementations must map local outcomes to harness classes without collapsing reason codes.
- When to revisit: If taxonomy classes are too coarse for reliable steering or too fine for consistent mapping.

### HD-006: Shared blocker envelope, domain-specific blocker content
- Status: Accepted
- Decision: Define one shared blocker/escalation envelope while allowing domain-specific blocker payload extensions.
- Rationale: Shared lifecycle and escalation semantics are needed for convergence; domain payloads still carry specialized value.
- Consequences: Non-blocker-native loops may synthesize blockers first; transcript-edit keeps richer closure internals as extensions.
- When to revisit: After migration phases show whether envelope fields are insufficient or overly heavy.

### HD-007: Minimal shared run-state envelope stays narrower than full run ledger
- Status: Accepted
- Decision: Adopt a minimum shared run-state envelope for resumability and comparability, defer full canonical run ledger design.
- Rationale: Premature full-ledger abstraction risks overfitting and monolith drift before contracts are proven in implementation.
- Consequences: Keep baseline fields small and extension-friendly; trace remains the detailed event record.
- When to revisit: After Phase 5 and 6 implementation evidence clarifies true shared state pressure.

### HD-008: Transcript-edit authority split (ledger closure truth, registry lifecycle truth)
- Status: Accepted
- Decision: In transcript-edit, decision ledger is canonical for unresolved closure truth; blocker registry is canonical for blocker and escalation lifecycle truth; loop-state pending prompt fields and terminal outputs are projection/compatibility layers.
- Rationale: Current code already derives closure gates from ledger and lifecycle transitions from registry; formalizing split removes ambiguous dual ownership before migration.
- Consequences: Implementation must route authority reads/writes through canonical owners and treat compatibility fields as non-authoritative projections.
- When to revisit: After Phase 5 migration when duplicate pending-prompt paths are retired or when emergent blocker behavior suggests a different authority split.

### HD-009: Canonical trace normalization uses per-loop adapters with a shared builder
- Status: Accepted
- Decision: Implement canonical traces with per-loop-family adapters (`controller_kernel`, `transcript_edit`) that feed a small shared canonical builder layer for schema/order/index enforcement.
- Rationale: Avoids a central trace monolith while still enforcing one canonical contract surface.
- Consequences: Loop semantics remain owned by family adapters; shared builder remains contract mechanics only.
- When to revisit: If a third loop family reveals missing shared seams or duplicate adapter logic that justifies refactoring boundaries.

### HD-010: First rollout slice is adapter-first and read-only across both loop families
- Status: Accepted
- Decision: First implementation slice ships read-only canonical trace adapters for both loop families from existing persisted artifacts, with schema and mapping tests; no runtime rewrites.
- Rationale: Lowest-risk path to prove canonical schema viability across heterogeneous sources.
- Consequences: Early traces may be partial for some historical runs; runtime emitters are deferred.
- When to revisit: After first slice results show where runtime-native enrichment is worth the complexity.

### HD-011: Raw-plus-canonical retention model
- Status: Accepted
- Decision: Keep existing raw observability artifacts as source of truth and treat canonical traces as additive normalized derivatives linked to raw source refs.
- Rationale: Preserves forensic fidelity and avoids lossy migration to a new single store.
- Consequences: Search should target canonical fields, while deep replay/debug follows source links to raw artifacts.
- When to revisit: If storage/query costs or operational complexity justify changing default retention and indexing strategy.

### HD-012: Shared terminal taxonomy is implemented as a classification seam
- Status: Accepted
- Decision: Implement shared terminal taxonomy in `backend/harness/terminal_taxonomy.py` as pure mapping helpers consumed by loop-family adapters; do not rewrite loop control flow or terminalization policy in this phase.
- Rationale: Provides one harness-level outcome vocabulary with low migration risk while preserving loop-family semantics and reason-code detail.
- Consequences: Tracing adapters now normalize through one shared mapper; broader runtime/API adoption is deferred to later phases.
- When to revisit: When runtime surfaces are ready for additive normalized terminal-class exposure beyond tracing.

### HD-013: Outer-loop review foundation is observational and trace-first
- Status: Accepted
- Decision: Implement Phase 8 review/eval as a lightweight observational layer over canonical traces and shared run-state envelopes (`backend/harness/review/reporting.py`), with deterministic heuristic flags and aggregate summaries, not runtime policy enforcement.
- Rationale: The outer loop needs evidence-driven diagnosis and contract-shape discovery without introducing a heavyweight analytics platform or hidden decision engine.
- Consequences: Review outputs are JSON-friendly artifacts for iteration and diagnosis; they inform migration and contract refinement but do not control loop execution.
- When to revisit: If recurring review usage demands persisted reporting workflows, benchmark packs, or stricter eval gates.

### HD-014: Operational review flow is a thin read-only orchestration tool
- Status: Accepted
- Decision: Operationalize review workflow via a small read-only orchestration tool (`backend/harness/review/tool.py`) that composes tracing service, shared run-state builders, and review reporting for single-run and multi-run analysis.
- Rationale: Make review flow usable in daily harness engineering without adding API endpoints, dashboard systems, or duplicate analytics services.
- Consequences: Tool output is structured JSON-friendly artifacts; explicit payload input remains required; orchestration stays thin and non-authoritative.
- When to revisit: If usage pressure justifies a scheduled/automated workflow or a persisted report index.

### HD-015: Ralph is out of scope for harness convergence
- Status: Accepted
- Decision: Exclude Ralph and `legacy-ralph/` from active harness-convergence steering, migration, and implementation planning.
- Rationale: Ralph is unrelated to the current harness-convergence program and introduces noise into decisions about shared harness architecture.
- Consequences: Future harness steering should focus on active harness-relevant seams only, especially transcript-edit and kernel compatibility surfaces.
- When to revisit: Only if a separately scoped legacy cleanup effort explicitly includes Ralph and its relationship to the harness.

### HD-016: Transcript-edit authority is materially converged; remaining work is simplification
- Status: Accepted
- Decision: Treat transcript-edit authority as materially converged after Phase 6/6A; future work should focus on compatibility retirement and simplification rather than reopening authority architecture.
- Rationale: Ledger-backed closure truth, registry-backed lifecycle truth, and projection-only waiting/resume fields are now materially implemented and covered by authority tests.
- Consequences: Steering should no longer frame transcript-edit authority as the primary unfinished architecture layer; shared-layer thinness and operational maturity now take priority.
- When to revisit: If new runtime evidence shows authority drift reappearing in code or if a later blocker architecture change materially alters the ownership model.

### HD-017: Shared run-state derives waiting/resumability from domain projection seams
- Status: Accepted
- Decision: `backend/harness/run_state.py` must remain a thin read-model builder and consume transcript-edit waiting/resumability projection through `agents.transcript_edit.state_projection.derive_waiting_feedback_projection` instead of re-deriving parallel waiting rules in harness-local helpers.
- Rationale: Waiting/resumability semantics are domain-owned for transcript-edit; duplicate derivation in harness creates drift risk and accidental second authority surfaces.
- Consequences: Harness run-state builders now compose domain projections with persisted/read-model snapshots; future waiting-rule changes should land in the transcript-edit projection seam and flow through to harness read models.
- When to revisit: If a new neutral projection interface supersedes `state_projection` or if loop families adopt a canonical-trace-first derivation path with equivalent authority preservation.

### HD-018: Phase 11 compatibility seams are explicitly classified and deprecation-oriented
- Status: Accepted
- Decision: Treat `transcript_edit_agent` endpoint/CLI as canonical harness-facing transcript-edit surfaces; treat `backend/transcript_edit` as the preferred package import path while package ownership is still transitional; keep `transcription_edit` endpoint/CLI and `run_kernel` as narrow legacy compatibility seams; treat `resume_pending_feedback_*` request fields as compatibility bridges with registry-first resumability as canonical authority.
- Rationale: Remaining ambiguity in active seams causes migration drift and caller confusion; explicit seam classification reduces accidental expansion of legacy paths.
- Consequences: New harness-oriented transcript-edit work should target canonical endpoint/CLI surfaces; compatibility paths remain additive and isolated until deprecation triggers are met.
- When to revisit: When telemetry/tests show compatibility consumers are retired and removal conditions in the Phase 11 seam ledger are met.

### HD-019: Trace/review operational artifacts are explicit export bundles
- Status: Accepted
- Decision: Canonical traces remain additive read models and are operationalized through explicit opt-in review bundle export (`harness.review.tool`) rather than background persistence or a separate trace platform.
- Rationale: Live-loop engineering needs durable evidence artifacts, but automatic storage layers create hidden persistence drift and platform creep.
- Consequences: Engineers can generate single-run or multi-run stable JSON bundles containing canonical trace, shared run-state envelope, review summaries, and aggregate summaries; writes occur only when explicitly requested.
- When to revisit: If operational load shows explicit artifact generation is insufficient and a bounded persisted index is justified without violating thin-layer constraints.

### HD-020: Review loop is institutionalized as a recurring observational routine
- Status: Accepted
- Decision: Establish a documented recurring harness review operating routine with required questions and artifact expectations, while keeping review outputs observational and non-enforcement.
- Rationale: The review tool exists, but without cadence/ownership ritual it does not reliably drive contract evolution or ergonomics discovery.
- Consequences: Harness engineering now has a concrete review ritual tied to trace/run-state/review bundles and recurring evidence-led questions; no runtime policy gating is introduced from review flags.
- When to revisit: If organization ownership/cadence changes or review volume requires a different operational cadence model.

### HD-021: Phase 14 regression packs protect high-signal normalized semantics
- Status: Accepted
- Decision: Add a compact fixture-backed harness regression pack that asserts high-signal normalized behavior (terminal class/reason, waiting posture, verification presence, partial-trace posture, selected review flags, mixed-run aggregate rates) instead of full serialized snapshots or performance benchmarking.
- Rationale: Harness convergence needs repeatable drift detection at canonical seams without freezing incidental internal details or creating a heavyweight benchmark framework.
- Consequences: Regression coverage stays maintainable and evidence-focused while still catching meaningful behavior shifts across controller/kernel and transcript-edit runs.
- When to revisit: If repeated regressions show missing signal and justify adding a small number of additional representative fixtures or aggregate assertions.

### HD-022: Unified mission runtime is locked as a four-layer, contract-first architecture with linear v1 transitions
- Status: Accepted
- Decision: For unified mission runtime implementation, lock the four-layer split (`MissionRuntime`, execution kernel, `RuntimeCapability`, `ModePolicy`), classify `MissionLedger` and `ModeTransition` as runtime-owned record contracts (not additional layers), enforce contract-first implementation posture via `docs/architecture/harness/mission-runtime-contracts-v1.md`, and constrain v1 mode switching to linear synchronous in-place transitions under one mission identity/continuity chain with two-owner transition flow (`ModePolicy` recommends, `MissionRuntime` validates/applies/persists).
- Rationale: The migration plan identified interface ambiguity as the main near-term drift risk; freezing boundaries and transition constraints first reduces monolith drift and ad hoc orchestration seams.
- Consequences: Runtime work should implement against the locked contract layer, keep domain truth in mode policies, keep reusable mechanics in capabilities, and defer child subruns.
- When to revisit: After first production use of cross-mode mission transitions if evidence shows linear in-place switching is insufficient or boundaries repeatedly force exceptions.

### HD-023: Phase A mission runtime shell is narrow, family-agnostic scaffolding
- Status: Accepted
- Decision: Implement Phase A as a minimal shared mission runtime shell under `backend/harness/mission_runtime/` with contract-aligned `MissionLedger` and `ModeTransition` records, a small mode-policy registry seam, active-mode tracking, and transition/terminal routing using fake-policy tests; defer deed-to-IR and transcript-edit runtime migration.
- Rationale: Early shell realism is needed to anchor later migration phases, but mixing family behavior now would inflate interfaces and blur ownership boundaries.
- Consequences: The shared shell exists and is testable without introducing a new mission-runtime monolith or controller-v2 policy interface; next phases can wire real families through additive adapters.
- When to revisit: When beginning first family integration slice (deed-to-IR mode adaptation) and evaluating whether additive compatibility seams remain sufficient.

### HD-024: Phase B integrates deed-to-IR as first real ModePolicy via additive adapter
- Status: Accepted
- Decision: Integrate deed-to-IR/controller as the first real `ModePolicy` under `MissionRuntime` using a narrow adapter module (`backend/harness/mission_runtime/modes/deed_to_ir.py`) that wraps existing `run_controller_loop` inputs/results into mission-runtime interpretation/recommendation structures, without transcript-edit migration and without nested mission/subrun mechanics.
- Rationale: The architecture needed proof that the Phase A shell can host a real family while preserving current controller behavior and keeping shell/policy boundaries constrained.
- Consequences: `MissionRuntime` now executes a real deed-to-IR cycle through a bounded mode policy seam; controller internals remain owned by controller-family modules; transcript-edit stays out of scope for this phase.
- When to revisit: When starting transcript-edit integration and deciding what (if any) reusable runtime capabilities should be extracted from mode-local adapters.

### HD-025: Phase C introduces a minimal capability layer and runtime-owned mode execution seam
- Status: Accepted
- Decision: Extract only one shared Phase C runtime capability (`transition`) under `backend/harness/mission_runtime/capabilities/`, and clarify execution ownership by introducing a typed `ModeCycleContext` contract that carries optional execution intent/result while runtime remains the executor of that seam.
- Rationale: Phase B left execution hidden inside policy context assembly; Phase C needed reusable mechanics without capability-zoo drift, so family-specific completion logic remained mode-local while transition validation became the first shared capability.
- Consequences: Runtime/policy ownership is clearer (`build_context` returns typed cycle context with optional execution adapter, runtime executes, policy interprets/recommends); mission runtime remains linear and family-agnostic; transcript-edit migration remains deferred.
- When to revisit: When transcript-edit ModePolicy integration shows whether additional capabilities are justified by real two-family reuse pressure.

### HD-026: Phase D integrates transcript-edit as second ModePolicy with authority-preserving adapter boundaries
- Status: Accepted
- Decision: Integrate transcript-edit as the second real `ModePolicy` via `backend/harness/mission_runtime/modes/transcript_edit.py`, keeping adapter logic additive and mode-local; preserve transcript-edit authority by consuming compact mission-runtime summary fields produced from transcript-edit canonical owners (ledger-backed closure/verification summary and registry-backed waiting/blocker/resume summary).
- Rationale: Transcript-edit is a richer family; shared mission runtime needed a second-family proof without flattening transcript-edit authority internals or growing domain branches in `MissionRuntime`.
- Consequences: Mission runtime remains generic and linear while transcript-edit runs through the same mode seam; no nested/child mission structure or cross-mode orchestration is introduced in this phase.
- When to revisit: When enabling cross-mode transitions between deed-to-IR and transcript-edit and validating whether any additional capability extraction is justified.

### HD-027: Phase E enables first linear in-place cross-mode round-trip under one mission continuity chain
- Status: Accepted
- Decision: Enable explicit transition recommendations and runtime-applied transitions for the first supported round-trip path (`deed_to_ir -> transcript_edit -> deed_to_ir`) using `ModeTransitionRecommendation`/`ModeTransition` records only, with synchronous in-place mode switching under one mission identity and one continuity chain.
- Rationale: The unified mission runtime needed a concrete multi-stage proof that preserves shell genericity and bounded mission ledger continuity without nested mission structures.
- Consequences: Executed-mode vs resulting-active-mode semantics are explicit per cycle (`trace_segment.mode` captures executed mode; ledger `active_mode` may change after transition apply); transition records now carry reviewable reason, handoff refs, expected next work, and resume note; no child mission model is introduced.
- When to revisit: When broadening transition heuristics beyond bounded metadata-gated triggers and when deciding production cross-mode orchestration policy.

### HD-028: Phase F adds bounded mission-level observability without changing runtime model
- Status: Accepted
- Decision: Extend harness observability additively so multi-mode missions are represented as one continuous mission story across canonical traces, shared run-state envelopes, and review summaries; keep runtime transition mechanics unchanged and keep observability fields bounded/read-model oriented.
- Rationale: After Phase E introduced real cross-mode runtime flow, operational visibility needed explicit mission continuity surfaces (mode segments, transition events, active/resulting mode clarity) without creating a second mission ledger or nested-run concepts.
- Consequences: Canonical tracing now supports `mission_runtime` loop family and mission-level fields (`mission_id`, `active_mode`, `mode_history`, `transition_events`, `resume_context_summary`) with explicit `mode_segment` and `mission_transition` events; shared run-state includes mission mode awareness (`active_mode`, `mode_history`, latest transition reason, bounded resume context); review summaries/aggregates expose mode history and transition counts/reasons while remaining observational.
- When to revisit: If mission observability payloads begin mirroring domain-local ledgers or if mission-level fields are insufficient for operator diagnosis of executed-mode vs resulting-active-mode semantics.

### HD-029: Phase G establishes canonical unified mission CLI and explicit compatibility CLI classifications
- Status: Accepted
- Decision: Treat `backend/api/mission_runtime_cli.py` as the canonical dev/testing CLI for unified mission runtime, and classify family-specific CLIs as compatibility/legacy surfaces (`agent_loop_cli`, `transcript_edit_agent_cli`, `transcription_edit_cli`) while keeping `agent_kernel.cli` low-level debug-only.
- Rationale: Entry-surface ambiguity was reintroducing an implicit engine split even after mission runtime unification; one canonical mission-facing CLI reduces drift and preserves explicit compatibility seams.
- Consequences: New harness-oriented manual testing should start from mission-runtime CLI; legacy CLIs remain additive but non-canonical and should avoid growth beyond compatibility needs; UI/service state can carry mission-level mode continuity fields without assuming separate engine species.
- When to revisit: When production-facing API/UI surfaces fully converge on mission runtime and compatibility CLI consumers are demonstrably retired.

## Change Protocol

For each new major decision or reversal, append an entry with:
- decision id
- status (`accepted`, `superseded`, `reversed`, `proposed`)
- rationale
- consequences
- explicit revisit condition

If an accepted decision is revised, keep original entry and add a newer entry that references the prior id.
