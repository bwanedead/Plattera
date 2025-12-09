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

- **Update (2025‑12‑09)**  
  Resolved via UTF‑8 BOM removal and updated in-app updater dialog; kept here for historical context.

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

- **Update (2025‑12‑09)**  
  Core schema loading and OpenAI structured output are now working in EXE; remaining Text→Schema issues (bearing normalization, Schema Manager wiring, direct-text persistence) are tracked in sections 6–10 below.

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
  - [ ] Logging / error surfacing still needs to be validated against a new EXE build and real OpenAI responses for non‑happy paths.

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

### 6. Text → Schema & Schema Manager – persistence, versions, and direct-text runs

- **Symptoms (2025‑12‑09 EXE test round)**
  - [ ] After app relaunch, selecting a saved schema in Schema Manager often shows JSON / Field view, but the **“Original Text” tab is empty**, making it hard to see what text the schema came from.
  - [ ] Editing a schema to produce a `_v2` variant (e.g., fixing `bearing_raw`) does not reliably drive the **“Draw Schema”** and mapping actions; logs show the backend still receiving the original v1 bearing string in some cases.
  - [ ] Version pills (`v1` / `v2`) in Schema Manager do not clearly indicate which version is currently active, and clicking them does not update any visible header in the Text→Schema results panel.
  - [ ] Schemas produced from **Direct Text Input** runs are not appearing in Schema Manager at all, even after refresh, suggesting they are not being persisted as first-class schema artifacts (or are missing `dossier_id` / index entries).

- **Likely root causes**
  - Original text is either not persisted with the schema artifact, or not re‑hydrated into `finalText` / original-text state when loading from Schema Manager.
  - “Draw Schema” and mapping currently operate on the in‑memory `schemaResults` from the last Text→Schema run, not necessarily the edited artifact / selected version from Schema Manager.
  - Direct text runs follow a lighter‑weight path that never saves a schema artifact to disk (or saves it outside the scope of `schemaApi.listAllSchemas()`).

- **Planned work**
  - [ ] Ensure every saved schema artifact includes:
    - [ ] The original legal text.
    - [ ] A stable `schema_id` root and explicit `version_label` (`v1`, `v2`, etc.).
  - [ ] When a schema is selected in Schema Manager:
    - [ ] Hydrate `finalText` / Original Text tab in the Text→Schema workspace from the artifact.
    - [ ] Set a visible version label in the results header (e.g., “Schema v2”) that stays in sync with the selected pill.
  - [ ] Wire the **Draw Schema** / “Map” actions to always use the currently selected schema artifact (including edits and version choice), not stale in‑memory copies.
  - [ ] Persist schemas generated from **Direct Text Input** into the same artifact store with:
    - [ ] A synthetic or “scratch” dossier id when no dossier is associated.
    - [ ] Inclusion in `schemaApi.listAllSchemas()` so they appear in Schema Manager with a clear source label.

- **Status notes (2025‑12‑09 code pass)**
  - [x] When a schema is selected in `SchemaManager`, `TextToSchemaWorkspace` now hydrates `finalDraftText` from the loaded artifact so the **Original Text** tab is populated after relaunch.
  - [ ] Direct-text schemas are still not persisted or listed in Schema Manager; selection and Draw Schema wiring still need end-to-end alignment with the artifact model.

### 7. Polygon drawing – bearing format robustness (Unicode minutes, spacing)

- **Symptoms**
  - [x] Initial EXE runs failed Text→Schema → polygon with:
    - `Failed to parse bearing: Could not parse bearing format: 'N. 4°00′W.' (original: 'N. 4° 00′ W.')`
    - Subsequent attempts showed `N. N. 4°00'W.` when manual edits duplicated the `N.` prefix.
  - [x] Even after origin parsing was fixed, polygon generation sometimes reported:
    - `Polygon generation failed - Insufficient valid courses for polygon: 0 courses processed`
    - Indicating that **all leg bearings** were rejected and no courses were drawn.
  - [ ] These failures only appear with more “typographic” output from Text→Schema (Unicode prime `′` and variable spacing), so dev runs against older JSON often worked.

- **Root cause**
  - `BearingParser._normalize_bearing` currently:
    - Assumes ASCII `'` for minutes.
    - Normalizes spacing and periods into patterns like `"N. 4°00'W."`.
  - The regex patterns only accept:
    - `([NS])\.\s*(\d+)°(\d+)'([EW])\.` and simpler variants, so any occurrence of `′` (`\u2032`) or extra letters like `N. N.` causes parsing to fail.

- **Planned work**
  - [x] Harden `BearingParser` normalization to:
    - [x] Replace `\u2032` (`′`) and `\u2019` (`’`) with `'` before regex matching.
    - [x] Strip stray duplicated direction letters (`"N. N." → "N."`) and redundant periods at the start of the string.
    - [x] Be tolerant of optional spaces around degrees/minutes and direction letters.
  - [ ] Add targeted unit tests for representative deed strings:
    - [ ] `N. 4° 00′ W.`, `N. 68° 30′ E.`, `S. 87° 35′ W.`, `S. 4° 00′ E.` and their normalized forms.
  - [ ] Improve logging to clearly show both the original and fully normalized bearing string used for parsing.

- **Status notes (2025‑12‑09 code pass)**
  - [x] Implemented Unicode prime normalization and leading `N. N.`/`S. S.` stutter cleanup in `_normalize_bearing`, plus stricter but more tolerant spacing rules; polygon generation for the test deed now succeeds once the correct schema version is applied.

### 8. Workspace layout instability – Allotment panes (Text→Schema & Image→Text)

- **Symptoms**
  - [ ] Occasionally, after switching rapidly between Image→Text, Map, and Text→Schema, the Text→Schema workspace “explodes” visually:
    - Controls and panels appear scattered or mis-sized.
    - The Dossier Manager / history toggle arrow disappears.
  - [ ] Frontend logs show repeated warnings and errors:
    - `Expected 2 children based on defaultSizes but found 1`
    - `ResizeObserver loop completed with undelivered notifications.`

- **Likely root cause**
  - `react-allotment` expects the length of `defaultSizes` to match the number of `Allotment.Pane` children.
  - In some layouts:
    - `ResultsViewer` always passes `[300, 700]` even when the history pane is hidden (1 child).
    - `ImageProcessingWorkspace` changes between 2–4 panes (Control / Alignment / Table / Results) while only computing sizes for 2–3, causing Allotment’s internal layout state to become inconsistent.

- **Planned work**
  - [ ] Audit all `Allotment` usages in:
    - [x] `ImageProcessingWorkspace.tsx`
    - [ ] `ResultsViewer.tsx`
    - [ ] `TextToSchemaWorkspace.tsx`
  - [ ] Ensure `defaultSizes.length` always matches the number of rendered panes for each state:
    - [ ] 2 panes: `[control, results]`
    - [ ] 3 panes: `[control, middlePanel, results]`
    - [ ] 4 panes: `[control, alignment, table, results]`
  - [ ] Add minimal guards / memoization so rapidly toggling panels cannot leave Allotment in an inconsistent state.

- **Status notes (2025‑12‑09 code pass)**
  - [x] Updated `ImageProcessingWorkspace` to compute `defaultSizes` dynamically based on visible panes (control, alignment panel, alignment table, results), eliminating the “Expected 2/3 children based on defaultSizes but found 3/4” warnings there.
  - [ ] `ResultsViewer` and `TextToSchemaWorkspace` Allotment usage still need the same treatment before we consider this fully resolved.

### 9. PLSS data download modal – Cancel / dismiss behavior

- **Symptoms**
  - [ ] When attempting to georeference a parcel without Wyoming PLSS data installed, the app shows the PLSS download modal.
  - [ ] Clicking **Cancel** does not reliably dismiss the modal or keep it suppressed; users can feel “trapped” in the download prompt if they do not want to download ~250MB immediately.

- **Current behavior**
  - `MapBackground` computes `shouldShowModal = status === 'missing' && !modalDismissed`.
  - `PLSSDownloadModal` calls `onCancel`, which is wired to `dismissModal()` in the PLSS state hook, but subsequent status checks appear to re-surface the “missing” state without remembering the dismissal.

- **Planned work**
  - [x] Ensure `dismissModal()` sets and persists `modalDismissed` for the current session (and possibly per‑state), so Cancel truly backs the user out.
  - [ ] Confirm that:
    - [ ] After Cancel, the map shows a stable “PLSS data required” placeholder instead of the modal.
    - [ ] Re‑triggering a mapping action explicitly can re‑open the modal when the user is ready.

- **Status notes (2025‑12‑09 code pass)**
  - [x] `usePLSSData` no longer blindly resets `modalDismissed` during initialization; it only resets when the underlying PLSS state code changes, so Cancel now persists for the current state within a session.

### 10. In-app Logs viewer – default scroll position

- **Symptoms**
  - [ ] Opening the in-app Logs panel (Frontend / Backend tabs) positions the scroll at the **top** of the log, forcing manual scrolling to see the latest entries.

- **Planned work**
  - [x] In `LogsPanel.tsx`, keep a `ref` to the scroll container and:
    - [x] Automatically set `scrollTop = scrollHeight` after logs are loaded or refreshed for the active tab.
    - [x] Ensure this behavior applies when:
      - [x] Opening the panel.
      - [x] Switching between Frontend and Backend tabs.
      - [x] Hitting “Refresh” on either tab.

- **Status notes (2025‑12‑09 code pass)**
  - [x] Logs panel now auto-scrolls to the bottom whenever frontend/backend logs or the active tab change, so the most recent entries are visible by default.