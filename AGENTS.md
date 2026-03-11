# Repository Guidelines

# Repo Operating Rules (read first)

This file defines non-negotiables and working norms for any agent (including Ralph loops) operating in this repository.

---

## 1) Safety / blast-radius rules (non-negotiable)

### Protected branches
- Do NOT checkout, commit to, push to protected branches, working and modifying as asked is fine, the purpose of this rule is to prevent unwanted git pushes:
  - `main`
  - `agent-loop-building`
- Work only on the current working branch (e.g. `ralph/*`, `feature/*`, etc.).

### Never-dos (hard bans)
- Never delete or modify anything outside the repository root. (exceptions:skill factory actions needed to add new skills via agent kit or profile skills to update a profile)

- Never run destructive / wide delete commands, especially anything that could target a drive/root/home, such as:
  - `rm -rf /`, `rm -rf ~`, `rm -rf ..`
  - `del /s`, `rmdir /s`
  - `Remove-Item -Recurse C:\*` or any absolute-path recursive deletion
- Never delete or modify `.git/` or git internals.
- Never use absolute paths for deletion or edits. except for adding .gitattributes
- Never use `..` path traversal for deletion or edits.
- Never read, print, commit, or modify secrets (e.g. `.env`, private keys, tokens, credentials).

### Deletions policy (allowed, but disciplined)
- You MAY delete/move files **within this repo** when required for refactors or cleanup.
- If deleting/moving files:
  - Prefer removing usage first, then delete the unused file(s).
  - Keep the change minimal and justified (no “random cleanup”).
  - Run repo checks (tests/lint/build) before committing whenever feasible.
  - Commit with a message that clearly explains what was removed and why.

---

## 2) Workflow rules (how you work)

- Prefer small, reviewable changes.
- One logical unit of work per commit (Ralph: one story per commit).
- Before committing:
  - run the project’s verification commands when feasible (tests/lint/typecheck/build).
  - if you cannot run them, state what you did run and what remains unverified.

## Mandatory review flow for non-trivial patches

This repository uses reviewer subagents to prevent two recurring failures:
1. monolith file drift
2. code mass inflation

A patch is non-trivial if it adds files, changes more than 3 files, materially expands a file, introduces a new abstraction/helper/service, changes module or layer boundaries, or is a refactor / cleanup / reorganization.

For non-trivial patches, run:
- `architecture_reviewer`
- `code_efficiency_reviewer`

### Reviewer purposes

`architecture_reviewer`
- prevent monolith files
- prevent mixed responsibilities
- enforce separation of concerns
- enforce boundary, layering, orchestration, and module-intent standards

`code_efficiency_reviewer`
- prevent unnecessarily heavy implementations
- reduce accidental complexity
- catch over-abstraction, duplication, helper sprawl, wrapper indirection, and excessive code quantity

### Standards to enforce

Before implementing or reviewing, consult:
1. `AGENTS.md`
2. deeper local `AGENTS.md` files if present
3. relevant `docs/ethos` files if present

If `docs/ethos` exists, its relevant standards are binding within the scope they cover.

### Review output requirements

Reviewer findings must:
- stay within scope
- cite exact files and symbols when possible
- distinguish blocking vs advisory findings
- identify the relevant standard or ethos principle when applicable

### Completion requirement

A non-trivial patch is not complete until the reviewer agents have run, their findings have been summarized, and valid blocking findings have been reconciled or explicitly justified.

---

## 3) Read-first behavior (ethos / vision / local notes)

Always review the repo wide ethos files no matter what at the beginning of each session of work

- NEVER make any edits with out first reviewing the repo wide ethos files `docs/ethos/`
- Some sub modules and or sub directories will have internal ethos files and must be reviewed when editing anything inside or anything related to that directory. 

Before making changes:
- Read the repo’s ethos/vision docs relevant to the scope you’re working in.
- If you are editing files inside a directory, first check for and read:
  - `agents.md` (if present)
  - `README.md` (if present)
  - any nearby `VISION*.md` / `ETHOS*.md` (if present) sometimes I just have the vision.md files flat in docs/ or sub-module/

If you are starting a new feature or touching cross-cutting architecture:
- Also review the most relevant docs in `docs/` (ethos/vision/specs) before implementing.

---

## 4) Compounding memory: folder-level `agents.md`

### What `agents.md` is for
`agents.md` is a short, local “sticky note” for a folder: constraints, invariants, commands, gotchas.

### When to create/update `agents.md` (only when it helps)
Create or update a folder-level `agents.md` ONLY if you discover something that will prevent repeated mistakes, such as:
- a non-obvious invariant/contract (“must keep X and Y in sync”)
- a required workflow command (“run this generator before tests”)
- a sharp edge/gotcha (“these files are auto-generated; don’t hand-edit”)
- a dependency ordering constraint (“do A before B or CI fails”)

Do NOT spam `agents.md` everywhere. Keep it short and factual.

### Standard template (use this exact structure)
When creating/updating `agents.md`, follow this template so files are consistent across the repo:

# agents.md

## Scope
- Folder: `<relative/path/>`
- Purpose: `<1–2 bullets, plain language>`

## Contracts & invariants
- `<bullet>`
- `<bullet>`

## Allowed changes
- `<what is safe to change here>`
- `<what should not be changed casually>`

## Commands
- Test: `<command>`
- Lint: `<command>`
- Build/Run: `<command>`
- Other: `<command>`

## Gotchas
- `<bullet>`
- `<bullet>`

## Patterns (optional)
- Naming: `<bullet>`
- Structure: `<bullet>`

## Links
- Docs: `<relative/path/to/doc.md>`
- Related code: `<relative/path/>`

Template rules:
- Keep it under ~30–50 lines unless absolutely necessary.
- Use bullets. Be factual and action-oriented.
- Prefer repo-relative paths, not absolute paths.
- Only include info that prevents future mistakes or speeds correct work.

---

## 5) Ralph-loop compatibility note

If running under a Ralph loop:
- Treat each iteration as a single bounded unit of work.
- Leave clear state in files + git commits so the next iteration can self-correct.
- Never signal completion unless objective criteria are met (tests pass and/or acceptance criteria satisfied).


## Non-negotiables

### Repo safety
- **Do not restructure the repository** (no moving/renaming files, folders, modules) unless the task explicitly asks for it.
- Prefer **minimal diffs** that solve the stated problem cleanly.
- Do not introduce “catch-all” modules or dump logic into large files.

### Git rules (read-only allowed)
Allowed (read-only introspection only):
- `git status`
- `git diff`
- `git log`
- `git show`

Allowed when needed please dont abuse tho and mess stuff up:

- `git add`
- `git commit`
- `git push`
- `git pull`
- `git checkout`
- `git switch`
Forbidden (anything that changes repo beyond scope or history):
- `git init`, `git fetch`
- `git merge`, `git rebase`, `git cherry-pick`
- `git reset`, `git clean`, `git stash`
- any other git command that alters working tree, index, branches, remotes, or history

If forbiddon git actions are needed, **describe exact commands for a human to run**. Do not execute them.

### Virtual environment (venv) is mandatory for Python work
- The repo venv is at: `\Plattera\.venv`
- **Before any Python-related terminal command**, the venv must be active.
- Activate with PowerShell:
  - `.venv\scripts\activate.ps1`
- Never create a new venv or change interpreter paths.
- Never install/upgrade dependencies unless the venv is active.


## Project Structure & Module Organization
`backend/` holds the FastAPI service. Key submodules: `api/` routers, `services/` for dossier, LLM, and georeference helpers, `pipelines/` for alignment and projection, plus `config/` and `prompts/` for runtime defaults. Reference tables live in `dossiers_data/` and `raw_alignment_tables/`; keep replacements lightweight. The Next.js client lives in `frontend/`, with `src/components/`, `src/services/`, `src/hooks/`, and route files under `src/pages/`. Static assets belong in `frontend/public/`. Legacy diagnostics stay as top-level `test_*.py`; migrate long-lived code back into the owning package.

## Build, Test, and Development Commands
Install backend deps with `pip install -r backend/requirements.txt`, then run `uvicorn main:app --reload` (from `backend/`) or `python main.py` for quick checks. Frontend setup uses `npm install` in `frontend/`, `npm run dev` for local preview, `npm run build` for production, and `npm run tauri:dev` for the desktop shell. Manage secrets through `backend/.env`; update header comments when introducing new variables.

## Linting & Static Governance
- The repo uses both generic linting and repo-specific static-governance checks.
- Read `docs/linting/static-governance.md` before changing lint, CI policy, or custom structural rules.
- Frontend governance entrypoints currently live in `frontend/package.json`:
  - `npm --prefix frontend run lint`
  - `npm --prefix frontend run governance`
  - `npm --prefix frontend run check`
  - `npm --prefix frontend run check:full`
- Treat the custom governance rules as architectural policy, not cosmetic style rules.

## Logs for Agents (Recommended Workflow)
- Prefer API log access first (stable and filterable), then file reads only if needed.
- Primary backend log module: `backend/api/logs.py` (API) and `backend/services/logging_service.py` (file/ring config).
- Endpoints:
  - `GET /api/logs/recent?limit=500` for in-memory recent logs.
  - `GET /api/logs/tail?source=active&limit_lines=400` for file-backed tail.
  - `GET /api/logs/tail?source=active&run_id=<id>` to isolate one loop/run.
  - `GET /api/logs/tail?source=active&contains=TX_LOOP_EVENT` for selective grep-like pulls.
  - `GET /api/logs/tail?source=active&exclude=uvicorn.access` to remove noise.
  - `GET /api/logs/frontend/recent?limit=200` for browser-side logs forwarded from the Agent Viewer.
  - `POST /api/logs/frontend` accepts structured frontend logs (`source`, `level`, `message`, `ts`).
  - `GET /api/logs/download` to export zipped logs.
- `source` options for `/api/logs/tail`:
  - `active` (current runtime log file; preferred)
  - `latest_session` (newest `app_*.log`)
  - `app` (stable `app.log`)
- File location:
  - Session logs are written under `backend/logs/` as `app_YYYYMMDD_HHMMSS.log`.
  - Retention is capped to the newest 5 session logs by default (`LOG_MAX_SESSION_FILES`, set in `backend/services/logging_service.py`).
- Keep pulls targeted:
  - Start with `run_id` and/or `contains` filters.
  - Increase `limit_lines` only when needed.

## Coding Style & Naming Conventions
Follow PEP 8: four-space indentation, `snake_case` functions, `PascalCase` classes, and descriptive module names (`georeference_service.py`). Prefer type hints and Pydantic models for payloads. In TypeScript, use functional components, `PascalCase` filenames in `components/`, and `camelCase` for hooks or util exports (for example `useAlignmentStatus`). Co-locate styles in `styles/` and reuse Leaflet tokens. Log via `logging.getLogger(__name__)` or the colored formatter configured in `backend/main.py`.

## Testing Guidelines
Most integration checks assume the API is running at `localhost:8000`; start the server before executing scripts such as `python test_alignment_api.py` or `python test_api.py`. For deterministic coverage, add pytest cases alongside the code (`pytest backend/test_pyproj_behavior.py`) and keep fixtures in JSON next to the test. Document required environment variables in the test docstring when hitting external services.

## Commit & Pull Request Guidelines
Recent commits are concise status lines (`ui improvements in regard to buttons...`). Mirror that style: keep the subject under 72 characters, mention the affected surface first, and describe the user-visible change. Reference issues when possible. Pull requests should include a short intent paragraph, manual test evidence (CLI output or screenshots for UI changes), notes on schema or prompt updates, and any datasets that need regeneration.

## Architecture Expectations
All development must follow modular, scalable architecture with strict separation of concerns. Code should not be placed into large, catch-all files or allowed to deteriorate into spaghetti structures. Each module or component should have a clearly defined responsibility, and coupling between unrelated parts of the system should be avoided. Maintainability, clarity, extensibility, and long-term soundness take priority over any fast workaround or short-term patch. When there is a choice between a quick implementation and a structurally correct solution, the more robust and reliable option should always be taken. Shortcuts that compromise future stability, readability, or adaptability should not be used.

## Separation of Concerns Protocol
- Before implementing substantial edits, ask: **"Should these edits be separated into dedicated modules of responsibility?"**
- If yes, define the target architecture first:
  - module responsibilities
  - boundaries/contracts between modules
  - how this supports future building, pivoting, and rewind
- Avoid growing high-churn files into monoliths. If a change mixes transport/state/policy/rendering/persistence concerns, split it.
- Optimize for architecture that stays sane under ongoing iteration, not just immediate delivery.
- Avoid massive spaghetti piles.


## Virtual Environment (venv) Requirements
The virtual environment must always be active before any terminal commands are executed, and no Python-related shell actions should ever run outside of it. The existing virtual environment is located at the project root and must always be used; no alternative environments or new venvs should be created. Dependencies must never be installed unless the venv is active, including pip installs, upgrades, development tooling, and any CLI actions that rely on Python packages. The venv must be activated as a separate, explicit step before running Python scripts, formatting or linting commands, tests, or build and pipeline scripts. If the venv is not already active, the agent must not proceed under any circumstances. The agent should not attempt to create new virtual environments, modify interpreter paths, or bypass the existing venv in any way. The venv for this repository is located at `\Plattera\.venv` and must be activated using the command `.venv\scripts\activate.ps1` before any other terminal operations.
