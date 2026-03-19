# Harness Decision Ledger (generic organized work)

Date: 2026-03-19  
Status: **Converging** — single harness-owned decision ledger is the **primary runtime read** direction; transcript-edit native JSON remains the **mutation/persistence** store; a few ancillary paths may still migrate  
Related: `docs/architecture/harness/target-harness-v1.md`, `docs/architecture/harness/minimal-shared-run-state-envelope.md`

## Purpose

There is **one** mission-agnostic harness surface for durable, inspectable work items:

- **Canonical name:** decision ledger (`backend/harness/decision_ledger/`).
- **Wire envelope (v1):** same JSON shape as `work_board.v1` (`backend/harness/work_board/contracts.py`) during migration.
- **Domains** (e.g. transcript-edit) **project** native stores into ledger rows; they do **not** define harness field semantics or a second parallel “real” ledger.

Transcript-edit retains a **native checklist JSON** in loop state (`state.decision_ledger`) for **persistence and mutation** (updates, tickets, orient baseline). **Operational runtime reads** (closure, registry sync, focus/repair/controller gates, HITL runtime snapshots) should use:

1. **Unified envelope** — `build_transcript_edit_unified_decision_ledger` (projection + emergent + notes), or
2. **Closure read ledger** — `transcript_edit_closure_read_ledger`: checklist-shaped `items` are **reconstructed from the unified envelope** (`te:ledger:*`); top-level fields not carried on the envelope (e.g. `external_context_injections`, `scope_summaries`, `source_completeness`) are **copied from the native dict**. Writes still go to `state.decision_ledger` only.

**Prefer one helper** — `transcript_edit_unified_and_closure_read_for_native` / `transcript_edit_unified_and_closure_read_from_loop_state` — instead of re-wiring `build_*` + `transcript_edit_closure_read_ledger` at each call site.

Some API/payload paths may still pass `ledger_snapshot_for_payload(state.decision_ledger)` for **wire compatibility** with the persisted native shape; that is not the same as using the native `items` list directly for closure/blocking decisions.

Default deed-slot **bootstrap** (township/range/section, …) lives in `transcript_edit_default_checklist_seed.py`. It may **seed** native rows and supply **domain tie-break ordering** (via `TRANSCRIPT_EDIT_DOMAIN_SLOT_PRIORITY` on the adapter). It is **not** the harness ontology and must not be treated as the canonical organized-work read surface.

## Generic ledger item (contract)

Fields (JSON-serializable): `item_id`, `title`, `kind`, `state`, `priority`, `materiality`, `blocking_impact`, `dependencies`, `evidence_refs`, `alternatives`, `resolution_condition`, `scope`, `summary`, `notes`, `context_notes`, `provenance`, `domain_payload`.

**Rule:** No PLSS or deed-specific harness slots; domain specifics live in `domain_payload` and in domain-chosen `kind` strings.

Lifecycle states (v1): `open`, `investigating`, `narrowed`, `blocked`, `waiting_human`, `waiting_evidence`, `answered_pending_integration`, `resolved`, `superseded`.

## Transcript-edit adapter

- **Projection:** `work_board_projection.project_decision_ledger_to_work_board` maps native checklist rows → generic ledger items (`te:ledger:<key>`).
- **Unified read surface:** `decision_ledger_adapter.build_transcript_edit_unified_decision_ledger`.
- **Closure/read model:** `decision_ledger_adapter.transcript_edit_closure_read_ledger`.
- **Combined read entrypoint:** `transcript_edit_unified_and_closure_read_for_native` / `transcript_edit_unified_and_closure_read_from_loop_state` (focus packet, repair loop, domain pack, controller orient/audit/HITL).
- **Focus selection:** `choose_investigation_focus` accepts the unified envelope alone (or legacy `ledger` + envelope during migration). Domain slot ordering for tie-breaks is `TRANSCRIPT_EDIT_DEFAULT_SLOT_PRIORITY` in the seed module (re-exported as `TRANSCRIPT_EDIT_DOMAIN_SLOT_PRIORITY` from the adapter).

## Recent iteration lane

`build_recent_iteration_lane` (`backend/harness/work_board/recent_iteration_lane.py`) thickens continuity from bounded `continuity_log` steps, not full history.

## Execution context (model-facing)

`focus_packet.execution_context` includes `active_work_item`, `work_board_focus_context`, `recent_iterations`, etc.

**Compatibility:** `focus_packet.work_board` is the unified ledger envelope (historical field name).

## Emergence, lifecycle, authority

- Emergence ops: `harness.work_board.emergence` (`propose_work_board_changes` / `work_board_changes[]` in API — field name unchanged).
- Lifecycle helpers: `harness.work_board.lifecycle`.
- Authority policy: `focus_authority_policy` (explicit modes; applies on the unified ledger).

## Anti-goals (resolved)

- No permanent **two** co-equal ledger-like surfaces for “real” vs “display” work.
- No transcript-edit deed checklist as the harness ontology; harness ledger stays generic; checklist is adapter/projection input.
