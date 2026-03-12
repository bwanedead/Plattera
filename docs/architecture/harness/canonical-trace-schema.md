# Canonical Trace Schema

Date: 2026-03-11
Status: Phase 2 shared contract (definition only)
Program references:
- `docs/architecture/migration/harness-convergence-roadmap.md`
- `docs/architecture/harness/target-harness-v1.md`
- `docs/architecture/harness/trace-normalization-and-adapter-design.md`

## Purpose

Define one Plattera-native trace schema that both loop families can emit into without semantic ambiguity.

This contract is for internal harness observability and analysis. It does not require LangSmith or any third-party observability product.

## What a Trace Is (and Is Not)

In Plattera terms:
- Trace: canonical per-run record for cross-loop analysis and migration convergence.
- Child step/event: one trace entry representing a meaningful run event.
- Transcript: loop-family specific narrative/event stream (controller transcript, tx viewer progress stream).
- Logs: operational text logs for debugging and runtime operations.
- Telemetry: counters/timers/distributions derived from traces/logs.
- Eval: scored judgments over traces/outcomes, usually cross-run.

Relationship:
- Transcript and step records are input sources.
- Trace is the normalized contract layer.
- Telemetry/evals are downstream products.

## Trace Record Contract (Top-Level)

Required fields:
- `trace_id`: stable id for this canonical trace record.
- `run_id`: primary run identifier.
- `session_id`: execution session id when present (conditionally required for sessionized runs).
- `request_id`: initiating request id when available.
- `loop_family`: `controller_kernel` or `transcript_edit` (extendable enum).
- `request_metadata`: bounded request context (objective, trigger, initiating surface).
- `start_context_summary`: bounded summary of initial context and bootstrap refs.
- `started_at_epoch_seconds`: trace start timestamp.
- `events`: ordered list of canonical child events.
- `terminal`: canonical terminal snapshot (status class + reason context).
- `completeness_status`: `complete` or `partial`.
- `missing_components`: list of source components absent during normalization.
- `normalization_warnings`: bounded warning list describing truncation, synthesis, or fallback behavior.
- `trace_version`: schema version identifier.

Optional but strongly recommended:
- `source_artifact_refs`: key refs available at start.
- `budgets`: run/session budget snapshot.

## Child Event Contract (Required)

Each `events[]` entry must include:
- `event_id`: stable unique id within trace.
- `event_index`: monotonic order index.
- `timestamp_epoch_seconds`: event timestamp.
- `event_kind`: canonical category (see below).
- `phase`: loop phase label when available.
- `iteration_index`: iteration number when available.
- `actor`: `model`, `controller`, `kernel`, `tool`, `harness`, or `human`.
- `status`: bounded execution state (for example `started`, `completed`, `refused`, `waiting`, `failed`).
- `reason_code`: stable reason/refusal code when available.
- `refs_delta`: bounded changed refs snapshot when available.
- `payload`: bounded event details specific to `event_kind`.

## Canonical Event Categories

Required supported `event_kind` categories:
- `request_start`
- `iteration`
- `model_proposal`
- `tool_execution`
- `retrieval_evidence`
- `blocker_transition`
- `verification`
- `hitl_escalation`
- `terminal_outcome`

Category notes:
- `iteration` events may represent start/end checkpoints.
- `tool_execution` includes kernel step executions and deterministic refusal outcomes.
- `blocker_transition` is required for blocker-native loops and optional synthesized projection for non-blocker-native loops.
- `hitl_escalation` includes prompt issued, feedback received, feedback consumed, and stale/superseded transitions.

## Searchable Dimensions

Canonical traces should expose these dimensions for downstream search/index systems:
- `loop_family`
- `terminal_class`
- `terminal_reason_code`
- `event_kind`
- `action_type`
- `blocker_kind`
- `blocking_impact`
- `blocker_state`
- `human_escalation_state`
- `verification_present`
- `iteration_count`
- `reason_code`
- `request_metadata.objective_type` (or nearest equivalent)

## Current Sources and Mapping

## Controller/kernel family

Current trace ingredients:
- controller transcript events (`controller_transcript.py`)
- kernel step records and refusals (`session.py`, `run_artifact.py`)
- dashboard snapshots (`latest_refs`, `failure_classification`, claimability)
- terminal outcome (`TerminalOutcome`, `StopReason`)

Mapping guidance:
- transcript `run_header` -> `request_start`
- proposal/refusal parse events -> `model_proposal`
- `kernel_step_result` -> `tool_execution`
- retrieval degradation events -> `retrieval_evidence`
- no-progress and refusal streak stops -> `terminal_outcome` with exhaustion/failure mapping
- periodic summary snapshots -> `iteration` with bounded continuity metadata

## Transcript-edit family

Current trace ingredients:
- progress/event emissions (`run_reporting.py`, viewer envelope in API)
- decision ledger closure transitions
- blocker registry transitions (`open`, `waiting_feedback`, `answered_unintegrated`, etc.)
- terminal summary/classification (`terminalization.py`)

Mapping guidance:
- starting/preflight -> `request_start` and `iteration`
- resolver/model stages -> `model_proposal`
- kernel `TX_*` step results -> `tool_execution`
- image/open spans checks -> `verification` or `retrieval_evidence` depending on intent
- blocker registry lifecycle changes -> `blocker_transition`
- human feedback lifecycle events -> `hitl_escalation`
- terminal summary payload -> `terminal_outcome`

## Mandatory Day-One vs Partial Initial Emission

Mandatory from day one:
- top-level identity fields (`trace_id`, `run_id`, `loop_family`, `events`, `terminal`, `trace_version`)
- canonical event ordering (`event_index`)
- event categories for start, proposal, tool execution, and terminal outcome
- terminal class + reason code

Allowed partial initially:
- synthesized blocker transitions for controller-family loops
- full verification/evidence detail richness
- full refs delta on every event
- complete HITL linkage fields in non-HITL runs

Rule:
- schema shape stays stable while event richness increases incrementally.

## Open Questions

- Do we need a stricter adapter target for `session_id` population coverage across loop families?
- Which controller transcript events should be normalized vs retained as raw payload attachments?

