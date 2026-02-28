# Transcription + Dossier System Specification

Status: Implementation-derived spec (current behavior)  
Scope: Image-to-text transcription, draft/version state, dossier storage model, consensus/alignment flows, finalization pipeline  
Audience: Engineers and external LLMs without repo access

---

## 1) Purpose and Mental Model

Plattera's transcription system is an artifact-first pipeline that:

1. Converts deed images into text drafts (often multiple redundant drafts).
2. Persists those drafts into dossier-scoped storage, with explicit run and head state.
3. Allows post-processing variants (alignment drafts, LLM consensus, alignment consensus, edits).
4. Supports strict per-segment final draft selection.
5. Produces dossier-level finalized stitched snapshots.

The filesystem under `backend/dossiers_data/` is the durable source of truth.  
Frontend state hydrates from those artifacts rather than being canonical itself.

---

## 2) Architectural Layers

### 2.1 Ingestion and orchestration

- API entrypoints:
  - `backend/api/endpoints/processing.py`
  - `backend/api/endpoints/dossier/dossier_image_processing.py`
  - `backend/api/endpoints/image_to_text_jobs.py` (queue path)
- Pipeline core:
  - `backend/pipelines/image_to_text/pipeline.py`
  - `backend/pipelines/image_to_text/redundancy.py`
  - `backend/pipelines/image_to_text/image_processor.py`
  - `backend/pipelines/image_to_text/final_draft_selector.py`

### 2.2 Dossier domain and persistence

- Domain models:
  - `backend/services/dossier/models.py`
- Services:
  - `backend/services/dossier/management_service.py`
  - `backend/services/dossier/association_service.py`
  - `backend/services/dossier/edit_persistence_service.py`
  - `backend/services/dossier/progressive_draft_saver.py`
  - `backend/services/dossier/final_registry_service.py`
  - `backend/services/dossier/finalization_service.py`
  - `backend/services/dossier/view_service.py`

### 2.3 Consensus and alignment

- Alignment APIs/services:
  - `backend/api/endpoints/alignment.py`
  - `backend/services/alignment_service.py`
- Consensus APIs:
  - `backend/api/endpoints/llm_consensus.py`
  - `backend/api/endpoints/consensus.py`

### 2.4 Retrieval/corpus hydration over dossier artifacts

- `backend/corpus/adapters/dossiers_fs.py`
- `backend/corpus/hydrate.py`
- `backend/corpus/views/final_segments.py`
- `backend/corpus/views/everything.py`

---

## 3) Canonical Data Entities

Defined in `backend/services/dossier/models.py`.

### 3.1 Dossier

Core fields:
- `id`, `title`, `description`, `created_at`, `updated_at`
- `segments[]`
- `manual_segments[]`
- `segment_name_overrides{}`
- `active_text_source` (hook for future source policy)

### 3.2 Segment

Logical grouping unit in a dossier:
- `id`, `name`, `description`, `position`
- `runs[]`

Current practical pattern is often 1 transcription -> 1 auto-generated segment, but the model supports richer structure.

### 3.3 Run

Represents one processing run for a transcription id:
- `id`, `transcriptionId`, `position`
- `status`: `processing | completed | failed`
- `redundancy_count`
- `completed_drafts[]`
- `has_llm_consensus`, `has_alignment_consensus`
- `processing_params`
- `started_at`, `finished_at`
- `drafts[]`

### 3.4 Draft

Renderable variant entry:
- `id`, `position`, `transcriptionId`
- `isBest`
- `metadata` including `versions` map and status hints

---

## 4) Storage Topology and Path Contracts

Paths are centralized in `backend/config/paths.py`.  
In dev mode, data resolves under `backend/dossiers_data/`.

## 4.1 Top-level directories

- `management/` -> dossier records
- `associations/` -> dossier/transcription relationships
- `views/transcriptions/` -> run folders and versioned draft artifacts
- `state/` -> final registries and global indexes
- `images/` -> original/processed image copies
- `processing_jobs/` -> batch queue job metadata
- `artifacts/` -> other artifact families (schemas/georefs/feature graph/agent kernel)

### 4.2 Dossier management records

- `backend/dossiers_data/management/dossier_<dossier_id>.json`

Contains dossier metadata and (materialized) segment/run/draft hierarchy for listing/navigation purposes.

### 4.3 Transcription associations

- `backend/dossiers_data/associations/assoc_<dossier_id>.json`

Contains ordered `transcription_id` associations and per-association metadata (provenance, images, params).

### 4.4 Run storage root

Per transcription run:

- `backend/dossiers_data/views/transcriptions/<dossier_id>/<transcription_id>/`

Subfolders/files:
- `run.json` (run execution state)
- `head.json` (raw/alignment/consensus/final head pointers)
- `raw/` (raw draft variants)
- `alignment/` (alignment-per-draft variants)
- `consensus/` (LLM/alignment consensus variants)
- `final/` (dossier final snapshots, at dossier-level path)

### 4.5 Segment-final registry

- `backend/dossiers_data/state/<dossier_id>/final_registry.json`

Schema:
- `segments[segment_id] = {transcription_id, draft_id, set_at, set_by}`

This is the canonical segment-final selection source used by finalization and corpus final-segment view.

### 4.6 Finalized index

- `backend/dossiers_data/state/finalized_index.json`

Stores summarized finalized dossier entries for listing.

---

## 5) Transcription Pipeline Flow (Natural End-to-End)

## 5.1 Pre-init path (recommended dossier UX)

1. Client calls `POST /api/dossier-runs/init-run`.
2. Backend ensures dossier exists (or creates it).
3. Backend determines `transcription_id`.
4. Backend writes `run.json` skeleton and optional placeholder draft files.
5. Backend creates association record so UI can show run immediately.

## 5.2 Processing execution path

1. Client calls `POST /api/dossier/process` (or generic `/api/process` with dossier params).
2. Endpoint parses enhancement + redundancy + consensus config.
3. Pipeline:
   - resolves model service from registry
   - prepares enhanced base64 image
   - generates extraction prompt
   - executes:
     - single call (`process`) if redundancy = 1
     - parallel calls (`process_with_redundancy`) if redundancy > 1
4. Redundancy processor filters failures/refusals and picks best draft (currently longest valid extraction heuristic).
5. Progressive saver persists each completed draft incrementally and updates run metadata.
6. Endpoint/service persists association metadata/provenance/images and optional consensus files.
7. Run status is finalized and events are emitted for UI refresh.

## 5.3 Batch queue path

1. Client submits files to `POST /api/image-to-text/jobs`.
2. Job records saved under `processing_jobs/image_to_text`.
3. Sequential worker (`queue_service.py`) runs jobs.
4. Worker performs same dossier/run bootstrap + pipeline processing + persistence lifecycle.

---

## 6) Version and State Semantics (v1/v2/av1/av2/consensus)

This section formalizes the practical meaning of states like `v1`, `v2`, `av1`, `av2`.

## 6.1 Raw drafts

Per redundancy slot `n`:
- Base head file: `<tid>_v<n>.json`
- Optional immutable baseline backup: `<tid>_v<n>.v1.json`
- Optional edited variant: `<tid>_v<n>.v2.json`

Strict identifier form used by FE selection logic:
- `<tid>_v<n>_v1`
- `<tid>_v<n>_v2`

Interpretation:
- `v1` = initial/raw baseline content for slot
- `v2` = edited or revised content for same slot

## 6.2 Alignment per-draft variants (Av1/Av2)

For raw slot `n`:
- `alignment/draft_<n>_v1.json` -> Av1
- `alignment/draft_<n>_v2.json` -> Av2
- `alignment/draft_<n>.json` -> current head copy

Strict IDs:
- `<tid>_draft_<n>_v1` (Av1)
- `<tid>_draft_<n>_v2` (Av2)

Interpretation:
- Av1 = first persisted alignment output for that draft slot
- Av2 = second/edit alignment revision

## 6.3 Consensus variants

LLM consensus:
- `consensus/llm_<tid>.json` (head/base)
- optional `llm_<tid>_v1.json`, `llm_<tid>_v2.json`

Alignment consensus:
- `consensus/alignment_<tid>.json` (head/base)
- optional `alignment_<tid>_v1.json`, `alignment_<tid>_v2.json`

Strict IDs:
- `<tid>_consensus_llm_v1|v2`
- `<tid>_consensus_alignment_v1|v2`

Base IDs:
- `<tid>_consensus_llm`
- `<tid>_consensus_alignment`

## 6.4 Run state flags

In `run.json`:
- `has_llm_consensus`
- `has_alignment_consensus`
- `status`
- `completed_drafts[]`

These control rendering and processing progress semantics in dossier UI.

---

## 7) Head and Selection Tracking

Central file: `head.json` in each run folder.

Typical structure:
- `raw.head`
- `alignment.head` (global alignment head)
- `raw_heads{ "<tid>_v<n>": "v1|v2" }`
- `alignment_heads{ "<tid>_draft_<n>": "v1|v2" }`
- `consensus.llm.head`
- `consensus.alignment.head`
- `final.selected_id` (legacy local final pointer)

### 7.1 Edit operations

`backend/services/dossier/edit_persistence_service.py` supports:
- save raw v2
- save per-draft raw v2
- revert raw/per-draft to v1
- save alignment v1/v2
- revert alignment to v1
- save consensus llm/alignment v2
- set/clear/get final selection in `head.json`

---

## 8) Final Selection Model (Segment Finals)

Current system has two selection surfaces:

1. **Legacy/local pointer:** `head.json.final.selected_id`
2. **Canonical segment finals:** `state/<dossier_id>/final_registry.json`

The canonical per-segment selection APIs are in:
- `backend/api/endpoints/dossier/final_selection.py`
- `backend/api/endpoints/dossier/finals.py`

Segment final set/get/clear resolves segment id by transcription and writes strict `draft_id` into `final_registry.json`.

---

## 9) Finalization Pipeline

Primary endpoint:
- `POST /api/dossier/finalize`

Implementation:
- `backend/services/dossier/finalization_service.py`

Algorithm per segment:
1. pick run (current implementation picks first run in segment)
2. check registry final for that segment
3. if final exists, load that exact draft id
4. otherwise fallback policy:
   - consensus first
   - then `isBest`
   - then longest
   - then first
5. append selected text to stitched output
6. record section-level `draft_id_used`

Outputs:
- timestamped snapshot: `final/dossier_final_<timestamp>.json`
- pointer snapshot: `final/dossier_final.json`
- finalized index update: `state/finalized_index.json`

Snapshot includes:
- stitched text
- sections with provenance
- selection map
- error list
- hash

---

## 10) Provenance and Image Artifacts

Provenance schema:
- `backend/services/dossier/provenance_schema.py`

Recorded fields include:
- source file hash/path/size/mtime
- processing engine/model/mode/date
- quality metrics
- enhancement settings + enhancement hash
- lineage scaffold

Image storage:
- `backend/services/dossier/image_storage_service.py`
- saved under:
  - `images/original/`
  - `images/processed/`

Association metadata often embeds:
- `metadata.provenance`
- `metadata.images` with local paths and optional URL projections

---

## 11) API Surface Summary

Main routes (prefixes omitted for brevity):

- Processing
  - `/api/process`
  - `/api/dossier/process`
  - `/api/dossier-runs/init-run`
  - `/api/image-to-text/jobs`

- Dossier CRUD
  - `/api/dossier-management/...`
  - `/api/transcription-association/...`
  - `/api/dossier-navigation/...`
  - `/api/dossier-views/...`

- Editing/versioning
  - `/api/dossier/edits/save`
  - `/api/dossier/edits/head`
  - `/api/dossier/versions/set-raw-head`
  - `/api/dossier/versions/revert-to-v1`

- Consensus/alignment
  - `/api/alignment/...`
  - `/api/llm-consensus/generate`
  - `/api/consensus/generate-consensus`

- Final selection/finalization
  - `/api/dossier/final-selection/set|get|clear`
  - `/api/dossier/finalize`
  - `/api/dossier/final/<dossier_id>`
  - `/api/dossier/finalized/list`
  - `/api/dossier/{dossier_id}/finals` and segment-final subroutes

---

## 12) Read/Hydration Semantics for Retrieval and External Consumers

Draft resolution:
- `backend/corpus/adapters/dossiers_fs.py` maps strict/base IDs to actual files with compatibility fallbacks.

Hydration:
- `backend/corpus/hydrate.py` converts refs to entry text.
- For segment finals, it resolves draft path from final registry data and extracts text from:
  - `sections[].body`, else `text`, else `mainText`.

Corpus views:
- `FINAL_SEGMENTS` reflects per-segment final selections.
- `EVERYTHING` currently conservative over transcription heads.

---

## 13) State Machine View (Operational)

### 13.1 Run lifecycle

1. `init-run` -> `run.json.status = processing` + placeholders.
2. Draft completions append to `completed_drafts`.
3. Consensus/alignment flags set as produced.
4. Run set to `completed` when enough outputs persist.
5. Edits may produce new per-draft v2/Av2/consensus-v2 variants while run remains completed.

### 13.2 Segment final lifecycle

1. No final selected -> fallback policy used for reads/finalization.
2. Final selected in registry -> strict draft id pinned for that segment.
3. Final cleared -> returns to fallback behavior.
4. Dossier finalize snapshot captures current registry/fallback choices.

---

## 14) Known Tensions and Refactor Risks

These are critical for safe rework.

1. Dual final-selection storage exists:
   - `head.json.final.selected_id` vs canonical `final_registry.json`.
2. Path/ID compatibility layers are broad (legacy + strict variants).
3. Multiple ingestion paths perform similar persistence responsibilities:
   - generic processing endpoint
   - dossier-specific endpoint
   - queue worker path
4. Consensus version variants (`_v1/_v2`) are supported conceptually, but generation/persistence can be inconsistent by route.

---

## 15) Refactor Safety Invariants (Do Not Break Without Migration)

1. Keep artifact-first truth (filesystem canonical).
2. Preserve strict ID vocabulary until full migration:
   - raw strict ids, alignment strict ids, consensus strict ids.
3. Preserve run/head file compatibility or provide migration tooling.
4. Preserve final registry semantics as canonical segment-final source.
5. Preserve deterministic text extraction/hydration behavior for retrieval.
6. Preserve eventing hooks for progressive UI updates.

---

## 16) Suggested Canonicalization Targets (Future)

Recommended cleanup directions:

1. Make `final_registry.json` the single final-selection source; deprecate `head.json.final`.
2. Consolidate processing persistence into one shared service used by all entrypoints.
3. Publish formal schemas for:
   - `run.json`
   - `head.json`
   - final registry
   - strict draft id grammar
4. Add migration utilities for legacy filename variants.
5. Add test matrix around version resolution and finalization correctness.

---

## 17) Quick Glossary

- **Dossier**: top-level container for related deed transcriptions.
- **Segment**: logical part of dossier; often one transcription today.
- **Run**: processing lifecycle for one transcription id.
- **Draft**: specific text variant rendered in UI.
- **Raw v1/v2**: baseline/edited raw draft variant.
- **Av1/Av2**: alignment per-draft baseline/edited variant.
- **Consensus (LLM/alignment)**: merged draft forms.
- **Head**: pointer to current selected version among variants.
- **Final selection**: strict segment-level chosen draft id.
- **Finalized dossier**: stitched snapshot using finals/fallback policy.

---

## 18) Source-of-Truth File Map

Primary implementation files referenced by this spec:

- `backend/config/paths.py`
- `backend/services/dossier/models.py`
- `backend/services/dossier/management_service.py`
- `backend/services/dossier/association_service.py`
- `backend/services/dossier/edit_persistence_service.py`
- `backend/services/dossier/progressive_draft_saver.py`
- `backend/services/dossier/final_registry_service.py`
- `backend/services/dossier/finalization_service.py`
- `backend/services/dossier/view_service.py`
- `backend/pipelines/image_to_text/pipeline.py`
- `backend/pipelines/image_to_text/redundancy.py`
- `backend/api/endpoints/processing.py`
- `backend/api/endpoints/dossier/dossier_image_processing.py`
- `backend/api/endpoints/dossier/dossier_run_initialization.py`
- `backend/api/endpoints/dossier/final_selection.py`
- `backend/api/endpoints/dossier/finalize.py`
- `backend/api/endpoints/alignment.py`
- `backend/services/alignment_service.py`
- `backend/corpus/adapters/dossiers_fs.py`
- `backend/corpus/hydrate.py`

