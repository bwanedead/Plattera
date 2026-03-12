# Trace Normalization and Adapter Design

Date: 2026-03-11
Status: Phase 4 design contract (implementation-facing)
Program references:
- `docs/architecture/migration/harness-convergence-roadmap.md`
- `docs/architecture/harness/canonical-trace-schema.md`
- `docs/architecture/harness/transcript-edit-state-authority.md`

## Purpose

Define how Plattera turns current run observability artifacts into canonical traces without rewriting loop runtimes.

This document resolves:
- where normalization logic should live
- how current artifacts map into canonical schema
- what the first safe implementation slice is

## A) Source Inventory

| Source | Owner and module | Current persistence | Fidelity and limits | Canonical fields it can populate |
| --- | --- | --- | --- | --- |
| Controller transcript events | `backend/agents/controller/controller_transcript.py` and `controller_runtime_loop.py` | JSON file under `agent_kernel_artifacts_root()/controller_transcripts/<request_id>/...json` | Bounded to max events and byte caps; includes truncation markers and bounded payload | `request_start`, `iteration`, `model_proposal`, `tool_execution`, `retrieval_evidence`, `terminal_outcome`, `reason_code`, `phase`, `event timestamp` |
| Kernel step records and idempotency ledger | `backend/agent_kernel/session.py`, `backend/agent_kernel/run_artifact.py` | Run artifact JSON via `RunArtifactPersistenceService` at `dossiers_data/artifacts/agent_kernel/<request_id>/<run_id>.json` (+ index in `dossiers_data/state/agent_kernel_runs_index.json`) | Durable and structured; no explicit canonical trace ordering metadata; some context only appears in caller transcript layer | `run/session identity`, `tool_execution`, `action_type`, `step_id`, `refusal`, `terminal`, `latest refs reconstruction`, budget context |
| Kernel dashboard/latest refs snapshots | Produced in `session.py`, consumed by controllers | Runtime step results and embedded transcript payload summaries; final run snapshot in tx registry | High signal but not separately persisted per step outside transcript/event payloads | `refs_delta`, `verification context`, `failure classification`, `request metadata` |
| Transcript-edit progress events | `backend/agents/transcript_edit/controller.py` + `run_reporting.py`; persisted by API endpoint | Stored in run registry snapshot (`transcription_edit_runs_index.json`) as `progress_log` (bounded 40) and `critical_events` (bounded 200) | Not full unbounded history in registry; critical events intentionally preserved; ordering implicit by append sequence | `request_start`, `iteration`, `model_proposal`, `tool_execution`, `verification`, `hitl_escalation`, partial `blocker_transition`, `phase`, `reason_code` |
| Blocker registry lifecycle transitions | `backend/agents/transcript_edit/blocker_registry_lifecycle.py` and views | Present in `runtime_hitl_state.blocker_registry` snapshots, including `rows`, `history`, `counts` | Snapshot-first view with bounded history; strong lifecycle semantics per Phase 3 authority split | `blocker_transition`, `hitl_escalation` linkage, blocker envelope fields (`blocker_kind`, `blocking_impact`, `state`, `next_valid_actions`) |
| Decision-ledger closure transitions | `backend/agents/transcript_edit/decision_ledger_*` | Snapshot payloads via `ledger_snapshot_for_payload(...)` embedded in progress details and terminal summary | Closure truth is authoritative, but transition history is partly reconstructed from progress phases/snapshots | closure-related `blocker_transition` context, `verification`/closure state summaries, source completeness metadata |
| Terminal summaries and run results | `backend/agents/transcript_edit/terminalization.py`; controller terminal in runtime loop | tx final snapshot (`terminal_summary`, status/reason); controller terminal in `ControllerRunResult` and transcripts | High value summary layer; derives from prior events and runtime state; should remain projection, not authority | `terminal` object, terminal class/reason mapping inputs, iteration count, final verification and blocker state summaries |
| Handoff packet (tx) | `backend/agents/transcript_edit/handoff_packet.py` | JSON file at `dossiers_artifacts_root()/transcript_edit_handoffs/<dossier>/<run_id>.json` | Post-run curated packet; not full timeline | supplemental terminal context, unresolved blocker summaries, evidence refs, cross-surface linkage |

### Source-level observations

- Controller family already has durable timeline (`transcript`) + durable execution ledger (`run artifact`).
- Transcript-edit family has durable bounded timeline in run registry, plus durable kernel artifact refs and handoff packet.
- Transcript-edit blocker and closure semantics must respect Phase 3 authority:
  - closure truth: decision ledger
  - blocker/escalation lifecycle truth: blocker registry

## B) Adapter Architecture

## Options evaluated

1. One central trace assembler module consuming all sources for all loops.
- Pros: single entrypoint.
- Cons: high monolith risk; loop/source coupling accumulates in one file.

2. Per-loop-family adapters into a shared canonical builder.
- Pros: loop semantics stay local; shared contract enforcement centralized; scales with new loop families.
- Cons: requires clear shared builder boundaries.

3. Per-source adapters with one final merger.
- Pros: source reuse.
- Cons: ordering and ownership become hard; final merger trends monolithic.

## Chosen approach: Hybrid of option 2 with small source normalizers

- Primary adapters are per loop family:
  - `controller_kernel` adapter
  - `transcript_edit` adapter
- Each family adapter can use tiny source normalizers internal to that family adapter package.
- One shared canonical builder layer owns:
  - schema validation
  - event id/index assignment
  - timestamp normalization policy enforcement
  - event envelope assembly (contract-level only)
  - bounded payload mechanics (size/shape caps only)
  - completeness/warning metadata

### Recommended module boundaries

Proposed package (new, implementation phase):
- `backend/harness/tracing/schema.py`
  - canonical trace typed contract + version constants
- `backend/harness/tracing/builder.py`
  - shared helpers: event shaping, ordering, indexing, warnings/completeness
- `backend/harness/tracing/adapters/controller_kernel.py`
  - maps controller transcript + kernel run artifact
- `backend/harness/tracing/adapters/transcript_edit.py`
  - maps tx run snapshot + kernel refs + terminal summary
- `backend/harness/tracing/storage.py` (optional in first slice)
  - sidecar persistence/index helpers for canonical trace exports

Anti-monolith rule:
- no single `trace_utils.py` or cross-family “god adapter.”
- loop-family adapters own source interpretation and family payload semantics; shared builder owns only canonical contract mechanics.

## C) Canonical Trace Assembly Model

## Minimum required inputs by family

Controller/kernel trace:
- controller transcript artifact ref (required)
- kernel run artifact ref (strongly recommended; optional fallback if unavailable)
- request/run identifiers from transcript header or run artifact

Transcript-edit trace:
- run registry entry snapshot (`progress_log`, `critical_events`, terminal fields)
- runtime HITL state snapshot (for blocker registry and escalation state)
- ledger snapshot source (from progress event `detail.decision_ledger` and/or `terminal_summary.decision_ledger`) when emitting closure-derived canonical fields
- optional kernel run artifact ref from snapshot (for step-level enrichment)

Authority rule for transcript-edit adapter:
- closure-related canonical fields must come from decision-ledger snapshots only.
- blocker/escalation lifecycle fields come from blocker registry lifecycle snapshots/events.
- terminal or registry projections must not be used to invent closure truth when ledger snapshot is absent; emit partial trace with warnings instead.

## Assembly order

1. Build top-level skeleton (`trace_id`, `run_id`, `session_id`, `loop_family`, `trace_version`).
2. Ingest source events into intermediate canonical candidates with `source_origin`.
3. Normalize event kinds and payload bounds.
4. Determine stable ordering and assign `event_index`.
5. Attach terminal snapshot and completeness metadata.
6. Validate required fields; emit warnings for missing optional sources.

## Ordering and indexing rules

Canonical ordering key:
1. `timestamp_epoch_seconds` if present
2. source-sequence fallback (append order in source artifact)
3. source-priority tie-breaker (`request_start` and bootstrap events first)

Timestamp policy:
- canonical `timestamp_epoch_seconds` is required for all events.
- if source timestamp is missing, adapter must derive a deterministic timestamp from run start + source sequence and set `payload.timestamp_source` to `derived_sequence`.

`event_index`:
- always reassigned by canonical builder after sort.
- monotonic starting at 0 for each trace.

`event_id`:
- deterministic local id: `<trace_id>:e<event_index_padded>`.

## Raw source linkage

Every canonical event includes source linkage in payload metadata:
- `source_origin.kind` (`controller_transcript`, `kernel_step_record`, `tx_progress`, `tx_critical`, `tx_blocker_registry`, `tx_terminal_summary`)
- `source_origin.ref` (artifact path, run_id, or registry run id)
- `source_origin.local_id` (e.g., `step_id`, prompt id, blocker id, source list index)

Raw linkage is mandatory even when canonical payload is synthesized.

## Partial traces without false completeness

Top-level fields:
- `completeness_status`: `complete` or `partial`
- `missing_components`: list of missing source categories
- `normalization_warnings`: bounded warning list

Rules:
- if source history is capped/truncated (e.g., tx `progress_log`), mark `partial`.
- never fabricate missing blocker/escalation history; synthesize only with explicit `payload.synthesized=true`.
- if required closure source (decision-ledger snapshot) is missing, closure-derived fields are omitted and noted in `missing_components`/`normalization_warnings`.

## Terminal attachment

Terminal snapshot is attached once at top-level `terminal`.
- Controller family: map `TerminalOutcome` and stop reason.
- Transcript-edit family: map status/reason plus derived class using shared taxonomy mapping rules.

## Blocker and escalation representation by family

Transcript-edit:
- blocker lifecycle events originate from blocker registry lifecycle/history and blocker recap events.
- closure-blocking context originates from decision ledger snapshots (Phase 3 authority compliant).
- HITL events originate from progress phases and registry/ticket linkage.

Controller/kernel:
- initial blocker/escalation events are synthesized from deterministic refusal/stop contexts.
- synthesized events must set:
  - `payload.synthesized=true`
  - source reason code and originating action context
- controller-family remains blocker-light in first implementation slice.

## D) Mandatory First Implementation Slice

## Chosen first slice

Read-only canonical trace adapters for both loop families from existing persisted artifacts, with schema tests and no runtime loop rewrites.

Why this slice:
- low risk: no behavior change in controller/kernel or transcript-edit loops
- proves canonical schema across both families immediately
- validates ordering, linkage, and partial-trace handling on real artifacts
- avoids premature new tracing pipeline/runtime emitter work

What is in scope for first slice:
- adapter modules and shared builder
- fixture-backed tests for both loop families
- optional on-demand export helper (CLI/service function)

What is out of scope:
- replacing existing runtime event emission
- mandatory persistent canonical trace store for all runs
- broad API contract changes

## E) Raw vs Canonical Retention Policy

Retention baseline:
- raw artifacts remain authoritative and retained in current stores:
  - controller transcripts
  - kernel run artifacts
  - tx run registry snapshots
  - tx handoff packets
- canonical trace is a normalized derivative record.

Linking policy:
- canonical trace must retain pointers to raw sources for replay/debug.
- raw payload deep details are not duplicated wholesale in canonical events.

Search policy:
- search/index primarily over canonical dimensions (event kind, terminal class, reason code, blocker fields, loop family, iteration count).
- reconstruct deep details by following canonical `source_origin` pointers back to raw artifacts.

## F) Versioning and Compatibility

Version fields:
- `trace_version`: canonical schema version (start `trace.v1`).
- `adapter_version`: adapter implementation version per family (start `v0`).

Compatibility rules:
- additive fields are allowed within same `trace_version`.
- semantic meaning changes require new `trace_version`.
- adapters must set `completeness_status=partial` for historical runs missing required source categories.

Historical-run handling:
- adapter must tolerate absent fields/artifacts without failing trace build.
- missing sources become warnings + `missing_components` entries.

Future richness expansion:
- enrich payloads/events incrementally while preserving existing event kinds and field semantics.
- avoid breaking downstream analysis by preserving old fields and adding new optional fields.

## Open implementation questions

- Should first-slice exports be on-demand only, or also persisted as sidecars under `dossiers_data/artifacts/harness_traces/`?
- Where should canonical trace retrieval be surfaced first: internal service API or developer CLI?
- How aggressively should controller synthesized blockers be expanded before controller becomes blocker-native?
