# agents.md

## Scope

- Folder: `backend/tooling/mapping/transcript_edit/`
- Purpose: Read dossier transcription runs, build startup ref inventories, hydrate drafts/images by ref.

## Contracts & invariants

- **Refs:** T0 drafts use `t0:raw:<stem>` matching `raw/<stem>.json`. Images use `image:assoc:<transcription_id>:original|processed`. Authored edits (when present): `transcript_edit/working.json`, `transcript_edit/output.json` with refs `transcript_edit:working` / `transcript_edit:output`.
- **Ignore `head.json`** for the agent-facing startup inventory (tooling may use storage internals later without exposing “head” to the model contract).
- **Peer T0 rule:** When `run.json` has `completed_drafts`, that list is canonical. Exclude `raw/<transcription_id>.json` (legacy pointer); if it exists, emit `t0_legacy_pointer_file_present`. Extra raw files → `t0_raw_file_not_in_completed_drafts`; missing listed files → `t0_peer_file_missing`.
- **Hydration cap:** Requests over `max_refs` set `cap_exceeded`, `omitted_ref_ids`, and a `cap_exceeded` error entry; `t0:raw:<transcription_id>` is rejected as `legacy_pointer_alias`.

## Allowed changes

- Safer path checks, extra metadata fields on descriptors, additional missing-resource codes.

## Commands

- Test: from `backend/`, venv active: `pytest tooling/mapping/transcript_edit/test_transcript_edit_startup.py -q`

## Gotchas

- Association paths and image paths are host-specific; hydration returns `exists` flags—callers must handle missing files.

## Links

- Domain payloads: `backend/domains/mapping/transcript_edit/payloads/`
- Paths root: `config.paths.dossier_run_root`, `dossiers_root`
