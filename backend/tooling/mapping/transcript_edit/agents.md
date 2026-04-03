# agents.md

## Scope

- Folder: `backend/tooling/mapping/transcript_edit/`
- Purpose: Read dossier transcription runs, build startup ref inventories, hydrate drafts/images by ref.

## Contracts & invariants

- **Refs:** T0 drafts use `t0:raw:<stem>` matching `raw/<stem>.json`. Images use `image:assoc:<transcription_id>:original|processed`. Authored transcript-edit drafts live under `dossiers_data/artifacts/transcript_edit/<dossier_id>/<transcription_id>/<workspace_id>/` with append-only `working/rev_NNNN.json`, mechanical `working/latest.json`, `manifest.json`, and published `output/output.json`. Aggregate refs: `transcript_edit:working`, `transcript_edit:output`; per-revision ref: `transcript_edit:working:rev:NNNN` (four digits). **Workspace key** = explicit `workspace_id` or `run_id` (same value used for save/hydrate/inventory).
- **Path segments + harness refs:** `dossier_id`, `transcription_id`, and workspace key are validated via `paths.require_safe_path_segment` before building paths — including **T0** `views/transcriptions/...` (`transcription_run_dir`, `run_json_path`, `raw_drafts_dir`) and **association** files (`association_path`), not only `artifacts/transcript_edit/`. Invalid segments yield `invalid_scope_path` (tools), `launch_scope_path_invalid` (startup inventory), or `transcript_edit_scope_path_invalid` (bad workspace key for TE artifacts). Successful `save_transcript_edit` / `publish_transcript_edit_output` include **top-level `artifact_refs`** so `ExecutionSession` merges them into `run_artifact.latest_refs` (continuity / Agent Viewer).
- **Ignore `head.json`** for the agent-facing startup inventory (tooling may use storage internals later without exposing “head” to the model contract).
- **Peer T0 rule:** When `run.json` has `completed_drafts`, that list is canonical. Exclude `raw/<transcription_id>.json` (legacy pointer); if it exists, emit `t0_legacy_pointer_file_present`. Extra raw files → `t0_raw_file_not_in_completed_drafts`; missing listed files → `t0_peer_file_missing`.
- **Hydration cap:** Requests over `max_refs` set `cap_exceeded`, `omitted_ref_ids`, and a `cap_exceeded` error entry; `t0:raw:<transcription_id>` is rejected as `legacy_pointer_alias`.

## Allowed changes

- Safer path checks, extra metadata fields on descriptors, additional missing-resource codes.

## Commands

- Test: from `backend/`, venv active: `pytest tooling/mapping/transcript_edit/test_transcript_edit_startup.py tooling/mapping/transcript_edit/test_transcript_edit_persistence.py -q`

## Gotchas

- Association paths and image paths are host-specific; hydration returns `exists` flags—callers must handle missing files.

## Links

- Domain payloads: `backend/domains/mapping/transcript_edit/payloads/`
- Paths root: `config.paths.dossier_run_root`, `dossiers_root`
