# agents.md

## Scope

- Folder: `backend/harness/`
- Purpose: Shared harness—runtime mechanics, mission coordination substrate, tracing, review/read models—without smuggling semantic “loop grammar” or family policy into generic code.

## Contracts & invariants

- **Mechanics, not choreography:** Tracing and runtime helpers must describe mechanical events; they must not encode a universal semantic phase model (e.g. focus → move → plan) as harness truth. See rationale: `docs/architecture/harness/harness-sanity-refactor-brief.md` §14.
- **Shared runtime stays generic:** Family- or mission-pack-specific meaning belongs at adapter/domain edges; orchestration helpers may host generic mode/runtime support, but they must not grow into family policy hosts.
- **Native wire only:** Harness accepts and produces the current wire vocabulary only (e.g. `opaque_payload`, `opaque_adapter_payload`, `pack_id`, JSON keys `mission_flow` and `orchestration_kernel`, `loop_family` values aligned with those). Do not add alternate keys, Pydantic aliases, or fallbacks for superseded names.
- **Inspection:** `observability/summary/` package (`models.py`, thin `build.py`, `orchestration.py`, `payload.py`, shared helpers) is the derived read model; keep it inspection-only (see `docs/architecture/harness/run-summary-build-refactor-brief.md`).
- **Runtime folders are responsibility-based:** `runtime/orchestration/` holds run-scope and mission-scope orchestration plus their generic mode-support contracts; `runtime/memory/` holds continuity/telemetry/loop-local carriage; `runtime/hitl/` holds HITL transport; CLI payload helpers live in `cli/`; mission payload helpers and derived summaries live in `observability/`.

## Allowed changes

- Fixes and refactors that align tracing, naming, and placement with §14 and the Harness Constitution.
- Mechanical event shapes and deletion of unused staging APIs.

## Commands

- Test: from `backend/`, with repo venv active: `pytest harness/ -q`
- Guardrails: from `backend/`, with repo venv active: `pytest harness/test_architecture_guardrails.py -q`

## Gotchas

- Stale **names** in tests/fixtures and committed caches teach the wrong architecture; prefer renames when editing adjacent code (§14.5).

## Remaining convergence (when touched)

- **`observability/summary/`:** Builders split per `run-summary-build-refactor-brief.md` (`build.py` = entrypoints + registration; family logic in `orchestration.py` / `payload.py`; shared coercion in `common.py`; prompt + mission-state helpers in dedicated modules).
- **`runtime/orchestration/orchestrator.py`:** Run-scope loop driver is typed against ``OrchestrationAdapter`` from ``contracts.py``; optional ``wire_identity_trace_cb`` stays duck-typed. No ``progress_cb``—mechanical status is trace-only (``KernelTraceCollector`` / ``KernelLoopResult.trace_events``).
- **`runtime/orchestration/mission_orchestrator.py`:** Mission-scope orchestration lives beside run orchestration; generic mode contracts/registries/transition validation live in `runtime/orchestration/`, not a separate `mission/` bucket.

## Enforcement

- `test_architecture_guardrails.py` is the executable backstop for shared harness discipline. Extend it when introducing a new canonical boundary or deleting an old one.
- The guard suite currently protects:
  - banned shared-harness vocabulary from re-entering live Python
  - deleted path regressions (`orchestration_kernel/`, `mission_runtime/`, `run_state.py`, etc.)
  - generic shared surface shape (`RequestSummary`, `VerificationSummary`, `OrchestratorContext`)
  - hotspot file growth budgets so broad modules get split instead of silently expanding

## Canonical naming (not legacy)

- **`mission_flow`:** Current native `loop_family` / JSON key for the **multi-cycle mission runtime** (traces, run-summary registration, review). It is wire vocabulary only; do not reintroduce a vague `mission/` ownership bucket just because the wire token contains “mission”.
- **`orchestration_kernel`:** Current native `loop_family` / JSON key for the **single-cycle orchestration kernel** loop (`run_orchestration_kernel_loop`, kernel trace persistence).

## No domain/family semantics in harness

Product- or pack-specific interpretation belongs **outside** `backend/harness/` (e.g. `backend/domains/...` or a composition layer). Shared types use **opaque** / **pack** vocabulary: `MissionModeRunEnvelope.opaque_payload`, `MissionObservation.opaque_adapter_payload`, `MissionState.opaque_payload`, trace `pack_id`.

- **No product persistence IDs on shared read models:** `RequestSummary` carries only objective/mode/trigger. Product case or dossier context must not appear as first-class harness fields; pass optional context through `OrchestratorContext.opaque_run_context` and trace `request_start` payload `opaque_run_context`, or through `MissionState.opaque_payload` from composition code.
- **No use-case readiness in inspection:** `VerificationSummary` is generic status/kind only—never mapping- or pipeline-specific flags.

## PR self-audit (harness)

After edits, ensure no reintroduction of superseded wire keys or ownership vocabulary in Python:

- `rg -n "domain_payload|family_coordination|mission_runtime|mission_runtime_ref" backend/harness --glob "*.py"` — should be empty.
- `rg -n "domain_|\\.get\\(\"domain\"\\)" backend/harness --glob "*.py"` — should be empty (product “domain” layer lives outside this folder; do not add `domain` as a prompt/trace key here).
- `rg -n "mapping_ready|dossier_id" backend/harness --glob "*.py"` — should be empty (composition/product layers may still use those terms outside this folder).
- `pytest backend/harness/test_architecture_guardrails.py -q` — should pass before considering the shared harness “clean.”

## Links

- Docs: `docs/architecture/harness/harness-sanity-refactor-brief.md` (especially §13 snapshot, §14 rationale)
- Docs: `docs/architecture/harness/harness-testing-brief.md`
- Docs: `docs/architecture/harness/run-summary-build-refactor-brief.md`
- Related: `docs/architecture/harness/harness-constitution.md`
