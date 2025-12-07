## Plattera Desktop EXE – Build & Runtime Issues Log (v0.9.x)

This document tracks the known issues and fixes specific to the **Windows EXE / Tauri desktop build**, so we can keep a clear history of what’s been done and what’s still outstanding.

Use this as the working checklist for future EXE rounds. When we close an item, **leave it here** with a short note instead of deleting it, so we preserve context.

---

## ✅ Resolved / Verified Items

- **Sidecar startup & shutdown**
  - [x] Backend sidecar starts with the Tauri app and serves on `http://localhost:8000`.
  - [x] `/api/cleanup` schedules a delayed `os._exit(0)` and performs best-effort cleanup, so the process exits even if cleanup fails.
  - [x] Tauri close handler calls `/api/cleanup` with a generous timeout and then kills any remaining child, freeing port `8000`.
  - [x] Verified via PowerShell (`Get-NetTCPConnection -LocalPort 8000 -State Listen`) that port 8000 is not left in `LISTEN` state after app exit.

- **Centralized data roots (EXE vs dev)**
  - [x] Backend now routes dossiers and related data under `%LOCALAPPDATA%\Plattera\Data\...` in frozen EXE mode.
  - [x] Confirmed paths for:
    - Dossier management JSON: `%LOCALAPPDATA%\Plattera\Data\dossiers_data\management\...`
    - Run metadata: `%LOCALAPPDATA%\Plattera\Data\dossiers_data\views\transcriptions\...`
    - Image originals / processed: `%LOCALAPPDATA%\Plattera\Data\dossiers_data\images\{original,processed}\...`
    - Redundancy drafts and LLM consensus: `%LOCALAPPDATA%\Plattera\Data\dossiers_data\views\transcriptions\...\{raw,consensus}\...`
  - [x] Dev mode still uses repo-relative paths under `backend/` for the same data.

- **Redundancy pipeline (image → text)**
  - [x] `redundancy_count == 1` path fixed to persist draft JSON under the stable views root instead of a transient `_MEI` directory.
  - [x] `redundancy_count > 1` + auto LLM consensus:
    - Progressive drafts saved as `draft_<id>_v{1..N}.json` with `.v1` snapshots.
    - LLM consensus JSON saved under `.../consensus/llm_<transcription>.json`.
    - Immediate UI state after a run can select between drafts and consensus.

- **Tauri logging**
  - [x] `tauri_plugin_log` configured in a version-compatible way for our current Tauri/RC plugin combo.
  - [x] Logs persisted to disk in installed builds and used to diagnose backend startup, shutdown, and pipeline behavior.

- **Build process documentation**
  - [x] `docs/build-process.md` updated with:
    - Correct PyInstaller command (including `--add-data` for PLSS schema, though current EXE indicates this still needs verification).
    - Copy commands for sidecar into `frontend/src-tauri/`.
    - ZIP + `.sig` + `latest.json` generation steps that match the current release workflow.

---

## 🚧 Open Issues / Next-Round TODOs

### 1. Updater – `error decoding response body`

- **Symptoms**
  - [ ] In dev and installed EXE, clicking “Check for Updates” shows:  
        `Updater check failed: error decoding response body`.
  - [x] From within Tauri dev, `fetch("https://raw.githubusercontent.com/bwanedead/Plattera/main/releases/latest.json")` returns valid JSON and parses fine in JS.
  - [x] `frontend/src-tauri/tauri.conf.json` `updater.endpoints[0]` points at the raw `latest.json` URL on `raw.githubusercontent.com`.

- **Hypothesis**
  - Likely a **serde / schema mismatch or plugin bug** inside `tauri-plugin-updater` v2, not a network or JSON-format problem.

- **Planned work**
  - [x] Implement Rust-side logging helper and debug command:
    - `debug_updater_endpoint` Tauri command logs HTTP status, headers and raw body for the configured endpoint.
    - Sidecar/stdout/stderr now flow through `tauri_plugin_log` with elevated log levels for `tauri_plugin_updater`.
  - [ ] Once we see the real error from the plugin in EXE/dev logs, either:
    - [ ] Adjust `latest.json` schema to match plugin expectations, or
    - [ ] Wrap the plugin with a small custom deserializer that matches Tauri’s latest manifest format.
  - [ ] Re-test `check()` in dev and EXE until it cleanly reports “up to date” or a valid `update.available === true`.

- **Status notes (2025‑12‑06 EXE test round)**
  - [x] Built new EXE, updated `releases/latest.json` signature, and copied it into `bundle/latest.json`.
  - [x] In EXE and Tauri dev, `check()` still reports `error decoding response body`; Tauri log only shows repeated `checking for updates ...latest.json` debug lines with no serde error detail.
  - [ ] `debug_updater_endpoint` is not yet wired into any UI path, so we still **do not** have the raw manifest body/headers from inside the app.
  - **Status notes (2025‑12‑07 EXE test round)**
    - [x] Re-verified that installed EXE still shows `Updater check failed: error decoding response body` with no additional serde details in Tauri logs.
    - [ ] Next step remains to add a small, temporary UI hook that calls `debug_updater_endpoint` so we can capture `UPDATER_DEBUG` lines (status, content-type, full body) in the Tauri log.

### 2. Dossier association – “Auto-create” vs existing segment

- **Symptoms**
  - [x] Dossier picker in the image-processing control panel shows “Auto-create new dossier” when value is `null`.
  - [x] When no dossier has been interacted with in the Dossier Manager, runs with “Auto-create” correctly create a brand‑new dossier.
  - [x] After clicking a dossier in the Dossier Manager (blue highlight), subsequent runs with “Auto-create new dossier” selected often attach as **new segments in that highlighted dossier**.

- **Likely root cause**
  - `useImageProcessing` maintains its own `internalSelectedDossierId` and computes:
    - `dossierIdToSend = (internalSelectedDossierId || selectedDossierId) || undefined;`
  - The Dossier Manager selection and/or previous auto-created dossiers end up populating this internal id, so “Auto-create” in the control panel does **not** guarantee that no dossier id is sent to the backend.

- **Planned work**
  - [x] Refactor `useImageProcessing` so that when `selectedDossierId` is provided from `ImageProcessingWorkspace`, it is treated as **source of truth**, and “Auto-create” (`null`) means `dossierIdToSend === undefined`.
  - [x] Ensure Dossier Manager highlighting does not implicitly change the dossier used for processing; Control Panel is now authoritative.
  - [x] When `initRun` auto-creates a dossier, propagate that id back into the workspace (`onAutoCreatedDossierId`) so the picker shows the newly created dossier explicitly for subsequent runs.
  - [ ] Regression matrix (pending EXE/dev verification):
    - [ ] Auto-create with no prior selection → new dossier.
    - [ ] Explicit existing dossier + “Add as new segment” → new segment in that dossier.
    - [ ] Switch back to auto-create → *another* new dossier, not a segment of the last one.

- **Status notes (2025‑12‑06 EXE test round)**
  - [x] In the current EXE, when the Control Panel is set to **Auto-create**, new runs create new dossiers as expected.
  - [x] When the Control Panel targets a specific dossier, runs attach as new segments to that dossier; Dossier Manager highlight no longer drives association implicitly.
  - [ ] UX follow-up: after an auto-create run, the Control Panel currently auto-switches to the newly created dossier; desired behavior is for the picker to **stay on the user’s last explicit choice** instead of changing itself.

### 3. Redundancy draft selector – persistence after refresh

- **Symptoms**
  - [x] Immediately after a redundancy run (e.g. count 3 + auto LLM consensus), the draft selector bubble appears and allows switching between Draft 1/2/3 and “Consensus”.
  - [ ] After refreshing the Dossier Manager or reopening the app and reloading the same run, the draft selector either disappears or loses the ability to switch drafts.

- **Likely root cause**
  - `redundancy_analysis` is present in the **immediate POST response** metadata, but is not persisted into the stored JSON (draft / run metadata) that the viewer loads later.

- **Planned work**
  - [x] Extend draft saving logic in the generic image-to-text processing endpoint to persist `metadata.redundancy_analysis` into the main transcription JSON on disk.
  - [ ] Confirm `ResultsViewer` continues to read redundancy metadata from `selectedResult.result.metadata` when loading from persisted JSON (pending end-to-end test).
  - [ ] Verify that:
    - [ ] Draft selector appears and works immediately after a run.
    - [ ] Draft selector still appears and works after refresh/reopen (EXE and dev).

- **Status notes (2025‑12‑06 EXE test round)**
  - [x] EXE run with redundancy `count = 3` + LLM consensus shows `metadata.redundancy_analysis` present in the saved JSON on disk, and this data is still present after app relaunch.
  - [ ] Viewer-level draft selector behavior after restart is still only partially verified; additional focused testing is needed to confirm that the selector uses the persisted metadata correctly.
  - **Status notes (2025‑12‑07 decision)**
    - [x] Floating `DraftSelector` in `ResultsViewer` has been **temporarily disabled**; Dossier Manager is now the canonical way to navigate between drafts for a run.
    - [ ] Future work (if re-enabled): rewire DraftSelector to use the same dossier-backed draft source (via resolver/text API) instead of relying solely on `redundancy_analysis`.

### 4. Text → Schema pipeline – schema file + OpenAI structured output

- **Symptoms**
  - [x] Both direct text input and “from finalized dossier” entry points into Text→Schema fail quickly with:
    - `Schema file does not exist: C:\Users\...\Temp\_MEIxxxxx\schema\plss_m_and_b.json`
    - `Parcel schema file not found at ...\plss_m_and_b.json`
    - OpenAI 400 errors:  
      `Invalid schema for response_format 'plattera_parcel': 'additionalProperties' is required to be supplied and to be false.`

- **Root causes**
  - [x] In the frozen EXE, the runtime loader looks for the schema at `_MEI...\schema\plss_m_and_b.json` while PyInstaller currently bundles it at `_MEI...\backend\schema\plss_m_and_b.json` via `--add-data "schema\plss_m_and_b.json;backend/schema"`, so `_load_parcel_schema()` returns `{}`.
  - [x] When the schema is missing/empty, we still send a strict `response_format` to OpenAI with `schema: {}`, which triggers 400 errors like: `"additionalProperties' is required to be supplied and to be false"`.

- **Planned work**
  - [ ] Fix runtime path resolution in frozen mode so `backend_root() / "schema" / "plss_m_and_b.json"` resolves to the **bundled** `_MEI...\backend\schema\plss_m_and_b.json` location (or adjust the PyInstaller target accordingly).
  - [ ] Once the file can be loaded, re-validate the parcel JSON schema against OpenAI’s current JSON-schema requirements for `response_format` under `strict: true` (ensuring top-level `type: "object"` and `additionalProperties: false` where required).
  - [ ] Add defensive logging so if the schema file is missing or OpenAI rejects the schema, the API returns a clear, frontend-friendly error.
  - [ ] Re-test Text→Schema:
    - [ ] Direct text input path.
    - [ ] Finalized dossier path.

- **Status notes (code implemented, awaiting EXE/dev verification)**
  - [x] Centralize schema path resolution via `backend_root()` for both `TextToSchemaPipeline` and OpenAI service, so the same `backend/schema/plss_m_and_b.json` path works in dev and frozen bundles (with PyInstaller `--add-data "schema\\plss_m_and_b.json;backend/schema"`).
  - [x] Ensure strict JSON schema is sent to OpenAI:
    - For fallback JSON-schema path, `call_structured` now wraps the schema in the `{ type: 'json_schema', json_schema: { name, schema, strict: true } }` structure.
    - `TextToSchemaPipeline` passes a strictified schema into `call_structured_pydantic` using `_convert_to_strict_schema`.
  - [ ] Logging / error surfacing still needs to be validated against a new EXE build and real OpenAI responses.

- **Status notes (2025‑12‑06 EXE test round)**
  - **Status notes (2025‑12‑07 EXE test round)**
    - [x] Re-ran Text→Schema in the EXE and confirmed logs show `_MEI...\schema\plss_m_and_b.json` as the lookup path, while the bundled file lives under `_MEI...\backend\schema\plss_m_and_b.json`, causing `_load_parcel_schema()` to return `{}`.
    - [x] Confirmed that the resulting empty strict schema is what drives the OpenAI 400 `"Invalid schema for response_format 'plattera_parcel': 'additionalProperties' is required to be supplied and to be false."`

### 5. Sidecar runtime stability – intermittent crashes

- **Symptoms**
  - [x] At least one prior EXE test round showed port 8000 not listening while the app window was still open, with features like Text→Schema doing nothing.
  - [ ] No definitive traceback captured yet for that event.

- **Planned work**
  - [x] Route sidecar and Python-backend stdout/stderr through `tauri_plugin_log` with explicit log targets and levels, so EXE logs capture child process output.
  - [ ] Add clearer startup / crash logging in `backend/main.py` and, if needed, additional Rust hooks to capture process exit codes and unhandled exceptions (pending further crashes).
  - [ ] Once a crash is captured, fix the underlying cause (e.g., resource exhaustion, missing config, etc.).

- **Status notes (2025‑12‑06 EXE test round)**
  - [x] Current EXE shows `[SIDECAR stdout]` and `[SIDECAR stderr]` entries in the Tauri log, including backend startup and third‑party warnings, confirming logging plumbing is working.
  - [ ] In this round the sidecar stayed healthy during normal use; no new intermittent crash was reproduced, so we still lack a concrete traceback to diagnose the original instability.

---

## 🔍 Uninstall / purge behavior (to verify)

- **Intended behavior**
  - On uninstall, when the user selects the “remove app data” checkbox, **all app data under `%LOCALAPPDATA%\Plattera\` should be removed**, including:
    - `Data\dossiers_data\...`
    - Any other app-specific caches or temp artifacts we create there.

- **Current behavior (observed)**
  - [x] With multiple dossiers/runs present under `%LOCALAPPDATA%\Plattera\Data\...`, running the uninstaller **with “delete data” checked** leaves:
    - `%LOCALAPPDATA%\Plattera\Data\dossiers_data\associations\*.json` and other dossier data intact.
  - [x] This means the uninstaller is currently **not honoring the user’s “delete app data” choice**.

- **Planned work**
  - [x] Add an in-app “Factory reset (delete all local data)” Tauri command (`factory_reset_data`) that recursively deletes `%LOCALAPPDATA%\Plattera\` for the current user and restarts the app.
  - [ ] Decide whether we also want NSIS uninstall to call the same logic or directly remove `%LOCALAPPDATA%\Plattera\` when “delete data” is checked.
  - [ ] Re-test:
    - [ ] Install EXE, create test dossiers/runs, verify files under `%LOCALAPPDATA%\Plattera\Data\...`.
    - [ ] Trigger Factory Reset from the UI (once wired) and confirm `%LOCALAPPDATA%\Plattera\` is removed or empty.


