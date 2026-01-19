# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Reference

**Before any work:** Read `AGENTS.md` for non-negotiables (safety rules, git restrictions, venv requirements).

**Before editing:** Review `docs/ethos/` files and any local `agents.md` in the target directory.

## Development Commands

### Backend (Python/FastAPI)
```powershell
# Activate venv FIRST (mandatory)
.\.venv\scripts\activate.ps1

# Run dev server
cd backend
python main.py                    # localhost:8000

# Run tests
pytest test_pyproj_behavior.py    # specific file
pytest backend/corpus/            # module tests
```

### Frontend (Next.js/TypeScript)
```powershell
cd frontend
npm install                       # one-time setup
npm run dev                       # localhost:3000
npm run tauri:dev                 # desktop shell with hot reload
```

### Production Build (Desktop)
```powershell
# 1. Build backend sidecar (from backend/, venv active)
pyinstaller --noconfirm --onefile --name plattera-backend --hidden-import openai --hidden-import services.llm.openai --add-data "schema\plss_m_and_b.json;backend/schema" main.py

# 2. Copy sidecar (from backend/)
Copy-Item ".\dist\plattera-backend.exe" "..\frontend\src-tauri\bin\plattera-backend-x86_64-pc-windows-msvc.exe" -Force

# 3. Build Tauri bundles (from frontend/)
npm run tauri:build
```

## Architecture Overview

**Three-tier desktop app:** Tauri shell → Next.js frontend → FastAPI backend

```
┌─────────────────────────────────────────────────────────────┐
│                    TAURI DESKTOP SHELL                       │
│         (spawns backend sidecar, auto-update system)         │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────────┐
│              FRONTEND (Next.js + React + TS)                 │
│         localhost:3000 → localhost:8000 (API)                │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────────┐
│              BACKEND (FastAPI + Python)                      │
│                    localhost:8000                            │
├─────────────────────────────────────────────────────────────┤
│  api/        → 35+ endpoints organized by domain             │
│  services/   → dossier, LLM, OCR, PLSS, georeference         │
│  pipelines/  → image_to_text, text_to_schema, mapping        │
│  corpus/     → virtual provider, semantic indexing, views    │
│  retrieval/  → RAG engine with hybrid lanes (lexical/vector) │
│  agents/     → autonomous agent orchestration loop           │
│  alignment/  → BioPython-based draft consensus alignment     │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow: Legal Description → Visual Boundary

1. **Image → Text**: OCR + LLM transcription of legal documents
2. **Text → Schema**: Parse legal description into structured parcel schema (metes and bounds, PLSS)
3. **Schema → Georeference**: Map schema to geographic coordinates using PLSS reference data
4. **Georeference → Polygon**: Render final boundary on map

### Key Patterns

**Artifact-driven persistence:** Data saved as JSON files in `LOCALAPPDATA\Plattera\Data`, not held in memory. UI components hydrate from disk artifacts.

**Service registry:** `backend/services/registry.py` handles runtime initialization of all services.

**Co-located tests:** Tests live next to modules they validate (`backend/corpus/test_*.py`), not in root.

## Backend Structure

| Directory | Purpose |
|-----------|---------|
| `api/` | FastAPI routers organized by domain (alignment, dossier, polygon, etc.) |
| `services/` | Business logic (LLM providers, OCR, georeference, PLSS data) |
| `pipelines/` | Multi-step processing (image_to_text, text_to_schema, mapping/georeference) |
| `corpus/` | Semantic corpus with virtual provider, views (FINAL_SEGMENTS, Everything) |
| `retrieval/` | RAG system: evidence lanes, filters, reranking, orchestration |
| `agents/` | Autonomous agent loop: toolbelt, contracts, corpus_chat, schema_mapping |
| `alignment/` | BioPython sequence alignment for draft consensus |
| `prompts/` | LLM prompt templates |

## Frontend Structure

| Directory | Purpose |
|-----------|---------|
| `src/components/` | React components by feature (dossier/, mapping/, schema/, plss/) |
| `src/hooks/` | Custom hooks for state management |
| `src/services/` | API client wrappers |
| `src/pages/` | Next.js routes |
| `src-tauri/` | Tauri config, Rust source, sidecar binaries |

## Testing

Tests use pytest. Run specific tests, not full suite:

```powershell
pytest backend/corpus/test_virtual_corpus.py
pytest backend/retrieval/test_provenance_lane.py
```

**Weight-bearing invariants to test:**
- No crashes in normal failure scenarios
- Stable IDs/hashes across runs
- Hydration returns consistent shapes
- Missing data returns explicit reason, not mystery error

## Current Development Focus

Branch `agent-loop-building` is developing autonomous agent capabilities:
- Corpus semantic indexing with deterministic chunking
- Hybrid retrieval (lexical + vector + semantic lanes)
- Agent orchestration loop for gap detection and synthesis

### Additional Guidence

## 1) Safety / blast-radius rules (non-negotiable)

### Protected branches
- Do NOT checkout, commit to, push to protected branches, working and modifying as asked is fine, the purpose of this rule is to prevent unwanted git pushes:
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

