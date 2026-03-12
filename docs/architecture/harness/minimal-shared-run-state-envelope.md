# Minimal Shared Run-State Envelope

Date: 2026-03-11
Status: Phase 2 shared contract (definition only)
Program references:
- `docs/architecture/migration/harness-convergence-roadmap.md`
- `docs/architecture/harness/target-harness-v1.md`

## Purpose

Define the minimum shared run-state/continuity envelope required across loop families.

This is intentionally not a full canonical run ledger. It is the smallest weight-bearing shared state needed for resumability, observability, and convergence.

## Minimum Shared Envelope (Required Fields)

Required top-level fields:
- `identity`: `run_id`, `session_id` (if present), `request_id`, `loop_family`.
- `objective`: bounded request/objective metadata.
- `latest_refs`: current working artifact refs snapshot.
- `blocker_summary`: unresolved blocker counts/status by `blocker_kind`, `blocking_impact`, and waiting state.
- `verification_summary`: latest verification posture (performed/missing, key reason context).
- `progress_summary`: current phase, iteration index, last significant reason code.
- `resumability`: `resumable` bool, `resume_reason`, `resume_requirements`.
- `terminal_snapshot`: terminal class/reason when closed, else null.
- `updated_at_epoch_seconds`: last envelope update timestamp.

Required design properties:
- bounded payload size
- refs-not-blobs
- additive extension support per loop family

Migration note:
- `blocker_summary` may be a derived projection (from refusals, failure classification, and terminal context) until explicit blocker records are adopted in a loop family.

## Current-State Mapping

## Controller/kernel family

Likely mappings from existing data:
- `identity`: start request/session/run ids
- `objective`: kernel goal + request metadata
- `latest_refs`: dashboard latest refs
- `blocker_summary`: derived from refusal/failure classification until explicit blockers exist
- `verification_summary`: claimability + gap summary + validation/terminal reason context
- `progress_summary`: phase hint + recent trace + last refusal/outcome
- `resumability`: derived from stop reason / refusal retryability
- `terminal_snapshot`: `TerminalOutcome`

Current continuity ingredients already present:
- bounded `run_summary_log`
- recent digest memory
- persisted controller transcript and periodic controller summary refs

## Transcript-edit family

Likely mappings from existing data:
- `identity`: run/session/request ids
- `objective`: run request + mode/trigger context
- `latest_refs`: loop state latest refs / terminal summary latest refs
- `blocker_summary`: blocker registry counts + active blocker + unresolved closure requirements
- `verification_summary`: audit/image verification status + layer status context
- `progress_summary`: iteration, phase, last reason, focus key
- `resumability`: pending feedback prompt and waiting-feedback ownership
- `terminal_snapshot`: status/reason/terminal_classification/closure_state

Current continuity ingredients already present:
- `TranscriptEditLoopState`
- decision ledger + blocker registry + HITL lifecycle state
- terminal summary payload

## Intentionally Deferred (Not Baseline)

Deferred to later phases:
- unified giant run ledger object
- full per-event history inside run-state envelope (trace owns that)
- domain-heavy closure internals as shared baseline fields
- full policy/action plan state machines

## Extensions vs Shared Baseline

Keep as extension fields (not required baseline):
- transcript scope proofs and per-decision closure details
- controller repair skeleton internals and proposal-debug payloads
- detailed per-check image verification diagnostics

Rule:
- if a field is required only by one loop family and not needed for cross-family resumability/observability, it remains an extension.

## Why This Supports Convergence

This envelope is enough to:
- resume safely with clear waiting requirements
- expose comparable run status across loop families
- support terminal taxonomy and blocker envelope mapping
- avoid premature monolithic state abstraction

## Open Questions

- Which resumability requirements should be normalized first (`prompt_id`, dependency ticket, capability gap)?
- Should `verification_summary` include a mandatory enum or remain a bounded structured object initially?
- Which controller refusal contexts should be promoted from derived blocker summaries into explicit blocker records?

