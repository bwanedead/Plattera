# Prompt Observability

This document defines the target observability architecture for prompt-driven model behavior in the Plattera harness.

It exists to solve one diagnostic problem:

**when the model behaves in an unexpected way, we need to inspect exactly what it received, what it returned, and what the harness did with that result.**

This is core observability infrastructure, not optional polish.

---

## 1. Core Rule

If a model behavior matters enough to diagnose, the exact payload that produced it should be inspectable beside the outcome.

That means prompt observability must preserve:

- the canonical source prompt blocks
- the exact final assembled prompt for a given call
- the exact structured payloads attached to that call
- the model output for that call
- the downstream outcome caused by that output

---

## 2. Observability Layers

Prompt observability has four linked layers.

## 2.1 Source Prompt Observability

This answers:

- what canonical prompt blocks exist?
- what did we intend to say at each ownership layer?

It should expose:

- block ids or stable names
- ownership layer
- source file/module
- version or hash
- authored text

This is how a developer inspects the intended doctrine.

---

## 2.2 Prompt Event Snapshot Observability

This answers:

- what exact prompt/payload did this specific model call receive?

This is the core runtime snapshot layer.

It should expose:

- final assembled prompt text
- attached structured payloads
- source block provenance
- run / iteration / surface / model identity
- ordering/timestamp anchors

This is how a developer inspects the actual conditioning state for a specific call.

---

## 2.3 Outcome Observability

This answers:

- what did the model output?
- how was it parsed or validated?
- what execution or state change followed?

It should expose:

- raw model output
- parsed/validated output
- repair or rejection outcome if any
- downstream execution/result
- resulting refs/state delta summary

This is how a developer inspects the effect of the call.

---

## 2.4 Review / Aggregate Observability

This answers:

- what patterns exist across many calls or runs?

It should expose:

- run-level summaries
- cross-run review bundles
- partial-trace honesty
- linkage back to underlying prompt events

This is how broader diagnosis and regression analysis happen.

---

## 3. Prompt Event

The central runtime forensic object should be a **Prompt Event**.

A Prompt Event is the exact causal bundle for one substantive model call.

It should include:

- exact assembled prompt
- exact structured payloads
- source blocks used
- model output
- downstream outcome

Conceptually:

```json
{
  "prompt_event_id": "prompt_event:run123:i04:resolver",
  "run_link_id": "mission-row1-tx",
  "run_id": "mission-row1-tx",
  "iteration_index": 4,
  "surface": "tx_focus_resolver",
  "domain": "transcript_edit",
  "model": "gpt-5.4",
  "constitution_version": "v2",
  "source_blocks": {
    "harness_trunk": [
      {"id": "machine_identity", "version": "v1", "hash": "abc123"},
      {"id": "run_choreography", "version": "v1", "hash": "def456"}
    ],
    "domain_branch": [
      {"id": "transcript_doctrine", "version": "v1", "hash": "ghi789"}
    ],
    "surface_packet": [
      {"id": "focus_resolver_system", "version": "v3", "hash": "jkl012"}
    ]
  },
  "assembled_prompt": {
    "system_text": "...",
    "user_text": "...",
    "structured_payloads": {
      "run_progress_frame": {},
      "support_state": {},
      "rationale_continuity_strip": [],
      "focus_packet": {}
    }
  },
  "response": {
    "raw_text": "...",
    "parsed_output": {},
    "validation_status": "accepted"
  },
  "downstream_outcome": {
    "execution_state": "executed",
    "action_type": "TX_APPLY_EDIT_PLAN",
    "latest_refs": {},
    "state_delta_summary": {}
  }
}
```

This is illustrative, not the final implementation contract.

---

## 4. Required Prompt Event Fields

At minimum, a prompt event should carry the following categories.

### Identity

- `prompt_event_id`
- `run_link_id`
- `run_id`
- `iteration_index`
- `surface`
- `domain`
- `model`
- `constitution_version`

### Source provenance

- source block ids
- source block versions and/or hashes
- source file references when practical

### Final assembled payload

- exact final prompt text
- exact structured payloads attached

### Response

- raw model output
- parsed/validated output
- parse/repair status

### Downstream outcome

- execution/no-execution outcome
- action or move type
- latest refs
- resulting state delta or terminal delta summary

---

## 5. Source Blocks vs Prompt Events

These must remain distinct.

## 5.1 Source blocks

These are:

- reusable authored prompt text
- human-maintained
- the source-of-truth wording layer

Examples:

- harness trunk blocks
- domain branch blocks
- surface packet text blocks

## 5.2 Prompt events

These are:

- exact per-call runtime snapshots
- assembled from source blocks plus dynamic state

You need both because failures can happen in different places:

- bad source wording
- bad composition
- bad dynamic payload/state

If these are blurred together, diagnosis becomes guesswork.

---

## 6. Prose Doctrine vs State Payload

Prompt observability should keep doctrine and state distinct.

## 6.1 Prose doctrine

These are prompt-text layers:

- harness trunk
- domain branch
- surface packet

They should be logged and inspectable as prose source and final assembly.

## 6.2 State payload

These are structured carriers:

- run context
- structured state
- continuity summaries
- refs and artifacts

They should be logged and inspectable as structured state.

This separation matters because state payloads must not quietly become hidden prompt doctrine.

---

## 7. Capture Points

Prompt events should be captured:

1. after final prompt assembly
2. after structured payload injection
3. before model invocation

Then linked or updated after:

4. raw model response
5. parse/repair/validation outcome
6. downstream execution/result outcome

This avoids reconstructing the causal chain from scattered logs later.

---

## 8. Linkage To Existing Systems

Prompt observability should not become a disconnected parallel reporting system.

It must link to existing harness observability surfaces.

## 8.1 Linkage to trace

Prompt events should link cleanly to:

- run id
- loop family
- iteration index
- surface / phase
- canonical trace events where applicable

## 8.2 Linkage to run-state

Prompt events should be linkable to:

- `SharedRunStateEnvelope`
- active run posture
- continuity context

## 8.3 Linkage to review bundles

Review/reporting surfaces should be able to reference:

- prompt event ids
- prompt source block ids
- prompt-event-level anomalies if needed later

The goal is one canonical linkage chain, not flattened storage.

---

## 9. Repo Reality Today

The repo already has several relevant observability pieces.

### Existing source-prompt-ish layer

- [backend/agents/common/prompt_sources.py](/C:/projects/Plattera/backend/agents/common/prompt_sources.py)
- [backend/agents/common/prompt_observability.py](/C:/projects/Plattera/backend/agents/common/prompt_observability.py)
- [backend/agents/common/identity_composer.py](/C:/projects/Plattera/backend/agents/common/identity_composer.py)
- [backend/agents/transcript_edit/prompting.py](/C:/projects/Plattera/backend/agents/transcript_edit/prompting.py)

### Existing structured payloads

- [backend/harness/orchestration_kernel/run_progress_frame.py](/C:/projects/Plattera/backend/harness/orchestration_kernel/run_progress_frame.py)
- [backend/harness/tracing/rationale_continuity_strip.py](/C:/projects/Plattera/backend/harness/tracing/rationale_continuity_strip.py)

### Existing canonical trace layer

- [backend/harness/tracing/schema.py](/C:/projects/Plattera/backend/harness/tracing/schema.py)
- [backend/harness/tracing/builder.py](/C:/projects/Plattera/backend/harness/tracing/builder.py)
- [backend/harness/tracing/service.py](/C:/projects/Plattera/backend/harness/tracing/service.py)
- adapters under [backend/harness/tracing/adapters/](/C:/projects/Plattera/backend/harness/tracing/adapters)

### Existing run-state / review sidecars

- [backend/harness/run_state.py](/C:/projects/Plattera/backend/harness/run_state.py)
- [backend/harness/review/reporting.py](/C:/projects/Plattera/backend/harness/review/reporting.py)
- [backend/harness/review/tool.py](/C:/projects/Plattera/backend/harness/review/tool.py)

This means the repo already has much of the scaffolding needed for prompt observability.

---

## 10. Current Gaps

### 10.1 Missing unified prompt-event artifact

There does not appear to be one canonical per-call artifact for:

- final assembled prompt text
- attached structured payloads
- source block provenance
- response
- downstream outcome

### 10.2 Mixed prompt source ownership

[backend/agents/common/identity_composer.py](/C:/projects/Plattera/backend/agents/common/identity_composer.py) now owns assembly and provenance, while the shared trunk source and transcript-edit branch source have moved into dedicated source modules. A deed-to-IR compatibility branch still remains in the composer for now.

### 10.3 Uneven assembly wiring

`compose_identity_header()` is now the clearer shared assembly path for identity/header composition, but the repo still has separate surface builders that do not yet all share a single observability record.

### 10.4 Sidecar advisory drift risk

[backend/harness/tracing/rationale_continuity_strip.py](/C:/projects/Plattera/backend/harness/tracing/rationale_continuity_strip.py) contains `carry_forward_hint`, which is a likely semantic-drift seam.

---

## 11. Legacy / Parallel Observability Audit Requirement

Before or during implementation, classify existing observability outputs as:

- canonical active
- active sidecar
- compatibility-only
- vestigial

Likely surfaces to classify:

- canonical trace
- run_state envelope
- review bundle/reporting
- focus packet continuity payloads
- any persisted prompt or rationale artifacts
- CLI/testing inspection surfaces

The goal is not to collapse everything into one system.
The goal is to ensure one canonical linkage chain and avoid parallel reporting regimes that muddy diagnosis.

---

## 12. Hard Requirements

### 12.1 Final prompt reconstructability

Every substantive model call must be reconstructable as an exact prompt event.

### 12.2 Source provenance

Every prompt event must identify the source prompt blocks used.

### 12.3 Doctrine/state separation

Observability must preserve the distinction between:

- prose doctrine
- structured payload state

### 12.4 Human inspectability

A human must be able to inspect both:

- canonical source prompt blocks
- exact final prompt-event snapshots

### 12.5 Compatibility honesty

Any old prompt/trace/reporting path that is compatibility-only must be visibly marked and must not masquerade as the canonical observability path.

---

## 13. Main Watchpoints

### Hidden strategy in state payloads

Most likely current offender:

- `carry_forward_hint`

### Composer becoming a doctrine store

Prompt assembly logic must not become the place where wording proliferates.

### Payload duplication

Prompt-event capture should be exact, but should not create redundant observability copies with weak linkage.

### Parallel observability systems

Prompt observability must integrate with trace/review/run-state, not become an isolated fourth or fifth reporting regime.

---

## 14. Target Outcome

The repo should converge to an observability model where every substantive model call can be inspected as:

- canonical source blocks used
- exact assembled prompt text
- exact attached structured payloads
- exact model output
- exact downstream outcome

This should be inspectable alongside trace and run-review information.

That is the target observability architecture.

---

## 15. Current Code Scaffold

The first code-level prompt-observability scaffold now lives in:

- [backend/agents/common/prompt_observability.py](/C:/projects/Plattera/backend/agents/common/prompt_observability.py)

It currently defines:

- `PromptSourceBlockRef`
- `PromptEventMetadata`
- `build_prompt_event_metadata(...)`

The source/assembly boundary now also passes provenance through:

- [backend/agents/common/prompt_sources.py](/C:/projects/Plattera/backend/agents/common/prompt_sources.py)
- [backend/agents/common/identity_composer.py](/C:/projects/Plattera/backend/agents/common/identity_composer.py)

### Current watchpoint

- `carry_forward_hint` in [backend/harness/tracing/rationale_continuity_strip.py](/C:/projects/Plattera/backend/harness/tracing/rationale_continuity_strip.py) remains a live observability watchpoint. It should be treated as a continuity hint, not as tactical authorship.

---

## 16. Coverage Audit Snapshot

Primary substantive model-call surfaces in the active harness paths are currently:

| Surface | File | Prompt event | Source provenance | Final prompt text | Structured payload snapshot | Outcome linkage | Inspection path | Classification |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Controller next-step / refusal-repair proposal | [backend/agents/controller/controller_proposals.py](/C:/projects/Plattera/backend/agents/controller/controller_proposals.py) | yes | yes | yes | yes | yes | review bundle `runs[*].prompt_events` | canonical active |
| Transcript planner proposal / repair | [backend/agents/transcript_edit/planner.py](/C:/projects/Plattera/backend/agents/transcript_edit/planner.py) | yes | yes | yes | yes | yes | review bundle `runs[*].prompt_events` | canonical active |
| Transcript orient baseline | [backend/agents/transcript_edit/orient_tool.py](/C:/projects/Plattera/backend/agents/transcript_edit/orient_tool.py) | yes | yes | yes | yes | yes | review bundle `runs[*].prompt_events` | canonical active |
| Controller iteration digest summarizer | [backend/agents/controller/openai_client.py](/C:/projects/Plattera/backend/agents/controller/openai_client.py) | no | no | no | no | no | controller run-review summary only | active sidecar |

Notes:

- The controller proposal surface covers both the normal next-step call and the refusal-repair retry path.
- The iteration digest summarizer is an active utility sidecar, not a canonical prompt-event surface.
- If a new substantive model-call surface is added, it should be added to this table and to the inspection path immediately.

---

## 17. Canonical Human Inspection Path

The canonical human inspection path for prompt events is the review bundle emitted by
[backend/harness/review/tool.py](/C:/projects/Plattera/backend/harness/review/tool.py).

Use:

- `build_single_run_review_bundle(...)`
- `build_multi_run_review_bundle(...)`

These include:

- canonical trace
- run-state envelope
- review summary
- derived `prompt_events`

Trace, run-state, and review summaries remain linked context. They are not a replacement for the prompt-event snapshot itself.

---

## 18. Payload Hygiene Classification

The following structured-state surfaces are currently acceptable:

| Surface | Classification | Note |
| --- | --- | --- |
| `run_progress_frame.run_posture.prompt_event_count` / `last_prompt_event_id` / `last_prompt_event_surface` | descriptive and acceptable | Mechanical observability counters and anchors. |
| `rationale_continuity_strip.carry_forward_hint` | watchpoint | Still a live continuity hint; acceptable only while it stays observational and non-prescriptive. |
| `run_state.prompt_observability_summary` | descriptive and acceptable | Derived observability summary, not doctrine. |
| `review.reporting.prompt_event_count` / `prompt_event_surfaces` / `prompt_event_outcomes` | descriptive and acceptable | Aggregate review signals, not canonical state. |

No current structured payload field is considered out of bounds, but `carry_forward_hint` should remain under active review if future changes begin to read like advice or tactics.

---

## 19. Transitional Residue Classification

Current observability-adjacent surfaces classify as follows:

- `backend/agents/common/prompt_sources.py` - canonical active
- `backend/agents/common/prompt_observability.py` - canonical active
- `backend/agents/common/identity_composer.py` - canonical active, with a narrow compatibility seam still present for deed-to-IR branch composition
- `backend/agents/deed_to_ir/prompt_sources.py` - active compatibility branch source
- `backend/harness/review/tool.py` - canonical active inspection surface
- `backend/harness/review/reporting.py` - active aggregate sidecar
- `backend/harness/run_state.py` - canonical active structured-state summary layer

Compatibility-only or legacy surfaces must stay visibly secondary and should not be treated as the primary observability model.
