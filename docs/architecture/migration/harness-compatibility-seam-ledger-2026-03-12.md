# Harness Compatibility Seam Ledger

Date: 2026-03-12
Status: Active
Scope: Phase 11 harness-relevant compatibility cleanup

Primary references:
- `docs/architecture/migration/harness-convergence-roadmap.md`
- `docs/architecture/migration/harness-delta-ledger.md`
- `docs/architecture/migration/harness-decisions.md`
- `docs/architecture/harness/transcript-edit-state-authority.md`

## Purpose

Make canonical-vs-compatibility posture explicit for the remaining active
harness-relevant seams so future work does not guess.

## Seam Classification

| Seam | Classification | Canonical replacement | Current consumers | Deprecation trigger | Safe removal conditions |
| --- | --- | --- | --- | --- | --- |
| `resume_pending_feedback_*` request fields (`backend/agents/transcript_edit/contracts.py`) | Compatibility bridge with explicit deprecation path | Registry-first resumability via `resume_blocker_registry` + registry projection (`derive_waiting_feedback_projection`) | Resume request builders and compatibility callers that still pass explicit pending fields | Resume callers consistently provide/derive registry payload and no longer require standalone pending prompt identity fields | API/CLI + transcript-edit tests pass with compatibility fields absent; run registry snapshots remain resumable via registry-only payloads |
| `backend/api/endpoints/transcript_edit_agent.py` | Canonical and staying | N/A (already canonical) | Harness-facing transcript-edit runs/resume | N/A | N/A |
| `backend/api/endpoints/transcription_edit.py` | Legacy surface to keep narrow and isolated | `backend/api/endpoints/transcript_edit_agent.py` | Deterministic transcription-edit v0 callers | Consumers migrate to canonical harness-facing endpoint where equivalent behavior is required | No active callers depend on this endpoint for supported workflows; migration window and docs updated |
| `backend/api/transcription_edit_cli.py` | Legacy surface to keep narrow and isolated | `backend/api/transcript_edit_agent_cli.py` | CLI users of deterministic v0 endpoint internals | Canonical CLI meets operational needs for active workflows | No active operational scripts rely on legacy CLI semantics |
| `backend/transcription_edit_loop` package path | Compatibility bridge with explicit deprecation path | Preferred import path is `backend/transcript_edit` (contract ownership remains transitional) | Imports from older package path | Import call sites moved to `backend/transcript_edit` | No in-repo imports remain, contract ownership moved off compatibility package, and external dependency window is closed |
| `agent_kernel.run_kernel` export (`backend/agent_kernel/__init__.py`) | Legacy surface to keep narrow and isolated | Step-driven session API (`KernelSessionManager`) | Deterministic/autopilot regression and smoke harness paths | All maintained harness workflows use step-driven session API | Legacy/autopilot usage retired or intentionally frozen with no active integration dependency |

## Implementation Notes (Phase 11 slice)

- Canonical/compatibility role markers were added on transcript-edit endpoint and
  CLI modules.
- `resume_pending_feedback_*` fields are now explicitly documented as
  compatibility-bridge inputs.
- `run_kernel` is explicitly marked as legacy/autopilot compatibility and
  non-growing.
