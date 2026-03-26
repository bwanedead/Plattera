# Deed-to-IR Domain Pack Target

Date: 2026-03-25
Status: Planning audit and convergence target
Scope: Deed-to-IR pack only

Related:

- `docs/architecture/harness/domain-pack-constitution.md`
- `docs/architecture/harness/domain-pack-architecture.md`
- `docs/architecture/harness/transcript-edit-domain-pack-target.md`
- `docs/architecture/harness/minimal-shared-run-state-envelope.md`

---

## 1. Purpose

This document audits the current deed-to-IR domain pack against the target
domain-pack architecture.

It does not claim deed-to-IR should define the generic template.

It is an audit object:

- what deed-to-IR currently owns
- why those pieces exist
- which parts look correctly domain-owned
- which parts still look compatibility-shaped, oversized, or transitional

---

## 2. Deed-to-IR Mission Summary

Deed-to-IR is not a generic "compile IR" helper.

Its semantic mission is:

- take deed semantics and bootstrap context
- inspect the deed text and supporting evidence
- produce an IR candidate that is faithful to deed meaning
- distinguish inspectable summaries from verbatim recall
- keep refusal / retry / declare-done behavior bounded
- emit a valid downstream posture toward transcript-edit review

This is a semantic domain with strong compatibility history.

It is not a generic harness template.

---

## 3. Current Deed-to-IR Inventory

## 3.1 Adapter shell

Primary surface:

- `backend/agents/controller/domain_pack.py`

Current role:

- implements the orchestration kernel's 9-hook host seam
- coordinates deed state, context packet assembly, LLM proposal, move compilation,
  closure evaluation, and feedback integration

Target judgment:

- should remain the adapter shell
- still reads as the main mixed seam
- should become thinner over time

## 3.2 Domain doctrine

Primary surfaces:

- `backend/agents/deed_to_ir/prompt_sources.py`
- `backend/agents/controller/prompting.py`
- `backend/agents/controller/controller_proposals.py`
- `backend/agents/controller/controller_bootstrap.py`

Current role:

- deed-to-IR branch doctrine
- prompt text for the deed controller
- proposal / repair prompting around deed actions
- bootstrap prompt context for deed span seeding and IR guidance

Target judgment:

- correctly domain-owned
- the doctrine is still compatibility-flavored, but the ownership is clear

## 3.3 Domain state authority

Primary surfaces:

- `backend/agents/controller/domain_pack.py`
- `backend/agents/controller/controller_bootstrap.py`
- `backend/agents/controller/controller_context.py`
- `backend/agents/controller/controller_guardrails.py`
- `backend/agents/controller/controller_transcript.py`

Current role:

- bootstrap context and deed fingerprinting
- transcript/event continuity
- latest-ref projection
- refusal / retry / stagnation state
- phase hint and dashboard continuity

Target judgment:

- largely correct as domain-owned

Watchpoint:

- some of this is still controller-shaped continuity machinery rather than pure deed meaning
- if it becomes reusable across domains, it should be separated from deed-specific state

## 3.4 Projection / read models

Primary surfaces:

- `backend/agents/controller/controller_context.py`
- `backend/agents/controller/controller_summary.py`
- `backend/agents/controller/controller_runtime.py`

Current role:

- adapt deed-native truth into shared kernel-facing packets
- expose bounded read models for orchestration, recovery, and reporting

Target judgment:

- legitimate domain projection layer
- still more centralized than the transcript-edit target shape

## 3.5 Focus context hydration

Primary surfaces:

- `backend/agents/controller/domain_pack.py`
- `backend/agents/controller/controller_context.py`

Current role:

- assemble the bounded context for an already-chosen focus item
- attach bootstrap context, dashboard progress, transcript, refusal context,
  run summary, phase hint, and recent digest memory

Target judgment:

- legitimate domain-owned hydration seam

Watchpoint:

- this seam still carries a lot of controller-native support state
- it is not yet as cleanly separated as the transcript-edit hydration seams
- `focus_scope`, `run_summary`, and rejected-graph context should stay under scrutiny

## 3.6 Reasoning / move surfaces

Primary surfaces:

- `backend/agents/controller/controller_proposals.py`
- `backend/agents/controller/contracts.py`

Current role:

- proposal generation
- refusal-repair proposal generation
- tool-menu shaping and bounded proposal validation

Target judgment:

- domain-owned reasoning surfaces

Watchpoint:

- the proposal layer is still tightly coupled to concrete tool names and compatibility-era action IDs

## 3.7 Evidence semantics and execution translation

Primary surfaces:

- `backend/agents/controller/domain_pack.py`
- `backend/agents/controller/contracts.py`
- `backend/agents/controller/controller_bootstrap.py`

Current role:

- classify evidence-gathering vs apply semantics
- validate and compile proposal payloads into execution-ready plans
- seed deed span indices from transcript seeds
- normalize deed/artifact inputs into kernel-facing requests

Target judgment:

- mixed but mostly domain-owned

Watchpoint:

- the seam still leans on transcript-edit action IDs in the controller contract layer
- that makes it a compatibility-residue seam as well as an execution-translation seam

## 3.8 Closure / terminal semantics

Primary surfaces:

- `backend/agents/controller/domain_pack.py`
- `backend/agents/controller/controller_summary.py`

Current role:

- determine deed completion / blockage / refusal outcomes
- synthesize fallback terminal evaluation from failure classification and claimability
- report why a run ended

Target judgment:

- domain-owned meaning

Watchpoint:

- terminal mechanics remain shared-harness owned
- `compile_move` still owns `declare_done_flag`, so closure meaning and execution translation remain close

## 3.9 Feedback semantics

Primary surfaces:

- `backend/agents/controller/domain_pack.py`
- `backend/agents/controller/controller_runtime.py`

Current role:

- deed-to-IR does not have a real HITL path in v1
- `integrate_feedback` is a compatibility seam that currently no-ops

Target judgment:

- compatibility-only residue

Watchpoint:

- this seam exists only because the host protocol expects it
- it does not currently carry deed feedback meaning

## 3.10 Capability declaration / identity / handoff

Primary surfaces:

- `backend/agents/controller/domain_pack.py`
- `backend/agents/common/domain_pack_contracts.py`

Current role:

- explicit deed-to-IR manifest construction
- capability declaration
- supported handoff posture declaration
- explicit pack bundle composition

Target judgment:

- structurally sound and already explicit

Watchpoint:

- the identity surface is still built inline in the adapter file instead of being split into dedicated local modules
- compared to transcript-edit, this remains less thinned

## 3.11 Compatibility residue

Primary surfaces:

- `backend/agents/controller/contracts.py`
- `backend/agents/controller/controller.py`
- `backend/agents/controller/controller_runtime.py`
- `backend/agents/controller/domain_pack.py`

Current role:

- retired legacy controller entrypoints remain guarded by `PLATTERA_ENABLE_LEGACY_CONTROLLERS`
- deed tool/menu contracts still import transcript-edit execution IDs
- the controller packet still uses transcript-edit-oriented action constants for tool coercion and guidance

Target judgment:

- explicit compatibility residue

Watchpoint:

- this is the clearest sign that deed-to-IR is still partly shaped by previous controller history
- the residue is controlled, but it is not yet fully cleared

---

## 4. Current Shape vs Ideal Shape

### Things deed-to-IR already has that match the target

- domain doctrine
- native state authority
- projection/read models
- focus-context hydration
- reasoning surfaces
- evidence semantics
- closure semantics
- explicit manifest / capabilities / handoff declaration

### Things deed-to-IR still appears to mix together

- adapter-shell logic and internal pack coordination in `domain_pack.py`
- controller-native support state inside focus packet assembly
- closure meaning and execution translation in the same file
- compatibility-era action-ID wiring in `contracts.py`
- no-op feedback seam retained for protocol parity

---

## 5. What Deed-to-IR Should Keep

Deed-to-IR should keep ownership of:

- what counts as deed evidence
- what deed truth looks like
- how deed closure is interpreted
- how proposal/refusal/retry behaves
- which capability families the pack requires
- what relevant context belongs around an active deed focus
- the supported downstream posture toward transcript-edit

These are domain concerns.

---

## 6. What Deed-to-IR Should Not Keep

Deed-to-IR should not become the owner of:

- generic loop law
- generic runtime mechanics
- generic HITL transport lifecycle
- generic focus continuity machinery
- generic observability law
- generic terminal taxonomy
- product-specific provider/tool realization

If deed-to-IR currently contains logic that feels like generic machine compensation,
that logic should be audited rather than blessed.

---

## 7. Target Deed-to-IR Pack Shape

Conceptual target:

```text
backend/agents/controller/
  domain_pack.py
  prompt_sources.py
  capabilities.py
  handoff.py
  controller_context.py
  controller_proposals.py
  controller_summary.py
  controller_bootstrap.py
  controller_transcript.py
  controller_guardrails.py
  contracts.py
```

This is not a mandatory exact filename plan.

It is the intended responsibility split.

The crucial rule is:

- `domain_pack.py` becomes the thin host adapter
- explicit manifest / capability / handoff logic can be split out later if
  the adapter starts growing again
- compatibility-era action-ID coupling should be narrowed where practical

---

## 8. Recommended Migration Order

1. Freeze deed-to-IR doctrine and architecture docs.
2. Keep the explicit shared manifest / capability / handoff contracts in place.
3. Thin `domain_pack.py` into a clearer host adapter.
4. Split compatibility-era action-ID guidance out of controller contracts if it becomes reusable or cross-domain.
5. Keep the no-op feedback seam clearly labeled as protocol parity only.
6. Re-run constitutional review around focus hydration and execution translation.

---

## 9. Main Watchpoints

### 9.1 Focus-context hydration drifting into steering

Most likely seam:

- `backend/agents/controller/domain_pack.py`
- `backend/agents/controller/controller_context.py`

### 9.2 Adapter shell staying too large

Most likely seam:

- `backend/agents/controller/domain_pack.py`

### 9.3 Capability semantics and concrete wiring staying too entangled

Most likely seam:

- `backend/agents/controller/contracts.py`

### 9.4 Compatibility residue staying too visible

Most likely seam:

- `backend/agents/controller/contracts.py`
- `backend/agents/controller/controller_runtime.py`

### 9.5 Transcript-edit compatibility leaking back into deed identity

Most likely seam:

- `backend/agents/controller/contracts.py`

---

## 10. Summary

Deed-to-IR is already a real domain-pack object.

It is not the same as transcript-edit, but it is now explicit enough to audit
against the target architecture.

It should be used to:

- validate the target domain-pack model
- expose remaining compatibility residue
- produce a clearer convergence map before any refactor

---

## Appendix A. Deed-to-IR Responsibility Inventory

This appendix is the code-grounded migration map for the current deed-to-IR pack.

### A.1 Adapter shell

- [backend/agents/controller/domain_pack.py](../../backend/agents/controller/domain_pack.py)
  is the current host adapter and remains a transitional mixed seam.
- It owns the 9-hook protocol entrypoints: `refresh`, `project`,
  `build_focus_packet`, `resolve_move`, `compile_move`, `supply_progress_metrics`,
  `supply_closure_rules`, `integrate_feedback`, and `build_domain_runtime_state`.
- Migration judgment: keep as a thin adapter shell, but continue thinning it.

### A.2 Domain doctrine

- [backend/agents/deed_to_ir/prompt_sources.py](../../backend/agents/deed_to_ir/prompt_sources.py)
  is the explicit branch doctrine surface.
- [backend/agents/controller/prompting.py](../../backend/agents/controller/prompting.py)
  and [backend/agents/controller/controller_proposals.py](../../backend/agents/controller/controller_proposals.py)
  shape the deed controller prompt contract and proposal loop.
- Migration judgment: keep in domain; do not move into shared harness code.

### A.3 State authority

- [backend/agents/controller/controller_bootstrap.py](../../backend/agents/controller/controller_bootstrap.py),
  [backend/agents/controller/controller_context.py](../../backend/agents/controller/controller_context.py),
  [backend/agents/controller/controller_guardrails.py](../../backend/agents/controller/controller_guardrails.py),
  and [backend/agents/controller/controller_transcript.py](../../backend/agents/controller/controller_transcript.py)
  form the deed-native continuity/state layer.
- Migration judgment: keep in deed-to-IR; this is the native semantic state layer.

### A.4 Projection / read models

- [backend/agents/controller/controller_context.py](../../backend/agents/controller/controller_context.py)
  and [backend/agents/controller/controller_summary.py](../../backend/agents/controller/controller_summary.py)
  adapt deed-native state into shared kernel-facing packets and summaries.
- Migration judgment: keep domain-owned for now, but continue watching for generic
  helper extraction opportunities.

### A.5 Focus seam audit

- [backend/agents/controller/domain_pack.py](../../backend/agents/controller/domain_pack.py)
  is the main focus-context hydration seam.
- Classification:
  - Focus discovery is controller/domain-authored semantics, not deterministic harness truth.
  - Focus selection is a mixed seam today because the work-item ranking is still controller-shaped.
  - Focus-context hydration is domain-owned and legitimate, but it is carrying a lot of support state.
  - Move resolution remains agent-authored in principle, but the packet shaping is still close enough to the seam to be a watchpoint.
- Migration judgment:
  - Keep focus hydration in deed-to-IR.
  - Treat the support-state carrier as transitional if it starts steering.

### A.6 Reasoning surfaces

- [backend/agents/controller/controller_proposals.py](../../backend/agents/controller/controller_proposals.py)
  and [backend/agents/controller/contracts.py](../../backend/agents/controller/contracts.py)
  are the proposal and validation surfaces.
- `propose_next_step` and `propose_refusal_repair_step` are legitimate agent-facing
  reasoning surfaces.
- Migration judgment: keep the reasoning surfaces in deed-to-IR, but continue
  separating prompt shaping from output coercion where practical.

### A.7 Evidence semantics

- [backend/agents/controller/controller_bootstrap.py](../../backend/agents/controller/controller_bootstrap.py)
  seeds deed span indices from transcript seeds.
- [backend/agents/controller/contracts.py](../../backend/agents/controller/contracts.py)
  still encodes the concrete action menu / schema guidance for deed actions.
- [backend/agents/controller/domain_pack.py](../../backend/agents/controller/domain_pack.py)
  classifies evidence-gathering actions and keeps bounded controller evidence use explicit.
- Migration judgment:
  - keep evidence meaning in deed-to-IR
  - watch the action-ID coupling as a likely future composition extraction point

### A.8 Execution translation

- [backend/agents/controller/domain_pack.py](../../backend/agents/controller/domain_pack.py)
  contains the current compile seam.
- [backend/agents/controller/contracts.py](../../backend/agents/controller/contracts.py)
  still imports transcript-edit action IDs to define deed tool/menu and validation
  behavior.
- Classification:
  - translating an agent-authored move into a concrete execution request is legitimate
    deed-to-IR work
  - hardcoded action identifiers and tool-menu naming are the parts most likely to migrate later
- Migration judgment:
  - keep semantic-to-mechanical translation in deed-to-IR
  - treat transcript-edit action-ID coupling as compatibility residue

### A.9 Closure / feedback / handoff

- [backend/agents/controller/domain_pack.py](../../backend/agents/controller/domain_pack.py)
  owns closure evaluation and the feedback no-op seam.
- Supported handoff posture is declared in the deed bundle manifest in
  [backend/agents/controller/domain_pack.py](../../backend/agents/controller/domain_pack.py).
- Handoff posture is explicit in the manifest, but it is not yet projected as a
  first-class runtime output the way transcript-edit now does.
- Migration judgment:
  - keep closure meaning in deed-to-IR
  - keep terminalization/reporting distinct
  - keep the no-op feedback seam labeled as compatibility-only

### A.10 Capability declaration

- Capability declaration now lives in the shared domain-pack contracts and bundle
  construction path, not as deed-only doctrine.
- [backend/agents/controller/domain_pack.py](../../backend/agents/controller/domain_pack.py)
  constructs the manifest inline.
- Migration judgment:
  - keep capability requirements explicit in composition
  - do not reintroduce them as hidden workflow policy

### A.11 Compatibility residue

- [backend/agents/controller/contracts.py](../../backend/agents/controller/contracts.py)
  imports transcript-edit action IDs and treats them as valid deed tool-menu values.
- [backend/agents/controller/controller_runtime.py](../../backend/agents/controller/controller_runtime.py)
  and [backend/agents/controller/controller.py](../../backend/agents/controller/controller.py)
  still contain retired-legacy controller guards.
- `integrate_feedback` is a protocol-parity no-op, not real deed feedback semantics.
- Migration judgment:
  - keep the residue bounded and explicit
  - remove or split it only when a better product-composition seam exists

### A.12 Current responsibility buckets and classification

- Correct domain ownership:
  - domain doctrine
  - native state authority
  - projection / read models
  - focus-context hydration
  - reasoning surfaces
  - evidence semantics
  - closure meaning
  - explicit manifest / capability / handoff declaration
- Transitional mixed seams:
  - `domain_pack.py`
  - focus packet assembly in `domain_pack.py`
  - `controller_context.py`
  - `controller_summary.py`
  - `controller_proposals.py`
  - `contracts.py` tool/menu shaping
- Compatibility-only residue:
  - retired legacy controller guards
  - `integrate_feedback` no-op seam
  - transcript-edit action-ID coupling in `contracts.py`
- Likely shared-harness candidate:
  - generic lifecycle or observability utilities if they prove reusable
- Likely product-composition candidate:
  - concrete capability realization
  - execution action wiring that is currently encoded as deed-specific compatibility glue

### A.13 Migration map for the next refactor

- Keep:
  - deed doctrine
  - state truth
  - closure meaning
  - focus hydration
  - supported handoff posture
- Thin:
  - `domain_pack.py` into a smaller adapter shell
  - prompt shaping helpers that mix policy with support state
  - tool/menu guidance that is still carrying transcript-edit residue
- Split later:
  - any reusable manifest/capability/handoff helper surface if the controller pack grows again
  - compatibility-era action-ID guidance if it becomes a shared or product-owned seam
- Candidate for shared harness later:
  - generic lifecycle utilities
  - generic packet-observability helpers
- Candidate for product composition later:
  - concrete provider/tool realization
  - action-menu realization that is no longer deed-specific compatibility wiring

### A.14 Watchpoints

- Treat the action-ID coupling in `contracts.py` as compatibility residue, not doctrine.
- Treat `integrate_feedback` as protocol parity only until deed-to-IR grows a real HITL path.
- Keep the manifest inline for now, but do not let it become another hidden monolith.
