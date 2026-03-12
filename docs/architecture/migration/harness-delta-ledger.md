# Harness Delta Ledger

Date: 2026-03-11
Status: Active migration tracker
Primary sequencing reference: `docs/architecture/migration/harness-convergence-roadmap.md`

## How To Use

Track migration deltas as capabilities, not as broad narratives.

Each row should be updated when:
- architecture decisions change
- implementation reduces a gap
- new evidence clarifies scope or sequencing

## Ledger

| Target capability | Current state | Gap | Migration phase | Owner | Migration status | Decision status | Evidence of progress | Open questions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| One shared harness spine with domain policies on top | Generic controller/kernel and transcript-edit operate as distinct harness personalities | Shared infrastructure exists but shared contract surfaces are incomplete | Phase 2 to Phase 7 | Unassigned | In progress | Accepted | Phase 1 and 2 contract docs established under `docs/architecture/harness/` | What boundary split is stable long-term for shared spine vs policy layers? |
| Canonical trace schema and normalization design defined | Shared tracing foundation exists and both read-only loop-family adapters emit canonical traces from persisted artifacts | Export surface/persistence policy is still pending | Phase 2 to Phase 4 | Unassigned | Phase 4C transcript-edit adapter implemented (authority-aware, partial-history aware) | Accepted | `docs/architecture/harness/canonical-trace-schema.md`; `docs/architecture/harness/trace-normalization-and-adapter-design.md`; `docs/architecture/migration/trace-implementation-plan.md`; `backend/harness/tracing/schema.py`; `backend/harness/tracing/builder.py`; `backend/harness/tracing/adapters/controller_kernel.py`; `backend/harness/tracing/adapters/transcript_edit.py`; `backend/harness/test_tracing_schema.py`; `backend/harness/test_tracing_builder.py`; `backend/harness/test_tracing_controller_kernel_adapter.py`; `backend/harness/test_tracing_transcript_edit_adapter.py` | Should first-slice canonical traces be on-demand only or also persisted as sidecars? |
| Shared terminal taxonomy defined | Loop-family terminal semantics and reasoning differ | No single harness-level terminal vocabulary used everywhere | Phase 2 to Phase 5 | Unassigned | Defined (docs), implementation pending | Accepted | `docs/architecture/harness/shared-terminal-taxonomy.md` | How should existing reason codes map to shared classes without losing signal? |
| Shared blocker/escalation envelope defined | Transcript-edit has blocker-native machinery; controller-family is blocker-light | No shared blocker contract implemented across both loop families | Phase 2 to Phase 5 | Unassigned | Defined (docs), implementation pending | Accepted | `docs/architecture/harness/shared-blocker-escalation-envelope.md` | Where should synthesized controller-family blockers be produced first? |
| Minimal shared run-state envelope defined | Continuity/state concepts differ across loop families | No minimum shared envelope used consistently | Phase 2 to Phase 6 | Unassigned | Defined (docs), implementation pending | Accepted | `docs/architecture/harness/minimal-shared-run-state-envelope.md` | Which fields are mandatory vs extension-only after first migrations? |
| Transcript-edit unresolved closure authority is singular and explicit | Closure derivation is ledger-led today, but compatibility paths can still blur ownership during runtime composition | Need implementation invariants that keep closure truth ledger-owned only | Phase 3 to Phase 5 | Unassigned | Defined (docs), implementation pending | Accepted | `docs/architecture/harness/transcript-edit-state-authority.md` (authority invariant) | How should emergent blockers be promoted when they need closure-level authority? |
| Transcript-edit blocker and HITL lifecycle authority is singular and explicit | Blocker lifecycle mostly lives in registry, but waiting/resume compatibility fields still duplicate ownership | Need registry-first waiting/resume derivation with compatibility projections only | Phase 3 to Phase 5 | Unassigned | Defined (docs), implementation pending | Accepted | `docs/architecture/harness/transcript-edit-state-authority.md`; `docs/architecture/migration/transcript-edit-authority-migration-notes.md` | What deprecation window should apply to `resume_pending_feedback_*` once registry-first resumability is implemented? |
| Capability exposure parity where policy intends parity | Platform capability exposure is uneven by loop context | Some represented moves are not yet executable in all relevant loops | Phase 7 | Unassigned | Open | Open | Gap captured in ambition and roadmap docs | Which parity items are foundational vs optional for first convergence milestone? |
| Outer-loop harness improvement machinery | Observability is strong but review/eval loop is not yet first-class | Limited repeatable trace-driven improvement process | Phase 8 | Unassigned | Open | Open | Phase 8 ritual defined in roadmap | What minimum recurring review artifacts should be required per cycle? |
| Docs information architecture supports architecture-led migration | Active architecture path exists and now includes phase contracts | Still early; needs disciplined updates during implementation phases | Phase 1 to Phase 2 | Unassigned | In progress | Accepted | Docs index plus Phase 1 and 2 harness contract docs in place | Do we need a small loops index page under `docs/architecture/loops/` in phase 3? |

## Update Rules

When editing rows:
- keep deltas evidence-backed
- link concrete artifacts/docs/tests where possible
- update phase, migration status, and decision status when a capability materially advances
- preserve unresolved questions until actually resolved
