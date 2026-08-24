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
- **Practice-packet freeze tooling:** `fixtures/dossier_t0_fixture.py` + `fixtures/dossier_t0_fixture_manifest.py` hold mechanical freeze/validate helpers for immutable local practice packets (distinct from static `test_fixtures/` regression JSON). Product coordinates such as `dossier_id` are allowed only in those two modules and `cli/freeze_dossier_t0_fixture.py`; they remain banned on orchestration, summary, runtime, and any other fixtures modules.
- **Pending-result delivery:** Typed `ActionDispatchResult` is the sole admission source (`result_delivery_hooks.admit_recorded_execution_result` from action-sequence execution). Semantic prompts project `structured_state.latest_action_results` via pure BR-017 projection; contact acknowledgement runs only after the primary `text_model_caller` returns in `LlmTurnOrchestrationAdapter.choose_action`. Prompt construction must not mutate delivery state. Do not admit from summaries, audit, journal, or tool-result slices. `latest_action_results` is the sole result-continuity prompt lane; durable sequence/step/delegate state remains for audit/hydrate/resume.
- **Post-repair contract recovery:** When deterministic salvage misses and one model repair still yields `invalid_model_action_json`, raise `RecoverableTurnFailure` (`failure_stage=post_repair_parse`) into the existing turn-recovery budget. Durable failure records stay JSON-native and within the compact-JSON cap (bounded diagnostic preview plus original character count; invalid or oversized provider identities and non-integer or out-of-range usage values are omitted whole). During `turn_recovery`, the bounded `turn_recovery` record is the sole mechanical failure-context lane (`contract_feedback` is omitted from that prompt mode so uninterrupted and resumed recovery stay equivalent). Prompt-facing `contract_feedback` diagnostics use the same preview/count shape so a repaired turn cannot inject an unbounded parser message into the next normal prompt. When the canonical parse error is `action_type not batchable: <tool_id>`, repair targets `select_one_nonbatchable_action_for_this_turn` instead of `preserve_multi_action_intent`. `turn_recovery` also receives a bounded generic `surface_packet.tool_contracts` projection (tool_id, expected_request_shape, batching when surface-visible). Do not route content filters, transport/auth failures, `model_caller_exception`, or any post-dispatch mutation through this path. Do not add a second retry counter.
- **Same-turn completion anchor:** Domains may opt in via `CompletionAnchorPolicy.terminal_on_satisfied_anchor`. Evaluation lives in `runtime/orchestration/completion_anchor_terminal.py`; `action_sequence_hooks.py` wires it after a successful sole publish action without synthesizing closure state.

## Allowed changes

- Fixes and refactors that align tracing, naming, and placement with §14 and the Harness Constitution.
- Mechanical event shapes and deletion of unused staging APIs.

## Commands

- Test: from `backend/`, with repo venv active: `pytest harness/ -q`
- Guardrails: from `backend/`, with repo venv active: `pytest harness/test_architecture_guardrails.py -q`
- Operator CLI (from `backend/` so `python -m harness.cli.*` resolves): `pytest harness/cli/test_cli_operator.py -q`

## Operator CLI (`harness/cli/`)

- **Purpose:** Process and path plumbing only (`start`, `watch`, `answer`, `status`). Run-state for **new runs** lives under `harness_cli_artifacts_root() / "cli_runs" / "by_loop_kind" / <run_collection> / <run_id> /` (`state.json`, `done.json`, `result.json`, logs). `--run-collection` selects retention/storage identity; when omitted it defaults to `--loop-kind`. `loop_kind` / `HARNESS_CLI_LOOP_KIND` / domain selection remain independent. Legacy flat runs remain at `cli_runs/<run_id>/`. Canonical discovery: `harness/cli/run_layout.py` (global unique `run_id`). Not orchestration.
- **Upstream lineage:** Optional launch-context `upstream_run_lineage` is normalized/stored in `state.json` extra, result/done payloads, and `audit/index.json`; it is stripped before domain adapters and model prompts. See `backend/harness/runtime/upstream_run_lineage.py`.
- **Start:** Spawns a detached child with env `HARNESS_CLI_RUN_ID`, `HARNESS_CLI_DONE_FILE`, `HARNESS_CLI_RESULT_FILE`, `HARNESS_CLI_STDOUT_LOG`, `HARNESS_CLI_STDERR_LOG`, `HARNESS_CLI_LOOP_KIND`. Real runners (e.g. future transcript-edit) should read these paths and write `done.json` / `result.json` on completion; default `--stub` uses `harness.cli.stub_worker`.
- **Run control sidecar:** Each CLI run directory gets human-editable `run_control.json` (`emergency_stop`, cooperative `stop`/`pause`). A sibling watchdog process polls `emergency_stop` and hard-kills the worker; cooperative flags bridge into the existing safe-boundary control reader. `control.json` CLI transport remains unchanged.
- **HITL:** Pending prompts still use `dossiers_artifacts_root() / hitl_prompts / {run_id}_pending.json` (see `runtime/hitl/watch.py`). **`--loop-kind` on `start` must match** the loop’s feedback namespace and `harness.cli.answer` / `feedback_store`.
- **Retention cleanup:** Retiring a CLI run also removes matching `artifacts/transcript_edit/.../<run_id>/` and `artifacts/transcript_edit_dossier/.../<run_id>/` workspace dirs (exact run-id match only; no TE tooling imports into retention).

## Gotchas

- Stale **names** in tests/fixtures and committed caches teach the wrong architecture; prefer renames when editing adjacent code (§14.5).

## Remaining convergence (when touched)

- **`observability/summary/`:** Builders split per `run-summary-build-refactor-brief.md` (`build.py` = entrypoints + registration; family logic in `orchestration.py` / `payload.py`; shared coercion in `common.py`; prompt + mission-state helpers in dedicated modules).
- **`runtime/orchestration/orchestrator.py`:** Run-scope loop driver is typed against semantic ``OrchestrationAdapter`` from ``contracts.py`` plus explicit mechanical ``OrchestrationLifecycle`` collaborators from ``runtime/orchestration/lifecycle.py``. Pre-choose compaction, prompt-event tracing, raw LLM I/O audit, and turn-completion observation belong on that lifecycle surface; no duck-typed ``wire_*`` or discoverable callback law remains. No ``progress_cb``—mechanical status is trace-only (``KernelTraceCollector`` / ``KernelLoopResult.trace_events``).
  Adapter-facing observer refs are injected through ``OrchestratorContext`` from the active lifecycle; semantic adapters must not retain a second lifecycle bundle as state.
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
- `rg -n "mapping_ready|dossier_id" backend/harness --glob "*.py"` — should be empty on orchestration/summary/runtime surfaces. Allowed exceptions only: `backend/harness/fixtures/dossier_t0_fixture.py`, `backend/harness/fixtures/dossier_t0_fixture_manifest.py`, and `backend/harness/cli/freeze_dossier_t0_fixture.py`.
- `pytest backend/harness/test_architecture_guardrails.py -q` — should pass before considering the shared harness “clean.”

## Links

- Docs: `docs/architecture/harness/dependency-practice-dossiers.md`
- Docs: `docs/architecture/harness/harness-sanity-refactor-brief.md` (especially §13 snapshot, §14 rationale)
- Docs: `docs/architecture/harness/agent-engine-constitution.md`
- Docs: `docs/architecture/harness/transcript-edit-live-loop-testing.md`
- Docs: `docs/architecture/harness/deed-to-ir-live-loop-testing.md`
- Docs: `docs/architecture/harness/run-summary-build-refactor-brief.md`
- Related: `docs/architecture/harness/harness-constitution.md`
