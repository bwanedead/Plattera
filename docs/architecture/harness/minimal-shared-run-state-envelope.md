# Minimal Shared Run-State Envelope

Date: 2026-03-11
Status: Phase 2 shared contract (definition only)
Program references:
- `docs/architecture/migration/harness-convergence-roadmap.md`
- `docs/architecture/harness/target-harness-v1.md`

## Purpose

Define the minimum shared run-state/continuity envelope required across loop families.

This is intentionally not a full canonical run ledger. It is the smallest weight-bearing shared state needed for resumability, observability, and convergence.

The canonical shared contract now has two nested surfaces:

- `mission_state`: top-level continuity, identity, posture, and bounded run summaries
- `resolution_state`: the active organized-work surface inside `mission_state`

Legacy names such as `work_board` and `decision_ledger` remain compatibility projections during migration.

## Minimum Shared Envelope (Required Fields)

Required top-level fields:
- `identity`: `run_id`, `session_id` (if present), `request_id`, `loop_family`.
- `objective`: bounded request/objective metadata.
- `latest_refs`: current working artifact refs snapshot.
- `blocker_summary`: unresolved blockage counts/status and waiting state, kept generic rather than ontology-specific.
- `verification_summary`: latest verification posture (performed/missing, key reason context).
- `progress_summary`: current phase, iteration index, last significant reason code.
- `resumability`: `resumable` bool, `resume_reason`, `resume_requirements`.
- `terminal_snapshot`: terminal class/reason when closed, else null.
- `updated_at_epoch_seconds`: last envelope update timestamp.
- `mission_mode_summary`: bounded mission-mode read model (`active_mode`, `mode_history`, latest transition reason, bounded resume context summary) when available.

Required design properties:
- bounded payload size
- refs-not-blobs
- additive extension support per loop family

Migration note:
- `blocker_summary` may be a derived projection (from refusals, failure classification, and terminal context) until explicit blocker records are adopted in a loop family.

## Current-State Mapping

The current runtime already has enough pieces to project into the new contract:

- `mission_state` maps from the existing run-state summaries, mission ledger continuity, and family posture fields.
- `resolution_state` maps from the current organized-work/read surfaces where they exist, plus bounded active-item continuity.
- `resolution_state.items` carries the generic item rows previously expressed through `work_board` / `decision_ledger`.
- lightweight item relations are a separate generic surface, not a graph engine.
- `active_item_id` lives on `resolution_state` and is a continuity rail, not a deterministic chooser.

Compatibility rule:

- `work_board` and `decision_ledger` are still allowed as wire/module aliases, but they are no longer the target architecture vocabulary.

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

Mission-runtime note:
- For `loop_family=mission_runtime`, `mission_mode_summary` is first-class and should stay read-model oriented.
- Do not mirror full mission ledger internals or mode-local domain ledgers into shared run-state.

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

