# Plattera Architectural Ethos

This document outlines the core engineering principles and architectural philosophy governing the Plattera codebase. These rules are designed to ensure high structural soundness, scalability, and long-term maintainability as the project evolves from prototype to production desktop application.

---

## 1. High Structural Soundness & Sanity
We prioritize **robust, long-term engineering** over quick fixes. Every solution must address the **root cause**, not just patch the symptom.

*   **No Spaghetti Code:** Features are decomposed into logical, focused modules with clear boundaries.
*   **No "God Objects":** Avoid massive, catch-all files (like a 2000-line `utils.js` or `App.tsx`) that accumulate unrelated responsibilities.
*   **Traceability:** Data flows must be explicit and traceable.
    *   *Example:* If a schema is saved, we must know exactly **where** (Artifact Store), **how** (Persistence Service), and **why** (Dossier Context).

## 2. Separation of Concerns
We enforce strict boundaries between application layers to prevent tight coupling and ensure testability.

*   **UI (Frontend):** Responsible solely for presentation and capturing user intent (e.g., `TextToSchemaWorkspace.tsx`, `SchemaManager.tsx`).
*   **State/Logic (Hooks):** Manages ephemeral runtime state and coordinates between UI and services (e.g., `usePLSSData`, `useImageProcessing`).
*   **Business Logic (Backend Services):** The "heavy lifting" domain rules and processing live here (e.g., `schema_persistence_service.py`, `plss_data_manager.py`).
*   **Data (Artifacts):** The file system (or database) is the ultimate source of truth, not frontend memory.

## 3. Persistence as Truth
Ephemeral state is fragile. If data matters, it must be persisted to disk immediately.

*   **Artifact-Driven Workflow:** We do not rely on passing massive objects around in React state memory. We save them as **Artifacts**—JSON files with metadata, lineage, and versioning—and then reload them.
*   **Hydration:** UI components should "hydrate" from these persisted artifacts.
    *   *Example:* The "Original Text" tab in Text→Schema works because it reads from a saved Schema Artifact on disk, not because a string was passed through five layers of props.

## 4. "Elite" Diagnosis & Root Cause Analysis
We do not guess. We investigate until we identify the "smoking gun."

*   **Evidence-Based:** We rely on logs, traces, and reproduction steps to prove *why* a failure occurs (e.g., verifying a port is closed via `Get-NetTCPConnection` before assuming a crash).
*   **Structural Solutions:** Fixes are applied at the architectural level to eliminate the entire class of error, rather than adding a localized `if/else` guard.
    *   *Example:* Instead of patching one specific malformed bearing string, we fix the `BearingParser` regex globally to handle Unicode and formatting edge cases.

## 5. Modular Scalability
We build today as if the app will grow 10x larger tomorrow.

*   **Composability:** Components (like `CleanMapBackground` or `PLSSDownloadModal`) are designed to be reused across different workspaces (`VisualizationWorkspace`, `TextToSchema`) without modification.
*   **Directory Hygiene:** New features deserve their own dedicated directories. We do not dump files into generic folders like `src/components` without organization.

---

### Summary
**"Structural correctness over speed. Persistence over memory. Modules over monoliths."**

