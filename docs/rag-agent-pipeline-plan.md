## RAG + Agent Pipeline for Text → Schema → Mapping

This document outlines a RAG- and agent-driven redesign of Plattera’s **text → schema → mapping** pipeline. The goal is to make schema extraction and georeferencing:

- **Universal**: handle complex, multi-deed, multi-station descriptions.
- **Dynamic & self-improving**: learn from curated past runs.
- **Safe & deterministic**: all numeric mapping remains driven by your existing PLSS + geodesic stack.
- **Modular**: new components live beside legacy code until we are confident enough to flip defaults.

This is a **plan**, not an implementation spec; it is designed to be iterated on as we fill in details and learn from early experiments.

---

### 1. Current Pipeline – Architecture Snapshot

#### 1.1 Text → Schema (legacy v0.2)

- **Pipeline**: `backend/pipelines/text_to_schema/pipeline.py`
  - `TextToSchemaPipeline.process(text, model, parcel_id)`
  - Uses `ServiceRegistry` (`backend/services/registry.py`) to select `OpenAIService`.
  - Loads `backend/schema/plss_m_and_b.json` via `_load_parcel_schema()`.
  - Builds a single ultra-strict prompt via `get_text_to_schema_prompt("parcel")` in `backend/prompts/text_to_schema.py` (`PARCEL_SCHEMA`).
  - Calls structured outputs (JSON schema / Pydantic) with a **strictified** copy of `plss_m_and_b.json`.
  - Post-processing:
    - `_validate_and_mark_completeness(structured_data)` – business rules for PLSS + POB + metes-and-bounds.
    - `_validate_parcel_data(structured_data)` – sanity check vs v0.2 expectations.
    - `_standardize_response(...)` – wraps `structured_data` + metadata.

- **Schema**: `backend/schema/plss_m_and_b.json` (version `"parcel_v0.2"`)
  - `parcel_id`, `descriptions[]`, `source`.
  - `descriptions[].plss`:
    - State / county / principal meridian.
    - TRS: `township_number`, `township_direction`, `range_number`, `range_direction`, `section_number`, `quarter_sections`.
    - `starting_point` with `pob_status` and optional `tie_to_corner` (with `reference_plss` for out-of-TRS ties).
  - `descriptions[].metes_and_bounds`:
    - `pob_vertex_index`, `legs_total`, `boundary_courses[]`, `closes_to_start`, `raw_text`.
    - `boundary_courses[]` holds `course` (text), `distance`, `distance_units`, `raw_text`, `description`; `bearing_degrees` is intentionally left `null` for LLM extraction (but not yet fully leveraged).

- **API**: `backend/api/endpoints/text_to_schema.py`
  - `/api/text-to-schema/convert` – direct JSON request (text, parcel_id, model, dossier_id).
  - Uses `TextToSchemaPipeline` to produce `TextToSchemaResponse`.
  - `/api/text-to-schema/save` – persists schemas using `SchemaPersistenceService`.
  - `/api/text-to-schema/schema` – exposes current template (plss_m_and_b.json).
  - `/api/text-to-schema/models` – lists allowed models (whitelist in the pipeline).

- **Persistence**: `backend/services/text_to_schema/schema_persistence_service.py`
  - `SchemaPersistenceService.save(...)` writes artifacts under:
    - `dossiers_schemas_artifacts_root() / {dossier_id} / {schema_id}.json`
    - Maintains `latest.json` pointer and `schemas_index.json` under `dossiers_state_root()`.
  - Artifacts include:
    - `structured_data`, `original_text`, `model_used`, `metadata.version_label` (v1/v2), and a `lineage` block.
  - Also dual-writes a “processing_jobs” layout for backward compatibility.

#### 1.2 PLSS + Georeference (deterministic core)

- **PLSS Pipeline**: `backend/pipelines/mapping/plss/pipeline.py` (class `PLSSPipeline`)
  - `resolve_starting_point(plss_description)`:
    - Validates PLSS description (`_validate_plss_description`).
    - Ensures PLSS data available via `PLSSDataManager.ensure_state_data`.
    - Uses `PLSSCoordinateService.resolve_coordinates` for centroid + bounds + corners.
    - Returns `anchor_point` (lat/lon + datum/accuracy) and metadata.
  - `get_section_view(plss_description)` – returns centroid + bounds via coordinate service.
  - `get_section_corner(plss_description, corner_label)` – currently returns section centroid (placeholder for real corners).

- **PLSS Services**:
  - `backend/pipelines/mapping/plss/coordinate_service.py` – fast TRS → coordinates using parquet index (and quarter-section offsets).
  - `backend/pipelines/mapping/plss/section_index.py`, `plss_joiner.py`, `nearest_snap_engine.py` – section/FGDB handling, fast search, corner resolution.

- **POB Resolver**: `backend/pipelines/mapping/georeference/pob_resolver.py` (class `POBResolver`)
  - Resolves `pob_geographic` from:
    - PLSS anchor only (section centroid).
    - PLSS anchor + tie to corner (bearing + distance from a named corner; primary path).
  - Uses:
    - `SectionIndex`, `PLSSJoiner`, `PLSSCoordinateService` for corners and geometry.
    - `CoordinateTransformer`, `UTMManager`, `GeodesicCalculator` for CRS transforms and geodesic math.
    - `SurveyingMathematics` (`survey_math.py`) for professional traverse calculations.
  - Includes boundary snapping and rich diagnostics to verify tie interpretation.

- **Traverse & Survey Math**: `backend/pipelines/mapping/georeference/survey_math.py`
  - `TraverseLeg`, `CoordinatePoint` dataclasses.
  - `SurveyingMathematics.calculate_traverse_coordinates(start_point, legs, tie_direction)` – geodesic traverse with closure and error propagation analysis.
  - Precision-focused helpers for bearings, distances, UTM approximation, and error metrics.

- **Georeference Service**: `backend/pipelines/mapping/georeference/georeference_service.py` (class `GeoreferenceService`)
  - `georeference_polygon(request)`:
    - Input: user-drawn `local_coordinates` + `plss_anchor` + optional `starting_point.tie_to_corner` + `options` (units, screen-coords).
    - Resolves POB via `POBResolver.resolve_pob(plss_anchor, tie_to_corner)`.
    - Normalizes, unit-converts, and (optionally) flips Y on local coordinates.
    - Converts local polygon into `TraverseLeg[]` via `_create_traverse_legs_from_local_coords` (feet/meters).
    - Runs `SurveyingMathematics.calculate_traverse_coordinates` from the POB to compute geodesic polygon vertices.
    - Builds GeoJSON polygon + bounds, attaches PLSS reference and POB metadata.
    - Calls `ProfessionalGeoreferenceValidator` to produce professional QA metrics.

- **Georeference Validation**: `backend/pipelines/mapping/georeference/validator.py`
  - `ProfessionalGeoreferenceValidator.validate_georeferenced_polygon(plss_desc, geographic_polygon, traverse_data)`:
    - PLSS boundary compliance via `PLSSPipeline.get_section_view` and geodesic distance checks.
    - Coordinate precision checks (≥6 decimal places).
    - Traverse closure and error metrics when traversal data supplied.

- **Mapping / Georef APIs**:
  - `backend/api/endpoints/georeference.py` – endpoints that call `GeoreferenceService.georeference_polygon` with either user-drawn coordinates or coordinates derived elsewhere.
  - `backend/api/endpoints/mapping.py` – endpoints that use `PLSSPipeline` for coordinate resolution and coverage queries.

**Key observation**: the deterministic PLSS + georeference stack is already robust and modular. The main redesign surface is **schema richness, extraction, and orchestration**, not numeric mapping.

---

### 2. Target Vision – RAG + Agent-Assisted Schema & Mapping

#### 2.1 High-Level Goals

- **Richer internal representation**:
  - Move beyond flat `metes_and_bounds.boundary_courses` into a **survey network** model:
    - `stations[]` (named points, including PLSS corners, stations, control points).
    - `segments[]` (straight-line legs between stations).
    - `curves[]` (arcs/spirals with radius, arc length, chord, direction).
    - `references[]` (cross-deed, cross-map references).
  - Keep v0.2 schema as a public/stable projection for UI and backward compatibility.

- **Deed + feature graph**:
  - Every deed becomes a node with:
    - Original text.
    - Versioned schema(s) (v0.2 + v0.3 internal model).
    - Georeference artifacts + validation metrics.
  - Stations, corners, curves become **features with IDs** that can be referenced across deeds.

- **RAG + agent orchestration**:
  - Use a retrieval layer (vector store + graph queries) to find:
    - Similar deed examples and schemas.
    - Referenced deeds in multi-deed chains.
    - Pre-mapped features for auto-anchoring.
  - Use an agent (LangChain / LangGraph / custom state machine) to:
    - Propose and iteratively refine schemas for new deeds.
    - Compose multi-deed dependencies.
    - Validate candidates via your existing PLSS + georef + validator stack.
    - Persist only validated results back into the KB.

- **Parallel rollout**:
  - Legacy v0.2 text→schema + manual/local drawing remain the default.
  - New RAG/agent path lives beside it, toggled per-request or per-dossier until proven.

#### 2.2 RAG & Agent Location

- **Backend-based LLM/agent**:
  - Use the existing `OpenAIService` + `ServiceRegistry` as the LLM abstraction.
  - Implement RAG retrieval and agent orchestration **in the backend**, behind REST endpoints.
  - The Tauri/desktop exe stays thin and only calls APIs like:
    - `/api/text-to-schema/convert?mode=legacy|rag_vnext`
    - `/api/mapping/schema-georef` (future) for schema-driven mapping.

- **Local models** (optional, later):
  - Reserve local models for optional UX helpers (e.g., quick hints or pre-parsing) rather than authoritative schema/mapping decisions.
  - Keep primary RAG + agent logic dependent on server-side models for quality.

---

### 3. Refactor Map – Where the New System Hooks In

This section lists concrete code points to **leave as-is**, **adapt**, or **wrap** as we introduce the new RAG/agent-driven stack.

#### 3.1 Text → Schema Layer

**Keep, but treat as legacy v0.2 path**

- `backend/pipelines/text_to_schema/pipeline.py` (`TextToSchemaPipeline`):
  - Continue to support existing `plss_m_and_b.json` and `PARCEL_SCHEMA` prompt for:
    - Simple deeds.
    - Backward-compatibility and regression comparisons.
  - Expose the current behavior under an explicit `mode="legacy"` flag (see below).

- `backend/schema/plss_m_and_b.json`:
  - Maintain as the **v0.2 storage schema** until after the new system proves out.
  - It may remain as your public/export schema even after v0.3 internal models exist.

- `backend/prompts/text_to_schema.py` (`PARCEL_SCHEMA`):
  - Keep as the **strict baseline prompt** for v0.2 extraction.

**Add / refactor (vNext path)**

- **New internal schema (v0.3)**:
  - Define Pydantic models in a new module, e.g.:
    - `backend/models/schema_v0_3.py` or `backend/pipelines/text_to_schema/models_v0_3.py`.
  - Core entities:
    - `Deed`: text, plss_context, list of `Description` objects.
    - `Description`: links to single parcel or multi-part description.
    - `Station`: id, labels, type, coordinates(optional), references (to deeds/maps/features).
    - `Segment`: from_station_id, to_station_id, course_text, distance_value/units, raw_text, description.
    - `Curve`: from_station_id, to_station_id, radius, arc_length, chord_length, direction, raw_text.
    - `Reference`: to deed (book/page or schema_id), to feature_id, notes.
  - These models live separately from v0.2 JSON schema to preserve clean modularity.

- **Schema Manager service** (new):
  - `backend/services/text_to_schema/schema_manager.py`:
    - Responsibilities:
      - Resolve schema version and engine:
        - `run_legacy(text, model)` → `TextToSchemaPipeline` (v0.2).
        - `run_rag_vnext(text, model)` → new RAG/agent pipeline (v0.3).
      - Convert between internal models and storage schemas:
        - v0.3 internal → v0.2 JSON projection (for UI/backward compatibility).
        - v0.2 JSON → v0.3 internal (best-effort migration for old schemas).
      - Coordinate with `SchemaPersistenceService` for artifact versioning and lineage.

- **RAG-enabled pipeline** (new):
  - `backend/pipelines/text_to_schema/rag_pipeline.py`:
    - `RagTextToSchemaPipeline.process(text, model, options)`:
      - Uses vector store + deed graph (see §3.4) to retrieve similar examples.
      - Builds prompts by composing:
        - Core instructions (for v0.3 models).
        - Example blocks from retrieved schemas.
      - Optionally runs a multi-step flow:
        1. Initial extraction (internal v0.3 model).
        2. Optional enrichment/repair pass guided by retrieved examples.
        3. Validation via mapping/PLSS tools (see below).
      - Returns both v0.3 internal model and v0.2 projection.

- **API routing flag**:
  - Extend `TextToSchemaRequest` (`backend/api/endpoints/text_to_schema.py`) with:
    - `mode: Optional[str] = "legacy"` (`"legacy" | "rag_vnext"`).
  - In `/api/text-to-schema/convert`:
    - `mode == "legacy"` → use `TextToSchemaPipeline` (unchanged behavior).
    - `mode == "rag_vnext"` → use `SchemaManager.run_rag_vnext`.
  - This gives a per-request “tire changing” switch without disturbing existing users.

#### 3.2 Mapping & Georeference Layer

**Keep mostly as-is**

- `PLSSPipeline` and all PLSS-related services (`coordinate_service`, `section_index`, `plss_joiner`, etc.).
- `POBResolver` and `SurveyingMathematics`.
- `GeoreferenceService.georeference_polygon` and `ProfessionalGeoreferenceValidator`.

These remain the **authoritative numeric and QA engines** used by both legacy and vNext flows.

**Add / extend**

- **Schema-driven georeference entrypoint**:
  - Either extend `GeoreferenceService` or introduce a narrow wrapper, e.g.:
    - `backend/pipelines/mapping/georeference/schema_georeference_service.py` with:
      - `georeference_from_schema(schema_v0_3, options)`:
        - Extract POB/PLSS anchor from internal model.
        - Build `TraverseLeg[]` directly from segments/curves:
          - Use existing bearing parsing and distance normalization helpers (`pob_math`, `SurveyingMathematics.convert_distance_units`).
        - Call `POBResolver` + `SurveyingMathematics.calculate_traverse_coordinates`.
        - Return polygon + traverse data for validation.
  - This path is **text-only mapping** (no user-drawn polygon), fully backed by the current math.

- **Station & curve support in traverse building**:
  - New helpers, likely in `schema_georeference_service.py` or a dedicated module:
    - `build_traverse_legs_from_network(schema_v0_3, plss_anchor)`:
      - Resolve station positions by walking segments/curves from known anchors (PLSS corners, prior stations, or feature_ids).
      - Handle curves by translating radius/arc into leg sequences that `SurveyingMathematics` can consume (straight-leg approximation or explicit curve support if added later).

- **New API endpoint for schema-based georef**:
  - `backend/api/endpoints/mapping.py` (or a new `schema_mapping.py`):
    - `/api/mapping/schema-georef`:
      - Input: `schema_id` or full v0.3 schema + options.
      - Uses the schema-driven georeference service.
      - Returns polygon, PLSS anchor info, validation metrics.

#### 3.3 Schema Persistence & Versioning

**Keep, but extend**

- `SchemaPersistenceService` already provides:
  - Atomic writes for schema artifacts.
  - `schemas_index.json` + `text_to_schema_index.json` for listing and legacy support.
  - Lineage (`root_schema_id`, `version_label`).

**Add / extend fields**

- In schema artifacts:
  - Ensure `original_text` and `version_label` are always present (per exe-issues section 6).
  - Add metadata hooks for vNext:
    - `metadata.engine = "legacy" | "rag_vnext"`.
    - `metadata.schema_version = "parcel_v0.2" | "parcel_v0.3"`.
    - `metadata.validation_summary` – essential metrics from `ProfessionalGeoreferenceValidator` for that schema’s georef run, if available.
  - Use `lineage.frozen_dependencies` to store:
    - Referenced deed schema IDs (for chains like Deed 1–4).
    - Referenced feature IDs (stations, corners, etc.).

This turns existing schema artifacts into nodes in a broader **deed graph** while preserving your current index layout.

#### 3.4 Deed & Feature Graph (New)

**New services / modules**

- **Deed graph service**:
  - `backend/services/rag/deed_graph_service.py`:
    - Read schema artifacts via `SchemaPersistenceService`.
    - Build a graph view:
      - Nodes: deeds (dossier_id + schema_id), plus optional `text_segment_id` for multi-description deeds.
      - Edges: references between deeds (book/page or explicit schema references), dependencies listed in `frozen_dependencies`.
    - Provide query methods for the agent:
      - `get_deed(schema_id)` → full artifact.
      - `get_dependencies(schema_id)` → upstream deed schemas / features.
      - `get_dependents(schema_id)` → downstream deeds that rely on this schema.

- **Feature persistence service**:
  - `backend/services/georeference/feature_persistence_service.py`:
    - Maintains a store of:
      - `feature_id` (UUID).
      - `type` (`"station"`, `"corner"`, `"control_point"`, etc.).
      - `labels` and aliases (as strings used in deeds).
      - Geometry (lat/lon, and optionally local coordinates / stationing).
      - References to `dossier_id`, `schema_id`, and description IDs.
    - Hooks:
      - Called once a georef run is accepted to register key stations and anchors as features.
      - Provides queries like `lookup_features_by_label(label_text, plss_context)` for RAG and agents.

- **Vector store / RAG service**:
  - `backend/services/rag/vector_store_service.py`:
    - Uses embeddings (OpenAI or other) through existing LLM service abstraction.
    - Stores vectors for:
      - Deed texts (whole or per-description segments).
      - Schema summaries (internal v0.3 structure plus key fields).
      - Feature labels + local context.
    - Query APIs for RAG:
      - `search_deeds(text, plss_context, k)` → top-k candidate deeds/schemas.
      - `search_features(reference_text, plss_context, k)` → candidate feature IDs with scores.

These services should be small, focused modules under a clear `services/rag` and `services/georeference` hierarchy to respect modular-architecture rules.

#### 3.5 Agent / Orchestration Layer

**Agent responsibilities**

- Given a new deed text (and optional PLSS/context):
  1. Discover references to existing deeds or maps (by citation, book/page, etc.).
  2. Use the deed graph + vector store to retrieve relevant schemas and examples.
  3. Propose an internal v0.3 schema (stations, segments, curves, references).
  4. Optionally refine using multiple passes and your georef + validation tools.
  5. Persist final schema and georef artifacts, updating the graph and RAG KB.
  6. Decide when to flag “needs human review” instead of force-fitting ambiguities.

**Where to implement**

- **Option A – LangChain / LangGraph (recommended for now)**:
  - Pros:
    - Off-the-shelf abstractions for tools, memory, and multi-step flows.
    - Good fit for resume/portfolio goals.
    - LangGraph allows more explicit state-machine style, which aligns with your “high structural soundness” ethos better than free-form ReAct loops.
  - Plan:
    - Implement a **lightweight graph**:
      - Nodes: extract, retrieve_examples, propose_schema, georeference, validate, repair, persist.
      - Tools: wrappers around your existing pipelines/services (TextToSchemaPipeline, PLSSPipeline, GeoreferenceService, vector store, deed graph).
    - Keep orchestration code in a dedicated module, e.g.:
      - `backend/pipelines/text_to_schema/agent_graph.py` (LangGraph) or `agent_chain.py` (LangChain).

- **Option B – Custom minimal state machine**:
  - Pros:
    - Maximal control and minimal dependencies.
    - Easier to reason about and debug, but less “standard” from a portfolio perspective.
  - Could be a future refactor if LangChain introduces friction or bloat.

Given your emphasis on modularity and clean architecture, **LangGraph on top of LangChain**, with each state mapped to a single-purpose function/module, is a solid compromise between structure and ecosystem leverage.

---

### 4. Phased Rollout Plan

#### Phase 1 – Parallel Text → Schema (No Mapping Changes)

**Goals**

- Introduce RAG-enhanced text→schema extraction (v0.3 internal) alongside legacy v0.2.
- Keep all georeference flows unchanged.

**Key tasks**

- Implement v0.3 internal models and `SchemaManager`:
  - Add Pydantic models for stations/segments/curves/references.
  - Implement basic v0.2 ⇄ v0.3 converters where possible.
- Implement `RagTextToSchemaPipeline`:
  - Embed + index a small curated set of hand-annotated deeds.
  - Implement retrieval (`search_deeds`) and prompt composition with examples.
  - Allow returning both v0.3 internal schema and a v0.2 projection.
- Extend `/api/text-to-schema/convert` with `mode` flag and hook into `SchemaManager`:
  - Ensure `mode="legacy"` preserves existing behavior bit-for-bit.
  - `mode="rag_vnext"` uses the new pipeline but writes artifacts via `SchemaPersistenceService` in the same layout.
- Update Schema Manager UI (frontend) to surface engine/schema version metadata (optional for this doc, but needed end-to-end).

**Validation strategy**

- For a subset of deeds, run **both** legacy and RAG pipelines:
  - Compare resulting v0.2 schemas (and v0.3 projections) field-by-field.
  - Record validation issues and ambiguous cases for schema + prompt adjustments.

#### Phase 2 – Schema-Driven Mapping (Parallel to User-Drawn Mapping)

**Goals**

- Enable **text-only** mapping from schemas (no manual polygon drawing).
- Keep user-drawn `GeoreferenceService.georeference_polygon` as the default mapping path.

**Key tasks**

- Implement schema-driven georeference service (`schema_georeference_service.py` or similar):
  - Build `TraverseLeg[]` from v0.3 internal schema (stations/segments/curves).
  - Resolve POB via `POBResolver` and run traverse via `SurveyingMathematics`.
  - Return polygon + traverse data in a similar shape to `georeference_polygon` output.
- Add `/api/mapping/schema-georef` endpoint:
  - Input: `schema_id` (or full schema) + options.
  - Output: polygon, PLSS reference, validation metrics.
- Integrate with `SchemaPersistenceService` and `ProfessionalGeoreferenceValidator`:
  - Persist georeference artifacts per schema/dossier (similar to existing georefs).
  - Attach validation summaries into schema metadata.

**Validation strategy**

- For simple deeds where user-drawn polygons already exist:
  - Compare schema-driven polygons vs user-drawn georefs:
    - Area/centroid differences.
    - Traverse closure metrics.
    - PLSS boundary compliance.
  - Use discrepancies to refine schema leg building and tie interpretation.

#### Phase 3 – Agentic Multi-Deed Reasoning & Feature Anchoring

**Goals**

- Allow the system to resolve complex deed chains and anchor to pre-mapped features autonomously.
- Use the PLSS + georef + validator stack as the objective scoring mechanism for agent decisions.

**Key tasks**

- Implement deed graph and feature persistence services (§3.4).
- Implement vector store/RAG service and wire into `RagTextToSchemaPipeline`.
- Build a LangGraph-based agent (`agent_graph.py`) that:
  - Detects references to other deeds in text (by citation patterns).
  - Uses deed graph + vector store to load and incorporate referenced schemas.
  - Calls schema-driven georeference + validator to score candidate schemas.
  - Iterates or flags “needs review” based on thresholds (e.g., closure, PLSS distance).
- Extend `SchemaPersistenceService` writes to include `frozen_dependencies` and/or feature references for agent use.

**Validation strategy**

- Start with a **curated test set** of multi-deed dependency scenarios:
  - Manually build “gold” internal schemas and polygons.
  - Measure how often the agent reproduces or closely approximates these results.
  - Tighten thresholds and add targeted examples until performance stabilizes.

---

### 5. Notes on Architecture & Libraries

- **Modularity expectations**
  - Each new concern (RAG retrieval, deed graph, features, agent orchestration) should live in its own focused module under `services/` or `pipelines/` (no dumping-ground files).
  - Schema models should be versioned and encapsulated (v0.2 JSON schema vs v0.3 internal Pydantic models) to avoid cross-contamination and ease future migrations.
  - Mapping/georef code should remain numerically focused and unaware of agent logic, consuming only well-defined schema and leg abstractions.

- **LangChain / LangGraph vs custom**
  - Starting with LangGraph on top of LangChain is a good compromise between structure, ecosystem, and portfolio value.
  - Each tool the agent calls should be a thin wrapper over an existing well-tested service or pipeline (e.g., `TextToSchemaPipeline`, `PLSSPipeline`, `GeoreferenceService`, vector store service).
  - If LangChain introduces too much complexity or overhead, the same state graph can be reimplemented as a custom orchestrator later without changing the underlying services.

This document is intended to evolve as we implement and learn from early iterations. As we build out each phase, we should keep it updated with concrete module names, interface signatures, and any deviations from the initial plan.


