# agents.md

## Scope
- Folder: `backend/agents/transcript_edit/`
- Purpose: Kernel-backed transcript audit/edit orchestration for post-T0 conditioning and manual runs.

## Contracts & invariants
- Agent loop must execute transcript actions through Agent Kernel (`TX_*`) only.
- Deterministic edit/apply semantics remain in `backend/transcript_edit/`; do not duplicate apply or validator logic here.
- Auto-promotion is only safe for clean or normalization-only outcomes.
- Keep orchestration in `controller.py`; keep pure disagreement and HITL helper logic in dedicated modules.
- Keep span-windowing and image-check assembly/terminal image gates in dedicated modules (`context_spans.py`, `image_verification.py`).
- Keep generic loop runtime mechanics (step execution/progress/read helpers) in `loop_runtime.py`.
- Keep plan/apply interpretation and display shaping in `plan_interpretation.py`.
- Keep event payload contracts (phase/message/detail/event_type) in `run_reporting.py`.
- Keep agent-edited draft save glue in `draft_persistence.py`.
- Keep terminal status/reason/review decision policy in `result_policy.py`.
- Keep mutable loop runtime state in `loop_state.py` (single source for iteration mutations).
- Keep clean/repair per-iteration branch orchestration in `iteration_pipeline.py`.
- Keep terminal run-result/message/summary composition in `terminalization.py`.
- Keep mapping-critical decision ledger model/update helpers in `decision_ledger.py` (derived explanatory state for progress/terminal payloads).
- Keep transcript-edit -> mapping handoff packet composition/persistence in `handoff_packet.py`.

## Allowed changes
- Safe: improve loop brakes, improve request/response contracts, add endpoint/CLI ergonomics.
- Do not casually change transcript action names or reason-code strings; kernel and API consumers rely on them.

## Commands
- Test: `.venv\scripts\activate.ps1; pytest backend/api/test_transcript_edit_agent_endpoints.py backend/api/test_transcript_edit_agent_cli.py -q`
- Lint: `N/A`
- Build/Run: `N/A`
- Other: `.venv\scripts\activate.ps1; python -m api.transcript_edit_agent_cli --help`

## Gotchas
- `edit_plan` is optional; without a valid plan the controller should terminate as `needs_review` when findings remain.
- Keep controller bounded; never run unbounded retries in this loop.
- If adding disagreement or HITL policies, extend `disagreement_analysis.py` / `hitl_feedback.py` first, then wire orchestration calls in `controller.py`.
- If adding span-open or image-check behavior, update `context_spans.py` / `image_verification.py` before touching loop orchestration.
- If adding generic step/progress/read mechanics, update `loop_runtime.py` and keep controller as the state machine.
- If adjusting plan fingerprinting/coercion/review flags/apply input persistence, update `plan_interpretation.py` first.
- If adjusting Agent Viewer phase/detail payloads, update `run_reporting.py` and preserve existing phase/detail keys.
- If changing where/how agent-edited drafts are persisted, update `draft_persistence.py`.
- If changing completion/needs_review/failed decision rules, update `result_policy.py`.
- If changing per-iteration clean/repair branching behavior, update `iteration_pipeline.py` before `controller.py`.
- If changing done-event human summary or run-result composition, update `terminalization.py`.
- If changing mapping-critical checklist items/decision states/evidence shaping, update `decision_ledger.py` and keep payload fields additive.
- If changing downstream continuity payload shape or storage location, update `handoff_packet.py` and keep fields additive.

## Links
- Related code: `backend/agents/transcript_edit/controller.py`
- Related code: `backend/agents/transcript_edit/disagreement_analysis.py`
- Related code: `backend/agents/transcript_edit/hitl_feedback.py`
- Related code: `backend/agents/transcript_edit/context_spans.py`
- Related code: `backend/agents/transcript_edit/image_verification.py`
- Related code: `backend/agents/transcript_edit/loop_runtime.py`
- Related code: `backend/agents/transcript_edit/plan_interpretation.py`
- Related code: `backend/agents/transcript_edit/run_reporting.py`
- Related code: `backend/agents/transcript_edit/draft_persistence.py`
- Related code: `backend/agents/transcript_edit/result_policy.py`
- Related code: `backend/agents/transcript_edit/loop_state.py`
- Related code: `backend/agents/transcript_edit/iteration_pipeline.py`
- Related code: `backend/agents/transcript_edit/terminalization.py`
- Related code: `backend/agents/transcript_edit/decision_ledger.py`
- Related code: `backend/agents/transcript_edit/handoff_packet.py`
- Related code: `backend/agent_kernel/actions.py`
- Related code: `backend/agent_kernel/tooling.py`
- Related code: `backend/transcript_edit/`
