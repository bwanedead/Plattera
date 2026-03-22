# agents.md

## Scope
- Folder: `backend/harness/work_board/`
- Purpose: mission-agnostic work-board envelope, emergent item application, and lifecycle stamps.

## Contracts & invariants
- `evaluate_add_item_promotion` gates on **generic** structural signals only (materiality, priority ≥ 70, dependencies, evidence refs, resolution text length). It does **not** interpret `blocking_impact` (Phase 29).
- `blocking_impact` on board rows is opaque domain payload for storage/display; not harness ontology.

## Allowed changes
- Adjust generic heuristics with tests; keep promotion free of mission-specific label branches.

## Commands
- Test: `pytest backend/harness/work_board/test_emergence.py backend/harness/work_board/test_lifecycle.py`

## Gotchas
- Domain packs that relied on transcript-shaped `blocking_impact` strings for promotion must supply generic signals (evidence, deps, high materiality, substantive resolution, or raised priority) before shared emergence.

## Links
- Docs: `docs/architecture/harness/harness-constitution.md`
