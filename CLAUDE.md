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
