# agents.md

## Scope
- Folder: `backend/`
- Purpose: Backend API/services runtime behavior, including logging and run-loop diagnostics.

## Contracts & invariants
- Backend logs are exposed via `backend/api/logs.py` endpoints and configured in `backend/services/logging_service.py`.
- Session log files live at `backend/logs/app_YYYYMMDD_HHMMSS.log` when running in dev mode.
- Session log retention is capped at 5 per-session files (`app_*.log`) in `logging_service.py`.
- Separation of concerns is required across backend work: orchestration, policy, reporting payloads, persistence, and transport should remain in dedicated modules.
- Before substantial edits, ask: "Should these edits be separated into dedicated modules of responsibility?" If yes, define the intended module boundaries first.

## Allowed changes
- Safe: add log filters/endpoints, improve diagnostic payloads, adjust retention defaults.
- Safe: extend backend static-governance rules when they enforce clear layer boundaries without relying on fuzzy heuristics.
- Avoid casual changes to `/api/logs/*` response shapes because agent workflows depend on them.

## Commands
- Test: `.venv\scripts\activate.ps1; pytest backend/api/test_transcript_edit_agent_endpoints.py backend/api/test_agent_viewer_endpoints.py -q`
- Build/Run: `.venv\scripts\activate.ps1; cd backend; uvicorn main:app --reload`
- Other: `.venv\scripts\activate.ps1; Get-Content backend\logs\app_*.log -Tail 200`

## Gotchas
- `source=active` resolves to the currently active session file, not always `backend/logs/app.log`.
- Prefer `/api/logs/tail` + filters (`run_id`, `contains`, `exclude`) before large file reads.
- Read `docs/linting/static-governance.md` before relaxing a backend boundary rule; `backend/api/` is treated as a transport layer, not a dependency for services or pipelines.
- Avoid monolith drift in high-churn files. Plan for future extension, pivoting, and rewind by keeping responsibilities isolated.

## Links
- Docs: `docs/linting/static-governance.md`
- Related code: `backend/api/logs.py`
- Related code: `backend/services/logging_service.py`

## Prompt Architecture Notes
- Shared harness prompt source words live in `backend/domains/common/prompt_sources.py`.
- Domain-branch prompt words live in domain-owned `prompt_sources.py` modules.
- Surface-local packet/task wording lives in the prompt assembly modules, not in the shared source modules.
- Prompt events are inspected through review bundles in `backend/harness/review/tool.py` (`build_single_run_review_bundle(...)` / `build_multi_run_review_bundle(...)`).
- Do not hide doctrine in composers.
- Do not put strategy into structured state.
- Do not add new prompt surfaces without prompt-event capture and review-path visibility.

