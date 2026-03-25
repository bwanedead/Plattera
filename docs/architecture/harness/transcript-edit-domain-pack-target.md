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
