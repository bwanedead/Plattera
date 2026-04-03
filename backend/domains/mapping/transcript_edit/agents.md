# agents.md

## Scope

- Folder: `backend/domains/mapping/transcript_edit/`
- Purpose: Semantic doctrine, payload contracts, tool *declarations*, and projection—no dossier filesystem access.

## Contracts & invariants

- **Domain vs tooling:** Dossier I/O and ref resolution live in `backend/tooling/mapping/transcript_edit/` only.
- **Startup payloads** (`payloads/startup_inventory.py`) are ref-first inventories for model-facing assembly—not persistence services, no “next action” scripting, no draft ranking.
- **TranscriptEditAuthoredDraftPosture** (`working_draft_ref` / `output_draft_ref`) models the agent-authored transcript-edit draft only. Legacy `final_selection` maps may be coerced for compatibility but `selected_final_ref` is not part of the domain shape.
- `runtime_adapter/` is the only harness-facing seam here; it may translate prompt blocks, startup inventories, and tool ids into generic `harness.runtime.composition` surfaces, but it must not author mission-state, closure, or ranking.

## Allowed changes

- Prompt/tool-spec updates that keep closure layers and mapping purpose intact.
- New semantic payload dataclasses under `payloads/` when they stay non-orchestrating.

## Commands

- Test: from `backend/`, venv active: `pytest domains/mapping/transcript_edit/test_transcript_edit_pack.py -q`

## Gotchas

- `save_transcript_edit` and `publish_transcript_edit_output` are wired in `runtime_adapter/composition.py`; other tools may still be declarative-only—keep `execution/tool_specs.py` honest.

## Links

- Tooling: `backend/tooling/mapping/transcript_edit/`
- Spec: `docs/transcription-dossier-system-spec.md`
