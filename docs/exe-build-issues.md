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
  - [ ] Add Rust-side logging around updater HTTP call to:
    - Log HTTP status, headers, and raw body used by the plugin.
    - Log the full decode error from the plugin (or from our own `serde_json::from_str`) instead of just “error decoding response body”.
  - [ ] Once we see the real error, either:
    - [ ] Adjust `latest.json` schema to match plugin expectations, or
    - [ ] Wrap the plugin with a small custom deserializer that matches Tauri’s latest manifest format.
  - [ ] Re-test `check()` in dev and EXE until it cleanly reports “up to date” or a valid `update.available === true`.

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
  - [ ] Refactor `useImageProcessing` so that when `selectedDossierId` is provided from `ImageProcessingWorkspace`, it is treated as **source of truth**, and “Auto-create” (`null`) means `dossierIdToSend === undefined`.
  - [ ] Ensure Dossier Manager highlighting does not implicitly change the dossier used for processing; it should only respond to the control panel selection.
  - [ ] When `initRun` auto-creates a dossier, propagate that id back into the workspace so the picker shows the newly created dossier explicitly for subsequent runs.
  - [ ] Regression matrix:
    - [ ] Auto-create with no prior selection → new dossier.
    - [ ] Explicit existing dossier + “Add as new segment” → new segment in that dossier.
    - [ ] Switch back to auto-create → *another* new dossier, not a segment of the last one.

### 3. Redundancy draft selector – persistence after refresh

- **Symptoms**
  - [x] Immediately after a redundancy run (e.g. count 3 + auto LLM consensus), the draft selector bubble appears and allows switching between Draft 1/2/3 and “Consensus”.
  - [ ] After refreshing the Dossier Manager or reopening the app and reloading the same run, the draft selector either disappears or loses the ability to switch drafts.

- **Likely root cause**
  - `redundancy_analysis` is present in the **immediate POST response** metadata, but is not persisted into the stored JSON (draft / run metadata) that the viewer loads later.

- **Planned work**
  - [ ] Extend draft saving logic to persist `metadata.redundancy_analysis` alongside the main draft JSON and run metadata.
  - [ ] On load (`ResultsViewer`), rehydrate `redundancyAnalysis` into `selectedResult.result.metadata` from the persisted JSON.
  - [ ] Verify that:
    - [ ] Draft selector appears and works immediately after a run.
    - [ ] Draft selector still appears and works after refresh/reopen.

### 4. Text → Schema pipeline – schema file + OpenAI structured output

- **Symptoms**
  - [x] Both direct text input and “from finalized dossier” entry points into Text→Schema fail quickly with:
    - `Schema file does not exist: C:\Users\...\Temp\_MEIxxxxx\schema\plss_m_and_b.json`
    - `Parcel schema file not found at ...\plss_m_and_b.json`
    - OpenAI 400 errors:  
      `Invalid schema for response_format 'plattera_parcel': 'additionalProperties' is required to be supplied and to be false.`

- **Root causes**
  - [ ] PyInstaller EXE is not bundling `schema\plss_m_and_b.json` into the `_MEI...\schema\` folder where the pipeline expects it.
  - [ ] The parcel JSON schema we send as `response_format` to OpenAI no longer satisfies the newer structured-output validator (missing `"additionalProperties": false` and possibly other constraints).

- **Planned work**
  - [ ] Fix PyInstaller command and/or runtime path resolution so `plss_m_and_b.json` is present at `.../_MEIxxxx/schema/plss_m_and_b.json` in EXE builds.
  - [ ] Update the parcel JSON schema in the backend to:
    - Explicitly include `"additionalProperties": false` at the required levels.
    - Conform to OpenAI’s current JSON schema requirements for `response_format`.
  - [ ] Add defensive logging so if the schema file is missing or OpenAI rejects the schema, the API returns a clear, frontend-friendly error.
  - [ ] Re-test Text→Schema:
    - [ ] Direct text input path.
    - [ ] Finalized dossier path.

### 5. Sidecar runtime stability – intermittent crashes

- **Symptoms**
  - [x] At least one prior EXE test round showed port 8000 not listening while the app window was still open, with features like Text→Schema doing nothing.
  - [ ] No definitive traceback captured yet for that event.

- **Planned work**
  - [ ] Add clearer startup / crash logging in `backend/main.py` and in the Tauri sidecar launcher (Rust) to record:
    - Process exit codes.
    - Any unhandled exceptions leading to shutdown.
  - [ ] Once a crash is captured, fix the underlying cause (e.g., resource exhaustion, missing config, etc.).

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
  - [ ] Update the NSIS/Tauri uninstall configuration so that, when “delete app data” is selected, it recursively deletes `%LOCALAPPDATA%\Plattera\` for the current user.
  - [ ] Consider adding an in-app “Factory reset (delete all local data)” action that performs the same purge without uninstalling.
  - [ ] Re-test:
    - [ ] Install EXE, create test dossiers/runs, verify files under `%LOCALAPPDATA%\Plattera\Data\...`.
    - [ ] Uninstall with “delete data” checked and confirm `%LOCALAPPDATA%\Plattera\` is removed or empty.


