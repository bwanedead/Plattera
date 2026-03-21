# Harness Decision Ledger (generic organized work)

Date: 2026-03-19  
Status: **Converging** — single harness-owned decision ledger is the **primary runtime read** direction; transcript-edit native JSON remains the **mutation/persistence** store; **Phase 17** default startup is **discovery-native** (no pre-authored checklist items); optional full checklist via ``initialize_decision_ledger_with_domain_template_seed``; composition **v5** carries ``ledger_establishment_mode`` / ``initial_ledger_source``; vestigial placeholder ``discovery_ledger_merge_hook_placeholder`` **removed** (use merge helpers); agent-kernel ``run_kernel`` remains **active compatibility** per ``backend/agent_kernel/COMPATIBILITY.md`` — all domain-local except noted; harness contract unchanged  

**Phase 18 (end-state framing, not migration diary):**  
- **One** organized-work read model: unified harness **decision ledger** envelope (`work_board.v1` = stable wire name for that envelope).  
- Transcript-edit **native** `state.decision_ledger` is a **write/persistence seam** (plus domain-only row extensions like `discovery_meta`); it does not conceptually own closure/focus/packet reasoning.  
- **Naming:** prefer “decision ledger” in prose; `work_board` in APIs/packets is the historical field/wire id for the same envelope.  
- **Domain policy** = doctrine, templates, heuristics — not a hidden default work universe; discovery-first remains default.  
- **Agent kernel:** `KernelSessionManager` = canonical; `run_kernel` + `cli` = compatibility (see `COMPATIBILITY.md`).

**Phase 19 (operational convergence):** transcript-edit iteration facade (`iteration_pipeline.py`) delegates clean/repair work directly to `iteration_repair_runtime.py` (removed redundant clean-flow hop); prefer `from agent_kernel import KernelSessionManager` in touched paths; native JSON snapshots for API (`ledger_snapshot_for_payload`) are explicitly wire-only — unified envelope remains the read model for reasoning.

**Phase 20 (run-centric persistence):** logical **run id** (e.g. `tx-agent-{uuid}`) is the stable key for run-feed / recent-runs; kernel **session id** is subordinate. Recent runs dedupe by logical `run_id` so HITL resume does not multiply top-level history rows. Per-run diagnostic JSON is written under `run_feed/diagnostics/`. Kernel step idempotency remains on the persisted `RunArtifact` for that session only — not across fresh runs.

Related: `docs/architecture/harness/target-harness-v1.md`, `docs/architecture/harness/minimal-shared-run-state-envelope.md`

## Purpose

There is **one** mission-agnostic harness surface for durable, inspectable work items:

- **Canonical name:** decision ledger (`backend/harness/decision_ledger/`).
- **Wire envelope (v1):** same JSON shape as `work_board.v1` (`backend/harness/work_board/contracts.py`) during migration.
- **Domains** (e.g. transcript-edit) **project** native stores into ledger rows; they do **not** define harness field semantics or a second parallel “real” ledger.

Transcript-edit retains a **native checklist JSON** in loop state (`state.decision_ledger`) for **persistence and mutation** (updates, tickets, orient baseline). **Operational runtime reads** (closure, registry sync, focus/repair/controller gates, HITL runtime snapshots) should use:

1. **Unified envelope** — `build_transcript_edit_unified_decision_ledger` (projection + emergent + notes), or
2. **Closure read ledger** — `transcript_edit_closure_read_ledger`: checklist-shaped `items` are **reconstructed from the unified envelope** (`te:ledger:*`); top-level fields not carried on the envelope (e.g. `external_context_injections`, `scope_summaries`, `source_completeness`) are **copied from the native dict**. Native-only row extensions (e.g. transcript-edit `discovery_meta`) are **overlaid from the native `items[]` by key** so packets/focus see durable discovery lineage without encoding it into generic `domain_payload`. Writes still go to `state.decision_ledger` only.

**Prefer one helper** — `transcript_edit_unified_and_closure_read_for_native` / `transcript_edit_unified_and_closure_read_from_loop_state` — instead of re-wiring `build_*` + `transcript_edit_closure_read_ledger` at each call site.

Some API/payload paths may still pass `ledger_snapshot_for_payload(state.decision_ledger)` for **wire compatibility** with the persisted native shape; that is not the same as using the native `items` list directly for closure/blocking decisions.

Default deed-slot **bootstrap** (township/range/section, …) lives in `transcript_edit_default_checklist_seed.py` and only **initializes** native rows. **Tie-break ordering hints** live in `transcript_edit_bootstrap_hints.py` (`TRANSCRIPT_EDIT_SLOT_PRIORITY_HINTS`), re-exported from the adapter as `TRANSCRIPT_EDIT_DOMAIN_SLOT_PRIORITY`. Neither module is the harness ontology or the canonical organized-work read surface.

**Discovery-first (Phase 11–12 — runtime):** `transcript_edit_ledger_discovery_prep.py` implements a **bounded** merge into the native `decision_ledger.items[]` (not harness ontology):

- **Merge helpers:** `merge_discovered_native_items` (validated rows), `merge_discovery_from_audit_findings` (infer from audit findings + merge). Wired after `update_ledger_from_iteration` in transcript-edit orient/update paths (e.g. domain pack, controller). Optional `merge_stats` records adds, evidence-only merges, semantic de-dupe, and caps for continuity rows (`append_discovery_merge_continuity`).
- **Identity:** `key` = `discovery:<kind>:<fingerprint>`; `provenance` = `transcript_edit.discovery.v1` (distinct from seed `deterministic` and harness-emergent items). Lineage stays in native `discovery_meta` / row fields — **not** leaked into `backend/harness/decision_ledger/contracts.py`. Semantic de-dupe uses `signal_fp` (hash of kind + normalized message text), per-kind caps, minimum message length, and skipped low-severity findings.
- **Caps (anti-sprawl):** global ceiling on discovery rows, per-merge and per-audit inference limits, per-kind ceilings (see module constants).
- **Coexistence:** default checklist **seed** still initializes slots; discovery **adds** durable rows where audit evidence supports them; unified projection maps all native rows to `te:ledger:*` for read/closure/focus.
- **Focus (Phase 12):** `ledger_discovery` candidates use the same **authority rank** as `ledger_decision` when materially mapping-blocking; tie-break uses native `scope_priority` (not the default “unknown slot” tail rank), and board parity mismatch penalties from seed tie-breaks are **not** applied to discovery rows so they compete on closure substance.
- **Phase 13 — seed demotion & discovery posture:** Bootstrap rows that look like **idle placeholders** (deterministic provenance, no evidence, not disputed, no contradiction signal) take a bounded **priority penalty** in `choose_investigation_focus` so they do not outrank materially mature discovery rows (`discovery_meta.posture` / `evidence_touch_count`, with `fresh` → `touched` → `stable` / `escalated`). Focus output includes `organized_work_composition` (counts + `work_drive_hint`). `focus_packet.execution_context` carries the same composition snapshot plus richer `discovery_work_context`.
- **Phase 14 — lazy seed + discovery-led init:** Default checklist rows are still created for **mutation compatibility**; Phase 14 briefly woke three PLSS spine slots at init (superseded by Phase 15). Other slots were **dormant** until audit (`update_ledger_from_iteration`), image checks, or **orient** touched them (`wake_seed_scaffolding_row`). While a discovery row is unresolved, **dormant** seed rows are **skipped** as focus candidates so discovery can define the practical work surface.
- **Phase 15 — seed-on-demand + discovery-led startup:** `SEED_WAKE_AT_INIT_KEYS` is **empty** — every default checklist row starts with `seed_scaffolding_dormant: true` (structural rows remain in `items[]` for mutation compatibility). Rows **wake** only when audit, image checks, or orient/evidence paths call `wake_seed_scaffolding_row`. `organized_work_composition` **v3** adds `seed_materialization_mode: on_demand`, `discovery_led_startup_surface`, and `startup_active_work_posture`. When discovery is unresolved and every unresolved seed row is still dormant, focus sorting **prefers `ledger_discovery` over `ledger_decision`** (`startup_discovery_led_surface` on `choose_investigation_focus`). Callers that need accurate composition/dormancy must pass **native** `decision_ledger` **plus** the unified envelope (not unified alone).
- **Phase 16 — discovery-first default + optional domain templates:** The **default** organized-work posture is **discovery-first**; transcript-edit’s default checklist seed is an **optional domain template policy** (`transcript_edit_ledger_bootstrap_policy`), not harness ontology. Templates remain bounded, inspectable, and overridable by discovery/runtime evidence. Controller audit path **updates seed from findings then merges discovery** so inferred work is the normal post-audit surface. `organized_work_composition` **v4** adds `bootstrap_policy`, `domain_template_rows_awake`, `unresolved_discovery_cooling_count`. Native `discovery_meta.lifecycle_hint` (`active` / `cooling`) marks stale zero-touch rows; focus applies a bounded priority penalty for `cooling`. Full template engines across domains are **out of scope** — the seam is explicit so future work does not “ban templates” or conflate them with the generic ledger.
- **Phase 17 — discovery-native initial ledger + vestigial cleanup:** Default ``initialize_decision_ledger`` starts with **empty** `items[]` (`ledger_establishment_mode: discovery_native`). First durable rows come from **discovery merge** and **on-demand materialization** when audit/orient/image touches a checklist key (`update_ledger_from_iteration` / `update_ledger_from_orient_baseline`). Optional full checklist: ``initialize_decision_ledger_with_domain_template_seed``. Legacy persisted sessions with a full default checklist and no explicit mode are classified as **template_seed** via ``effective_ledger_establishment_mode``. `organized_work_composition` **v5** adds native establishment fields. The old no-op ``discovery_ledger_merge_hook_placeholder`` was **removed** as vestigial (no compatibility commitment).

Use the bounded discovery merge helpers (`merge_discovery_from_audit_findings`, `merge_discovered_native_items`).

## Generic ledger item (contract)

Fields (JSON-serializable): `item_id`, `title`, `kind`, `state`, `priority`, `materiality`, `blocking_impact`, `dependencies`, `evidence_refs`, `alternatives`, `resolution_condition`, `scope`, `summary`, `notes`, `context_notes`, `provenance`, `domain_payload`.

**Rule:** No PLSS or deed-specific harness slots; domain specifics live in `domain_payload` and in domain-chosen `kind` strings.

Lifecycle states (v1): `open`, `investigating`, `narrowed`, `blocked`, `waiting_human`, `waiting_evidence`, `answered_pending_integration`, `resolved`, `superseded`.

## Transcript-edit adapter

- **Projection:** `work_board_projection.project_decision_ledger_to_work_board` maps native checklist rows → generic ledger items (`te:ledger:<key>`).
- **Unified read surface:** `decision_ledger_adapter.build_transcript_edit_unified_decision_ledger`.
- **Closure/read model:** `decision_ledger_adapter.transcript_edit_closure_read_ledger`.
- **Combined read entrypoint:** `transcript_edit_unified_and_closure_read_for_native` / `transcript_edit_unified_and_closure_read_from_loop_state` (focus packet, repair loop, domain pack, controller orient/audit/HITL).
- **Focus selection:** `choose_investigation_focus` accepts the unified envelope alone (or legacy `ledger` + envelope during migration). **Seed** rows use `TRANSCRIPT_EDIT_SLOT_PRIORITY_HINTS` for tie-breaks (`transcript_edit_bootstrap_hints.py`), re-exported as `TRANSCRIPT_EDIT_DOMAIN_SLOT_PRIORITY`, plus **weak-placeholder demotion** (Phase 13). **Discovery** rows use **effective** priority: `scope_priority` minus a small **maturity bonus** for `touched` / `stable` / `escalated` posture in native `discovery_meta`.

## Recent iteration lane

`build_recent_iteration_lane` (`backend/harness/work_board/recent_iteration_lane.py`) thickens continuity from bounded `continuity_log` steps, not full history.

## Execution context (model-facing)

`focus_packet.execution_context` includes `active_work_item`, `work_board_focus_context`, `recent_iterations`, `discovery_work_context` (when the active key is discovery-backed), `organized_work_composition`, `organized_work_note`, etc.

**Compatibility:** `focus_packet.work_board` is the unified ledger envelope (historical field name).

## Emergence, lifecycle, authority

- Emergence ops: `harness.work_board.emergence` (`propose_work_board_changes` / `work_board_changes[]` in API — field name unchanged).
- Lifecycle helpers: `harness.work_board.lifecycle`.
- Authority policy: `focus_authority_policy` (explicit modes; applies on the unified ledger).

## Anti-goals (resolved)

- No permanent **two** co-equal ledger-like surfaces for “real” vs “display” work.
- No transcript-edit deed checklist as the harness ontology; harness ledger stays generic; checklist is adapter/projection input.
