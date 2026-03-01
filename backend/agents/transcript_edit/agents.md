# agents.md

## Scope
- Folder: `backend/agents/transcript_edit/`
- Purpose: Kernel-backed transcript audit/edit orchestration for post-T0 conditioning and manual runs.

## Contracts & invariants
- Agent loop must execute transcript actions through Agent Kernel (`TX_*`) only.
- Deterministic edit/apply semantics remain in `backend/transcript_edit/`; do not duplicate apply or validator logic here.
- Auto-promotion is only safe for clean or normalization-only outcomes.

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

## Links
- Related code: `backend/agents/transcript_edit/controller.py`
- Related code: `backend/agent_kernel/actions.py`
- Related code: `backend/agent_kernel/tooling.py`
- Related code: `backend/transcript_edit/`

