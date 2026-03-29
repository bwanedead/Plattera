# Transcription Edit Loop Disposition (Raptor Pass)

Date: 2026-03-29  
Status: Active extraction checkpoint  
Scope: transcript-edit extraction surfaces

`backend/transcription_edit_loop/` is not a permanent root and should not be revived as one.
Deterministic capability code and workflow support were split out to their target roots.

## Keep (deterministic tooling worth relocating)

- `apply.py`
- `contracts.py`
- `validators.py`
- `section_adapter.py`
- `span_seeds.py`

These deterministic capability pieces now live at:

- `backend/tooling/mapping/transcription_edit/`

## Workflow/application support (not tooling)

- `persistence.py`
- `run_registry.py`

These are runtime/application support concerns, not deterministic tooling.
They now live at:

- `backend/services/workflows/mapping/transcription_edit/`

Important:

- these files are **not** deterministic capability tooling just because tool implementations currently import them
- persistence and run registry belong under workflow-service roots, not tooling roots
- `run_service.py` has been removed; pipeline repair now uses direct orchestration with tooling + persistence

## Not final architecture commitments

- Do not restore `backend/transcription_edit_loop/` as a long-term root.
- Do not add new family runtime species.
- Keep separation clear: tooling vs workflow support.

## Exit criteria for this island

This slice should be considered fully resolved only when both are true:

1. deterministic capability pieces remain under `backend/tooling/...` with direct imports; and
2. workflow support surfaces are either:
   - re-homed under `backend/services/workflows/...`; or
   - deleted if no longer required.
