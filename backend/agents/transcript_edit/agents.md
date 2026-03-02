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

## Links
- Related code: `backend/agents/transcript_edit/controller.py`
- Related code: `backend/agents/transcript_edit/disagreement_analysis.py`
- Related code: `backend/agents/transcript_edit/hitl_feedback.py`
- Related code: `backend/agents/transcript_edit/context_spans.py`
- Related code: `backend/agents/transcript_edit/image_verification.py`
- Related code: `backend/agents/transcript_edit/loop_runtime.py`
- Related code: `backend/agents/transcript_edit/plan_interpretation.py`
- Related code: `backend/agent_kernel/actions.py`
- Related code: `backend/agent_kernel/tooling.py`
- Related code: `backend/transcript_edit/`
