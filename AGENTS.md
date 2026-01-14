# Repository Guidelines

# Repo Operating Rules (read first)

This file defines non-negotiables and working norms for any agent (including Ralph loops) operating in this repository.

---

## 1) Safety / blast-radius rules (non-negotiable)

### Protected branches
- Do NOT checkout, commit to, push to, or modify protected branches:
  - `main`
  - `agent-loop-building`
- Work only on the current working branch (e.g. `ralph/*`, `feature/*`, etc.).

### Never-dos (hard bans)
- Never delete or modify anything outside the repository root.
- Never run destructive / wide delete commands, especially anything that could target a drive/root/home, such as:
  - `rm -rf /`, `rm -rf ~`, `rm -rf ..`
  - `del /s`, `rmdir /s`
  - `Remove-Item -Recurse C:\*` or any absolute-path recursive deletion
- Never delete or modify `.git/` or git internals.
- Never use absolute paths for deletion or edits.
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

## Coding Style & Naming Conventions
Follow PEP 8: four-space indentation, `snake_case` functions, `PascalCase` classes, and descriptive module names (`georeference_service.py`). Prefer type hints and Pydantic models for payloads. In TypeScript, use functional components, `PascalCase` filenames in `components/`, and `camelCase` for hooks or util exports (for example `useAlignmentStatus`). Co-locate styles in `styles/` and reuse Leaflet tokens. Log via `logging.getLogger(__name__)` or the colored formatter configured in `backend/main.py`.

## Testing Guidelines
Most integration checks assume the API is running at `localhost:8000`; start the server before executing scripts such as `python test_alignment_api.py` or `python test_api.py`. For deterministic coverage, add pytest cases alongside the code (`pytest backend/test_pyproj_behavior.py`) and keep fixtures in JSON next to the test. Document required environment variables in the test docstring when hitting external services.

## Commit & Pull Request Guidelines
Recent commits are concise status lines (`ui improvements in regard to buttons...`). Mirror that style: keep the subject under 72 characters, mention the affected surface first, and describe the user-visible change. Reference issues when possible. Pull requests should include a short intent paragraph, manual test evidence (CLI output or screenshots for UI changes), notes on schema or prompt updates, and any datasets that need regeneration.

## Architecture Expectations
All development must follow modular, scalable architecture with strict separation of concerns. Code should not be placed into large, catch-all files or allowed to deteriorate into spaghetti structures. Each module or component should have a clearly defined responsibility, and coupling between unrelated parts of the system should be avoided. Maintainability, clarity, extensibility, and long-term soundness take priority over any fast workaround or short-term patch. When there is a choice between a quick implementation and a structurally correct solution, the more robust and reliable option should always be taken. Shortcuts that compromise future stability, readability, or adaptability should not be used.


## Virtual Environment (venv) Requirements
The virtual environment must always be active before any terminal commands are executed, and no Python-related shell actions should ever run outside of it. The existing virtual environment is located at the project root and must always be used; no alternative environments or new venvs should be created. Dependencies must never be installed unless the venv is active, including pip installs, upgrades, development tooling, and any CLI actions that rely on Python packages. The venv must be activated as a separate, explicit step before running Python scripts, formatting or linting commands, tests, or build and pipeline scripts. If the venv is not already active, the agent must not proceed under any circumstances. The agent should not attempt to create new virtual environments, modify interpreter paths, or bypass the existing venv in any way. The venv for this repository is located at `\Plattera\.venv` and must be activated using the command `.venv\scripts\activate.ps1` before any other terminal operations.
