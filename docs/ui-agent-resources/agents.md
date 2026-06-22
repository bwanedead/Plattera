# agents.md

## Scope
- Folder: `docs/ui-agent-resources/`
- Purpose: Git-safe replay data and contracts for universal agent-viewer development.

## Contracts & invariants
- The viewer core is domain-agnostic; transcript-edit is representative data, not the platform schema.
- Generated fixtures contain no raw prompts, binary media, secrets, or absolute local paths.
- Unknown tools, state fields, events, and artifact kinds must remain inspectable.
- Cloud UI work must not edit `backend/harness/`, active domain packs, or domain tooling; adapt only at the viewer-owned intake seam or document an upstream contract need.

## Allowed changes
- Improve the platform contract, fixture generator, validation, and optional domain examples.
- Do not hand-edit generated fixture files; update the generator and regenerate them.

## Commands
- Test: `.venv\scripts\activate.ps1; python docs/ui-agent-resources/scripts/build_transcript_edit_replay.py`
- Lint: `.venv\scripts\activate.ps1; python -m py_compile docs/ui-agent-resources/scripts/build_transcript_edit_replay.py`
- Build/Run: Not applicable.
- Other: Inspect `fixtures/<run-id>/replay_manifest.json` first.

## Gotchas
- Media refs intentionally resolve to `media/placeholder.svg`; real deed images are not committed.
- Turn snapshots omit before-state copies; derive them from the prior turn's after-state.

## Links
- Docs: `docs/ui-agent-resources/cloud-agent-initiation-brief.md`
- Docs: `docs/architecture/agent-viewer-product-vision.md`
- Docs: `docs/ui-agent-resources/platform-viewer-contract.md`
- Related code: `backend/harness/`
