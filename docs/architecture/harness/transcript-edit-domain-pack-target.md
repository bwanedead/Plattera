# Transcript-Edit Domain Pack Target

Date: 2026-03-25
Status: Planning audit and convergence target
Scope: Transcript-edit pack only

Related:

- `docs/architecture/harness/domain-pack-constitution.md`
- `docs/architecture/harness/domain-pack-architecture.md`
- `docs/agent-testing/transcript-edit-loop-holistic-intent.md`
- `docs/transcript-edit-loop-orchestration.md`
- `docs/transcript-edit-loop-focus-cycle-architecture-2026-03-05.md`

---

## 1. Purpose

This document audits the current transcript-edit domain against the target domain-pack architecture.

It is not a claim that current transcript-edit should define the generic template.

It is an audit object:

- what transcript-edit currently owns
- why those pieces exist
- which parts look correctly domain-owned
- which parts may still be mixed, oversized, or transitional

---

## 2. Transcript-Edit Mission Summary

Transcript-edit is not merely a text-cleaning loop.

Its semantic mission is:

- take transcript-like source material and supporting evidence
- converge toward mapping-relevant transcript truth
- preserve unresolved contradictions honestly
- distinguish mapping-blocking issues from optional quality issues
- use HITL only when bounded autonomous closure is exhausted
- produce a truthful downstream posture for later mapping-family work

This is a rich semantic domain.

It is not a generic harness template.

---

## 3. Current Transcript-Edit Inventory

## 3.1 Adapter shell

Primary surface:

- `backend/agents/transcript_edit/domain_pack.py`

Current role:

- implements the orchestration kernel's 9-hook host seam
- coordinates transcript-edit state, projection, evidence use, move compilation, closure evaluation, and feedback integration

Target judgment:

- should remain as the adapter shell
- should become thinner over time

## 3.2 Domain doctrine

Primary surfaces:

- `backend/agents/transcript_edit/prompt_sources.py`
- `backend/agents/transcript_edit/prompting.py`
- `backend/agents/transcript_edit/planner.py`
- `backend/agents/transcript_edit/orient_tool.py`

Current role:

- transcript-edit branch doctrine
- planner/resolver surface prompting
- orient baseline prompt and action surface
- prompt-event integration for transcript-edit reasoning calls

Target judgment:

- correctly domain-owned

## 3.3 Domain state authority

Primary surfaces:

- `backend/agents/transcript_edit/loop_state.py`
- `backend/agents/transcript_edit/decision_ledger.py`
- `backend/agents/transcript_edit/decision_ledger_state.py`
- `backend/agents/transcript_edit/decision_ledger_closure.py`
- `backend/agents/transcript_edit/decision_ledger_scope.py`
- `backend/agents/transcript_edit/decision_ledger_focus.py`
- `backend/agents/transcript_edit/blocker_registry*.py`

Current role:

- native organized-work and closure truth
- blocker/dependency/escalation state
- feedback-adjacent semantic state
- domain-local runtime continuity

Target judgment:

- largely correct as domain-owned

Watchpoint:

- any pieces that are really generic organized-work transport rather than transcript-edit meaning should eventually move toward shared generic surfaces or be removed

## 3.4 Projection / read-model layer

Primary surfaces:

- `backend/agents/transcript_edit/decision_ledger_adapter.py`
- `backend/agents/transcript_edit/domain_pack_focus_wiring.py`
- `backend/agents/transcript_edit/state_projection.py`

Current role:

- adapt transcript-edit native truth into shared or packet-facing projections
- provide unified read models used by focus and runtime reporting

Target judgment:

- legitimate domain projection layer

## 3.5 Focus context hydration

Primary surfaces:

- `backend/agents/transcript_edit/focus_packet.py`
- `backend/agents/transcript_edit/focus_packet_board_context.py`

Current role:

- build the bounded context for an already-chosen focus item
- attach relevant ledger state, evidence, feedback, attempts, and supporting context

Target judgment:

- legitimate domain-owned hydration seam

Watchpoint:

- this area is also where tactic-shaped support material can quietly become steering
- `working_plan`, `policy_signals`, and similar helpers should be treated as scrutiny targets, not automatically canonical

## 3.6 Reasoning / move surfaces

Primary surfaces:

- `backend/agents/transcript_edit/planner.py`
- `backend/agents/transcript_edit/focus_resolver.py`
- `backend/agents/transcript_edit/plan_interpretation.py`

Current role:

- semantic move proposals
- bounded plan authoring
- coercion/validation of returned move shapes

Target judgment:

- domain-owned

## 3.7 Evidence semantics and evidence translation

Primary surfaces:

- `backend/agents/transcript_edit/evidence_executor.py`
- `backend/agents/transcript_edit/evidence_runtime.py`
- `backend/agents/transcript_edit/image_verification.py`

Current role:

- normalize evidence requests
- execute transcript/image evidence actions
- interpret/cache evidence artifacts in transcript-edit terms

Target judgment:

- mixed but mostly domain-owned

Rule:

- evidence meaning stays domain-owned
- concrete capability/tool realization should remain product-composition or shared execution territory

## 3.8 Execution translation

Primary surfaces:

- `backend/agents/transcript_edit/execution_action_ids.py`
- compile logic in `backend/agents/transcript_edit/domain_pack.py`

Current role:

- translate transcript-edit semantic moves into concrete execution requests

Target judgment:

- legitimate domain-owned translation seam

## 3.9 Closure / terminal semantics

Primary surfaces:

- `backend/agents/transcript_edit/result_policy.py`
- `backend/agents/transcript_edit/terminalization.py`
- `backend/agents/transcript_edit/runtime_summary.py`

Current role:

- define transcript-edit closure and post-run meaning
- summarize transcript-edit terminal posture

Target judgment:

- domain-owned meaning

Watchpoint:

- generic terminal mechanics must remain shared-harness owned

## 3.10 Feedback semantics

Primary surfaces:

- hook-9 integration in `backend/agents/transcript_edit/domain_pack.py`
- ticket and registry helpers in `decision_ledger*` and `blocker_registry*`

Current role:

- translate human responses into transcript-edit semantic state changes

Target judgment:

- domain-owned

---

## 4. Current Shape vs Ideal Shape

### Things transcript-edit already has that match the target

- domain doctrine
- domain-native truth surfaces
- a projection/read-model layer
- focus-context hydration
- execution translation
- closure semantics
- feedback semantics

### Things transcript-edit still appears to mix together

- adapter-shell logic and internal pack coordination in `domain_pack.py`
- rich packet hydration and tactic-shaped support material in `focus_packet.py`
- closure meaning and some terminal/reporting mechanics in adjacent modules
- capability semantics and concrete action wiring still expressed too close together

---

## 5. What Transcript-Edit Should Keep

Transcript-edit should keep ownership of:

- what counts as transcript-edit evidence
- what transcript-edit truth looks like
- how transcript-edit closure is interpreted
- how transcript-edit feedback is semantically integrated
- which capability families transcript-edit requires
- what relevant context belongs around an active transcript-edit focus

These are domain concerns.

---

## 6. What Transcript-Edit Should Not Keep

Transcript-edit should not become the owner of:

- generic loop law
- generic runtime mechanics
- generic HITL transport lifecycle
- generic focus continuity machinery
- generic observability law
- generic terminal taxonomy
- product-specific provider/tool realization

If transcript-edit currently contains logic that feels like generic machine compensation, that logic should be audited rather than blessed.

---

## 7. Target Transcript-Edit Pack Shape

Conceptual target:

```text
backend/agents/transcript_edit/
  manifest.py
  prompt_sources.py
  domain_pack.py
  state.py
  projection.py
  focus_hydration.py
  execution_translation.py
  closure.py
  feedback.py
  capabilities.py
  handoff.py
```

This is not a mandatory exact filename plan.

It is the intended responsibility split.

The crucial rule is:

- `domain_pack.py` becomes the thin host adapter
- richer semantics live behind it in narrower modules

---

## 8. Recommended Migration Order

1. Freeze domain-pack doctrine and architecture docs.
2. Introduce minimal shared manifest / capability / handoff contracts.
3. Audit transcript-edit responsibilities against those contracts.
4. Thin `domain_pack.py` into a clearer host adapter.
5. Make transcript-edit capability requirements explicit.
6. Split handoff posture out from general closure logic where useful.
7. Re-run constitutional review around focus hydration and execution translation.

---

## 9. Main Watchpoints

### 9.1 Focus-context hydration drifting into steering

Most likely seam:

- `focus_packet.py`

### 9.2 Adapter shell staying too large

Most likely seam:

- `domain_pack.py`

### 9.3 Capability semantics and concrete tool wiring staying too entangled

Most likely seam:

- compile/action-id surfaces

### 9.4 Transcript-edit semantics leaking into shared generic layers

Most likely seam:

- projection/read-model helpers if they become treated as generic truth

---

## 10. Summary

Transcript-edit is already rich enough to act as the first real domain-pack audit object.

It should not be treated as the default architecture truth.

It should be used to:

- validate the target domain-pack model
- expose mixed seams
- produce the first clean exemplar once the generic domain-pack infrastructure is in place

---

## Appendix A. Transcript-Edit Responsibility Inventory

This appendix is the code-grounded migration map for the current transcript-edit pack.

### A.1 Adapter Shell

- [backend/agents/transcript_edit/domain_pack.py](../../backend/agents/transcript_edit/domain_pack.py) is the current host adapter and remains a transitional mixed seam.
- It owns the 9-hook protocol entrypoints at `project`, `build_focus_packet`, `resolve_move`, `compile_move`, `supply_progress_metrics`, `supply_closure_rules`, and `integrate_feedback`.
- Migration judgment: keep as a thin adapter shell, but continue thinning it over time.

### A.2 Domain Doctrine

- [backend/agents/transcript_edit/prompt_sources.py](../../backend/agents/transcript_edit/prompt_sources.py), [backend/agents/transcript_edit/prompting.py](../../backend/agents/transcript_edit/prompting.py), [backend/agents/transcript_edit/orient_tool.py](../../backend/agents/transcript_edit/orient_tool.py), and [backend/agents/transcript_edit/planner.py](../../backend/agents/transcript_edit/planner.py) are correct domain ownership.
- These surfaces encode transcript-edit meaning, domain-specific prompt branches, and transcript-specific reasoning surfaces.
- Migration judgment: keep in domain; do not move into shared harness code.

### A.3 State Authority

- [backend/agents/transcript_edit/loop_state.py](../../backend/agents/transcript_edit/loop_state.py), [backend/agents/transcript_edit/decision_ledger.py](../../backend/agents/transcript_edit/decision_ledger.py), [backend/agents/transcript_edit/decision_ledger_state.py](../../backend/agents/transcript_edit/decision_ledger_state.py), [backend/agents/transcript_edit/decision_ledger_closure.py](../../backend/agents/transcript_edit/decision_ledger_closure.py), [backend/agents/transcript_edit/decision_ledger_scope.py](../../backend/agents/transcript_edit/decision_ledger_scope.py), [backend/agents/transcript_edit/decision_ledger_focus.py](../../backend/agents/transcript_edit/decision_ledger_focus.py), and the blocker-registry modules are correct domain ownership.
- Migration judgment: keep in transcript-edit; this is the native semantic state layer.

### A.4 Projection / Read Models

- [backend/agents/transcript_edit/decision_ledger_adapter.py](../../backend/agents/transcript_edit/decision_ledger_adapter.py), [backend/agents/transcript_edit/state_projection.py](../../backend/agents/transcript_edit/state_projection.py), [backend/agents/transcript_edit/work_board_projection.py](../../backend/agents/transcript_edit/work_board_projection.py), and [backend/agents/transcript_edit/organized_work_composition.py](../../backend/agents/transcript_edit/organized_work_composition.py) are mixed but mostly domain-owned projection surfaces.
- They adapt native transcript-edit state into shared containers and board/read-model shapes.
- Migration judgment: keep domain-owned for now, but continue watching for generic work-board logic that could later move to shared harness composition.

### A.5 Focus Seam Audit

- [backend/agents/transcript_edit/decision_ledger_focus.py](../../backend/agents/transcript_edit/decision_ledger_focus.py) is the most sensitive focus-seam helper. It currently performs advisory focus ordering through `choose_investigation_focus`, `authority_rank_for_candidate`, and `focus_authority_audit`.
- [backend/agents/transcript_edit/domain_pack_focus_wiring.py](../../backend/agents/transcript_edit/domain_pack_focus_wiring.py) is thin transitional glue that keeps `domain_pack.py` smaller.
- [backend/agents/transcript_edit/focus_packet.py](../../backend/agents/transcript_edit/focus_packet.py) is the main hydration seam. It contains `working_plan`, `policy_signals`, `support_state`, and the focus packet assembly logic.
- Classification:
  - Focus discovery is agent-authored or ledger-authored semantics, not deterministic harness truth.
  - Focus selection is a mixed seam today because advisory ranking and continuity carry both participate.
  - Focus-context hydration is domain-owned and legitimate, but it is carrying tactic-shaped support state that must remain under scrutiny.
  - Move resolution remains agent-authored in principle, but the current packet shaping makes the seam easy to over-steer.
- Migration judgment:
  - Keep focus hydration in transcript-edit.
  - Continue thinning advisory selection helpers so they do not become hidden semantic authority.
  - Treat `working_plan` and `policy_signals` as transitional support state, not durable doctrine.

### A.6 Reasoning Surfaces

- [backend/agents/transcript_edit/planner.py](../../backend/agents/transcript_edit/planner.py) is domain-owned reasoning code.
- `propose_plan` and `propose_focus_move` are legitimate agent-facing reasoning surfaces.
- `_planner_policy_signals` and `_coerce_focus_move` are transitional mixed helpers because they shape the prompt and normalize semantic output at the same time.
- Migration judgment: keep the reasoning surfaces in transcript-edit, but continue separating prompt shaping from output coercion where practical.

### A.7 Evidence Semantics

- [backend/agents/transcript_edit/evidence_executor.py](../../backend/agents/transcript_edit/evidence_executor.py), [backend/agents/transcript_edit/evidence_runtime.py](../../backend/agents/transcript_edit/evidence_runtime.py), and [backend/agents/transcript_edit/image_verification.py](../../backend/agents/transcript_edit/image_verification.py) are domain-owned evidence semantics.
- They remain close to execution because transcript-edit needs bounded evidence realization, but they are not generic harness mechanics.
- Migration judgment: keep in domain for now; later evaluate whether capability realization belongs more clearly in product composition.

### A.8 Execution Translation

- [backend/agents/transcript_edit/domain_pack.py](../../backend/agents/transcript_edit/domain_pack.py) contains the current execution translation seam in `compile_move`.
- [backend/agents/transcript_edit/execution_action_ids.py](../../backend/agents/transcript_edit/execution_action_ids.py) is a transitional product-composition candidate because it names concrete action wiring rather than transcript-edit meaning.
- Classification:
  - Translating an agent-authored move into a concrete execution request is legitimate transcript-edit work.
  - Hardcoded action identifiers and evidence-shape normalization are the parts most likely to migrate later.
- Migration judgment:
  - Keep semantic-to-mechanical translation in transcript-edit.
  - Watch `execution_action_ids.py` and related evidence normalization for future composition extraction.

### A.9 Closure / Feedback / Handoff

- [backend/agents/transcript_edit/result_policy.py](../../backend/agents/transcript_edit/result_policy.py) is transcript-edit closure meaning.
- [backend/agents/transcript_edit/terminalization.py](../../backend/agents/transcript_edit/terminalization.py) is terminal/reporting projection only.
- [backend/agents/transcript_edit/feedback_lifecycle.py](../../backend/agents/transcript_edit/feedback_lifecycle.py) is a mixed seam: it owns transcript-edit feedback meaning, but it also carries generic lifecycle mechanics for HITL prompt/ticket handling.
- [backend/agents/transcript_edit/domain_pack.py](../../backend/agents/transcript_edit/domain_pack.py) currently owns feedback integration at the adapter seam.
- Handoff posture is not yet a first-class transcript-edit module; it is now represented through the shared domain-pack bundle contract.
- Migration judgment:
  - Keep closure meaning in transcript-edit.
  - Keep terminalization as reporting projection.
  - Continue thinning feedback lifecycle mechanics so the generic lifecycle pieces can eventually stand apart from transcript-edit meaning.

### A.10 Capability Declaration

- Capability declaration now lives in the shared domain-pack contracts and bundle construction path, not as transcript-edit-only doctrine.
- Transcript-edit is a consumer of that shared manifest shape, not the owner of the contract itself.
- Migration judgment: keep capability requirements explicit in composition, but do not reintroduce them as hidden workflow policy.

### A.11 Current Responsibility Buckets And Classification

- Correct domain ownership:
  - domain doctrine
  - native state authority
  - projection/read models
  - focus-context hydration
  - reasoning surfaces
  - evidence semantics
  - closure meaning
  - feedback meaning
- Transitional mixed seams:
  - `domain_pack.py`
  - `focus_packet.py`
  - `decision_ledger_focus.py`
  - `planner.py` prompt shaping helpers
  - `feedback_lifecycle.py`
  - `compile_move` action mapping
- Likely shared-harness candidate:
  - generic lifecycle mechanics around feedback/ticket transport
  - advisory focus-selection mechanics that are not transcript-specific
- Likely product-composition candidate:
  - execution-action identifiers and concrete tool/provider realization
  - capability realization wiring that is currently still close to transcript-edit

### A.12 Migration Map For The Next Refactor

- Keep:
  - transcript-edit doctrine
  - ledger/state truth
  - closure meaning
  - feedback meaning
  - hydration semantics
- Thin:
  - `domain_pack.py` into a smaller adapter shell
  - focus-selection helpers that read as advisory steering
  - prompt-shaping helpers that blend policy with support state
  - feedback lifecycle helpers that mix generic transport with transcript meaning
- Split later:
  - focus hydration support state into narrower modules
  - execution translation into a narrower domain translation layer
  - evidence realization into clearer capability-specific boundaries
- Candidate for shared harness later:
  - generic lifecycle utilities
  - generic advisory ranking or bundle composition helpers if they prove reusable across domains
- Candidate for product composition later:
  - concrete capability realization
  - execution action wiring
  - provider/menu realization that is not transcript-edit semantics

### A.13 Watchpoints

- Treat `working_plan` and `policy_signals` as transitional support state, not source-of-truth doctrine.
- Treat advisory focus ranking as bounded context, not semantic authority.
- Treat execution identifiers as wiring, not meaning.
- Treat feedback lifecycle mechanics as transport unless the logic is explicitly transcript-specific.
- Do not let the bundle or manifest become a hidden workflow framework.
