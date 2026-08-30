# agents.md

## Scope

- Folder: `backend/tooling/mapping/transcript_edit/`
- Purpose: Read dossier transcription runs, build startup ref inventories, hydrate drafts/images by ref.

## Contracts & invariants

- **Refs:** Peer T0 drafts use stable alias refs `t0:raw:draft_1`, `t0:raw:draft_2`, ... and resolve to the actual `raw/<transcription_id>_draft_N.json` files for the transcription. Canonical stored stems are `<transcription_id>_draft_1`, `<transcription_id>_draft_2`, etc. The `_draft_N` suffix is the peer-draft identity; `_vN` is reserved for true revision lineage only. Images use `image:assoc:<transcription_id>:original` only. Authored transcript-edit drafts live under `dossiers_data/artifacts/transcript_edit/<dossier_id>/<transcription_id>/<workspace_id>/` with append-only `working/rev_NNNN.json`, mechanical `working/latest.json`, `manifest.json`, and published `output/output.json`. Aggregate refs: `transcript_edit:working`, `transcript_edit:output`; per-revision ref: `transcript_edit:working:rev:NNNN` (four digits). **Workspace key** = explicit `workspace_id` or `run_id` (same value used for save/hydrate/inventory).
- **Path segments + harness refs:** `dossier_id`, `transcription_id`, and workspace key are validated via `paths.require_safe_path_segment` before building paths — including **T0** `views/transcriptions/...` (`transcription_run_dir`, `run_json_path`, `raw_drafts_dir`) and **association** files (`association_path`), not only `artifacts/transcript_edit/`. Invalid segments yield `invalid_scope_path` (tools), `launch_scope_path_invalid` (startup inventory), or `transcript_edit_scope_path_invalid` (bad workspace key for TE artifacts). Successful `save_transcript_edit` / `publish_transcript_edit_output` include **top-level `artifact_refs`** so `ExecutionSession` merges them into `run_artifact.latest_refs` (continuity / Agent Viewer).
- **Ignore `head.json`** for the agent-facing startup inventory (tooling may use storage internals later without exposing “head” to the model contract).
- **Peer T0 rule:** When `run.json` has `completed_drafts`, that list is canonical. Exclude `raw/<transcription_id>.json` (legacy pointer); if it exists, emit `t0_legacy_pointer_file_present`. Extra raw files → `t0_raw_file_not_in_completed_drafts`; missing listed files → `t0_peer_file_missing`.
- **Hydration cap:** Requests over `max_refs` set `cap_exceeded`, `omitted_ref_ids`, and a `cap_exceeded` error entry; `t0:raw:<transcription_id>` is rejected as `legacy_pointer_alias`.
- **Point-crop projection:** `point_crop_set_projection.py` is the single mechanical crop-set projector (legacy slicer may import it temporarily). Do not reintroduce a harness-memory copy.
- **Canonical source immutability:** Canonical dossier images are read-only transform inputs. All new `image:derived:*` bytes and descriptors belong under the owning transcript-edit workspace’s `derived_images` directory.
- **Derived-image storage audit:** Read-only. Coordinator: `derived_image_storage_audit.py`. Inventory / reconstruction / references: sibling `derived_image_storage_*.py` modules. Structural ref field vocabulary lives in `artifact_ref_contract.py` with consumer-specific sets (`ACTION_RESULT_*` vs broader `AUDIT_*` unions). Never authorizes deletion. Generic rendering + `RENDERER_ID` / `GENERIC_SUB_ACTIONS` live solely in `derived_image_rendering.py`. Legacy source-adjacent filenames match `*_derived_<8 hex>.png` only. Reference indexing is structural JSON field walk — prose substrings do not count. Run-owned requires descriptor stem, `ref_id` UUID, and PNG stem to agree.
- **Dossier-scoped foundation:** Dossier machinery is production-reachable only through explicit `transcript_edit_scope_mode="dossier"` selection; the absent selector remains single-transcription mode. `dossier_startup_inventory.py`, `dossier_artifact_refs.py`, `dossier_artifact_hydration.py`, `dossier_action_result_refs.py`, and `dossier_workspace_actions.py` aggregate/qualify/hydrate/route across segments via leaf inventory + leaf handlers. Do not invent active-window harness state here. Every agent-facing inventory field ending in `_ref` / `_refs` must resolve through `DossierStartupInventoryBundle.ref_index`; segment navigation uses `previous_segment_id` / `next_segment_id`. Runtime-minted `transcript_edit:working:rev:NNNN` and `image:derived:*` may resolve after topology run-binding validation without rebuilding the startup index.
- **Dossier publication candidate (read-only):** `dossier_publication_candidate.py` requires an explicit exact working revision (`transcript_edit:working:rev:NNNN`, dossier-qualified) for every topology segment; it validates coverage/lineage and mechanically stitches transcript lanes. It never chooses among runs/drafts and never writes.
- **Dossier publication persistence (append-only):** `dossier_publication_persistence.py` rebuilds a BR-004 candidate then persists it under `artifacts/transcript_edit_dossier/<dossier_id>/<workspace_id>/output/` as immutable `transcript_edit:dossier_output:sha256:<fingerprint>` plus aggregate `transcript_edit:output`. Idempotent replay/orphan recovery only; never chooses runs/drafts and never writes per-segment `output/output.json` or legacy finalized-dossier snapshots.
## Allowed changes

- Safer path checks, extra metadata fields on descriptors, additional missing-resource codes.

## Commands

- Test: from `backend/`, venv active: `pytest tooling/mapping/transcript_edit/test_transcript_edit_startup.py tooling/mapping/transcript_edit/test_transcript_edit_persistence.py tooling/mapping/transcript_edit/test_dossier_startup_inventory.py tooling/mapping/transcript_edit/test_dossier_artifact_hydration.py tooling/mapping/transcript_edit/test_dossier_artifact_refs.py tooling/mapping/transcript_edit/test_dossier_action_result_refs.py tooling/mapping/transcript_edit/test_dossier_workspace_actions.py tooling/mapping/transcript_edit/test_dossier_publication_candidate.py tooling/mapping/transcript_edit/test_dossier_publication_persistence.py tooling/mapping/transcript_edit/test_derived_image_persistence.py tooling/mapping/transcript_edit/test_derived_image_storage_audit.py -q`
- Audit CLI: `python -m tooling.mapping.transcript_edit.audit_derived_image_storage --dossier-id <id>` (read-only; no `--apply`)
- Topology: from `backend/`, venv active: `pytest services/dossier/test_segment_topology.py -q`

## Gotchas

- Association paths and image paths are host-specific; hydration returns `exists` flags—callers must handle missing files.

## Links

- Domain payloads: `backend/domains/mapping/transcript_edit/payloads/`
- Paths root: `config.paths.dossier_run_root`, `dossiers_root`
