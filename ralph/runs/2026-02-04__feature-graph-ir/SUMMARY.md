# SUMMARY.md - Ralph Run: 2026-02-04__feature-graph-ir

This file captures a running summary of what was built, one entry per completed story. It provides a human-readable debrief for reviewers.

---

## Story S1: Create core Feature Graph IR models
**Status:** PASS
**Iteration:** 1

### What was built
- Seven core Pydantic models for universal feature graph intermediate representation
- `FeatureKind` enum with point, curve, region, frame, constraint, annotation, unknown types
- `Literal` model for typed values with raw string preservation (for provenance)
- `OpExpr` model for operation expressions (Traverse, Close, Buffer, Union, etc)
- `FeatureRef` model for internal and external feature references
- `FeatureNode` model supporting three content types: direct geometry, operation expression, or feature reference
- `FeatureEdge` model for directed relationships (dependencies, sequencing, anchoring)
- `FeatureGraph` model with nodes, edges, metadata, and query helper methods

### Files changed
- `backend/feature_graph/__init__.py` - module initialization with public exports
- `backend/feature_graph/models.py` - all core IR models (7 classes, ~160 lines)
- `backend/feature_graph/test_models.py` - comprehensive test suite (9 tests, ~280 lines)
- `backend/feature_graph/_test_import.py` - quick validation script (can be removed later)

### Key decisions
- Used Pydantic BaseModel for all models to ensure JSON serialization and validation
- Made FeatureNode support three mutually exclusive content types (geometry, op_expr, feature_ref) for flexibility
- Added query helper methods to FeatureGraph (get_node, get_edges_from, get_edges_to) for common traversal patterns
- Used frozen=False config to allow mutability (may be needed for compilation/mutation steps)
- Followed "total representability" principle: any deed assertion can be encoded, even if not compilable yet
- No confidence scores: following PRD constraint to record facts and deterministic outcomes only

### Tests added
- 9 new tests in `backend/feature_graph/test_models.py`
- Coverage includes:
  - JSON round-trip for all model types (Literal, OpExpr, FeatureRef, FeatureNode, FeatureEdge, FeatureGraph)
  - Minimal graph serialization (acceptance criterion)
  - Graph query methods (get_node, get_edges_from, get_edges_to)
  - Complex nested operation expressions
  - Empty graphs and edge cases

### Notes
- All models are designed to be extended without breaking existing code (enum values, edge types, node content)
- OpExpr supports nested operands for complex operations (e.g., Union(Close(T1), Buffer(Close(T2), 10ft)))
- Graph structure allows DAGs and cycles (for constraint systems)
- Provenance fields (citations, evidence) deferred to S2 (provenance module)
- Test suite validates weight-bearing invariants: stable serialization, deterministic IDs, safe empty cases

---

## Story S2: Add provenance + citation models and attach to nodes
**Status:** PASS
**Iteration:** 2

### What was built
- Four provenance models for complete traceability of feature graph elements
- `TextSpan` model for precise source document locations (character offsets or line/column positions)
- `EvidenceRef` model for structured links to corpus documents, chunks, and semantic segments
- `Citation` model linking graph elements to source text spans and evidence (supports direct, inferred, corroborating types)
- `ProvenanceAttachment` model for embedding citations, creator info, timestamps, and lineage
- Added optional `provenance` field to both FeatureNode and FeatureEdge models

### Files changed
- `backend/feature_graph/provenance.py` - new file with 4 provenance models (~80 lines)
- `backend/feature_graph/models.py` - added provenance field to FeatureNode and FeatureEdge
- `backend/feature_graph/__init__.py` - exported provenance models and fixed imports to use relative imports
- `backend/feature_graph/test_provenance.py` - comprehensive test suite with 19 tests (~400 lines)

### Key decisions
- Made provenance optional on nodes/edges (not all features need explicit citations)
- Used TYPE_CHECKING for forward references to avoid circular imports
- Changed all imports in __init__.py to relative imports for cleaner module structure
- TextSpan supports both character offsets and line/column positions for flexibility
- EvidenceRef supports multiple evidence types (textual, visual, derived) with relevance notes
- Citations can include multiple evidence references for multi-source corroboration
- ProvenanceAttachment includes lineage tracking for derived features

### Tests added
- 19 new tests in `backend/feature_graph/test_provenance.py`
- Coverage includes:
  - TextSpan JSON round-trip with offsets and line/column positions
  - EvidenceRef with corpus documents, chunks, and semantic segments
  - Citation with text spans and multiple evidence references
  - ProvenanceAttachment with lineage tracking
  - Nodes and edges with provenance attachments (full round-trip)
  - Complex scenarios: multiple citations, empty citations, nodes without provenance
- All tests pass with 100% coverage of acceptance criteria

### Notes
- Provenance models enable full traceability from IR back to source documents
- Citations link to both raw text (TextSpan) and structured corpus evidence (EvidenceRef)
- No confidence scores used (following PRD constraint: record facts only)
- Provenance attachment supports creation timestamps and creator tracking (for audit trails)
- Lineage field enables tracking derived features through compilation pipeline
- Fixed import structure across feature_graph module for consistency

---

## Story S3: Define gap types and judge report models
**Status:** PASS
**Iteration:** 3

### What was built
- Six typed gap kinds for all compilation failure modes (MissingAnchor, MissingOperand, MissingParameter, AmbiguousChoice, UnsupportedOperation, PreconditionFailed)
- `FeatureGap` model with gap kind, message, feature ID, severity, citations, and structured metadata
- `JudgeReport` model aggregating all gaps, warnings, artifacts, and metadata from compilation/validation
- Conversion methods to serialize into existing `backend/agents/common/contracts.py` Gap/CompileReport shape
- Six gap constructor helpers for common scenarios (missing_anchor_gap, missing_operand_gap, etc.)
- Comprehensive test suite validating JSON serialization, contract conversion, and all gap types

### Files changed
- `backend/feature_graph/gaps.py` - gap types and judge report models (~290 lines)
- `backend/feature_graph/test_gaps.py` - comprehensive test suite with 14 tests (~400 lines)

### Key decisions
- Used GapKind enum to ensure gap types are strongly typed and exhaustive
- Made FeatureGap carry citations (via provenance module) for full traceability
- Implemented `to_contract_gap()` and `to_contract_report()` methods to bridge feature graph gaps to existing agent contracts
- JudgeReport status determination: SUCCESS (no errors), PARTIAL (errors + artifacts), FAILED (errors, no artifacts)
- Gap metadata stores structured details (operation name, parameter name, choices, etc.) for programmatic handling
- Included convenience properties on JudgeReport (has_errors, error_count, warning_count) for quick inspection
- All gaps have severity field (error/warning/info) for flexible diagnostic filtering

### Tests added
- 14 new tests in `backend/feature_graph/test_gaps.py`
- Coverage includes:
  - Gap kinds coverage validation (all 6 required kinds present)
  - FeatureGap JSON round-trip serialization
  - FeatureGap with citations and provenance
  - FeatureGap to contract Gap conversion
  - JudgeReport JSON round-trip serialization
  - JudgeReport to contract CompileReport conversion (success/partial/failed status)
  - JudgeReport convenience properties (has_errors, error_count, warning_count)
  - All gap constructor helpers (missing_anchor_gap, missing_parameter_gap, etc.)
  - Complex judge report with multiple gap types
  - Empty judge report edge case

### Notes
- Gaps are deterministic: same inputs always produce same gap records (no non-determinism)
- Citations enable tracing gaps back to source text spans and evidence
- Gap metadata is structured (Dict[str, Any]) allowing rich diagnostic information
- Contract conversion allows feature graph compiler to interoperate with existing agent/judge infrastructure
- PreconditionFailed gap type covers unclosed curves, invalid prerequisites, and other precondition violations
- All acceptance criteria met: gap types complete, contract serialization working, tests pass

---

## Story S4: Add operation registry for universal constructors
**Status:** PASS
**Iteration:** 4

### What was built
- Universal operation registry defining all operations that can appear in feature graph IR
- `OperationCategory` enum for operation classification (Traverse, Derive, Constraint, Boolean, Unknown)
- `ParameterSpec` model defining operation parameter specifications (name, type, required/optional, unit, default value)
- `OperationDef` model defining complete operation specifications (name, category, parameters, operand counts, support status)
- 14 operation definitions across 4 categories registered in `OPERATION_REGISTRY`
- `UnsupportedOperation` wrapper for storing operations not yet implemented in compiler
- Registry query helpers for retrieving and filtering operations

### Files changed
- `backend/feature_graph/operations.py` - operation registry with models and definitions (~470 lines)
- `backend/feature_graph/test_operations.py` - comprehensive test suite with 17 tests (~320 lines)

### Key decisions
- Operations are registry entries, not hard-coded classes, allowing easy extension
- Each operation specifies required/optional parameters, operand count constraints, and support status
- UnsupportedOperation wrapper ensures total representability: any deed operation can be stored in IR even if not compilable
- Marked LineStep and Close as supported (implemented in future stories), all others as unsupported initially
- ParameterSpec includes unit hints (feet, degrees) for measurement parameters
- Operand count validation built into OperationDef (min_operands, max_operands with None = unlimited)
- Registry provides query functions: get by name, filter by category, list supported/unsupported operations

### Tests added
- 17 new tests in `backend/feature_graph/test_operations.py`
- Coverage includes:
  - Registry population validation (all expected operations present)
  - get_operation_def retrieval (known and unknown operations)
  - is_supported_operation filtering
  - get_operations_by_category filtering (all 4 categories)
  - get_supported_operations / get_unsupported_operations listing
  - Specific operation definitions (LineStep, Close, Buffer structure validation)
  - Operand count validation logic
  - UnsupportedOperation wrapper and to_op_expr conversion
  - ParameterSpec structure
  - Operation descriptions and categories validation
  - JSON serialization round-trip for OperationDef
  - Boolean operations unlimited operand support
  - Constraint operations correct operand counts

### Notes
- Operations organized into 4 categories:
  - Traverse: LineStep (supported), CurveStep, ConstraintStep
  - Derive: Close (supported), Buffer (stubbed), Offset
  - Constraint: Distance, Angle, Perpendicular, Parallel
  - Boolean: Union, Intersection, Difference, SymmetricDifference
- LineStep includes both numeric params (bearing, distance) and raw string params (bearing_raw, distance_raw) for provenance
- CurveStep includes comprehensive curve parameters (radius, arc_length, chord_bearing, chord_distance, delta_angle, direction)
- Registry is extensible: new operations can be added without breaking existing code
- UnsupportedOperation to_op_expr adds _unsupported and _reason flags to params for clear identification
- All acceptance criteria met: operation definitions complete, UnsupportedOperation wrapper works, tests pass

---

## Story S5: Define artifact models for IR/compile/judge/bundle
**Status:** PASS
**Iteration:** 5

### What was built
- Five artifact models for durable persistence of feature graph pipeline states
- `ArtifactMetadata` model with lineage tracking (parent_artifact_ids), timestamps, creator info, and version field
- `IRArtifact` model for persisting complete feature graph IR with source document references
- `CompileArtifact` model for storing compilation outputs (compiled features, gaps, warnings) with compiler version tracking
- `JudgeArtifact` model wrapping JudgeReport with artifact metadata for validation results
- `BundleArtifact` model for portable packaging of target graph + dependency subgraphs with inclusion reasons
- Four constructor helpers that set timestamps and metadata automatically
- Bundle helper methods (get_all_graph_ids, get_dependency_reason)

### Files changed
- `backend/feature_graph/artifacts.py` - new file with 5 artifact models and 4 constructor helpers (~280 lines)
- `backend/feature_graph/test_artifacts.py` - comprehensive test suite with 20 tests (~500 lines)
- `backend/feature_graph/__init__.py` - exported artifact models and helpers

### Key decisions
- Used ArtifactMetadata as common base for all artifacts (consistent lineage tracking pattern)
- All artifacts have artifact_type discriminator field for polymorphic deserialization
- Artifacts store timestamps in ISO format with UTC timezone ("2024-01-01T00:00:00Z")
- BundleArtifact stores dependency_reasons as Dict[graph_id -> reason] for explainability
- CompileArtifact stores gaps as plain dicts (not FeatureGap objects) for flexibility
- JudgeArtifact wraps JudgeReport rather than duplicating fields (composition over inheritance)
- Constructor helpers automatically set created_at timestamps using datetime.utcnow()
- All artifacts support version field for schema evolution (defaults to "1.0")

### Tests added
- 20 new tests in `backend/feature_graph/test_artifacts.py`
- Coverage includes:
  - ArtifactMetadata JSON round-trip
  - IRArtifact minimal and with source document tracking
  - CompileArtifact with gaps, warnings, and empty results
  - JudgeArtifact with JudgeReport integration
  - BundleArtifact minimal, with dependencies, and with included artifacts
  - Lineage tracking across all artifact types (IR → Compile → Judge → Bundle)
  - Timestamp validation for all constructors
  - Artifact type discriminator validation
  - Complex nested graph serialization
  - Version field validation

### Notes
- All artifacts are durable: full JSON round-trip with no loss of information
- Lineage tracking enables full audit trail from bundle back to source documents
- Bundles are self-contained and portable (include all dependencies)
- BundleArtifact dependency_reasons field enables explainability (why was each dependency included)
- Artifacts follow existing Pydantic patterns (BaseModel, Field, Config with frozen=False)
- All acceptance criteria met: artifact models complete with lineage, tests pass, round-trip coverage verified

---

## Story S6: Add feature graph artifact persistence service + paths
**Status:** PASS
**Iteration:** 6

### What was built
- Feature graph artifact paths added to centralized path configuration
- `FeatureGraphPersistenceService` for atomic writes and index maintenance
- CRUD operations (save, get, list, delete) for all artifact types (IR, compile, judge, bundle)
- Queryable index with filtering by dossier_id and artifact_type
- Test isolation support via optional root and state_dir parameters

### Files changed
- `backend/config/paths.py` - added `dossiers_feature_graphs_artifacts_root()` path helper
- `backend/services/feature_graph/__init__.py` - service module initialization
- `backend/services/feature_graph/feature_graph_persistence_service.py` - persistence service implementation (~250 lines)
- `backend/feature_graph/test_persistence.py` - comprehensive test suite with 13 tests (~400 lines)

### Key decisions
- Followed existing persistence patterns from `schema_persistence_service.py` (atomic writes with tempfile + os.replace)
- Separated feature graph artifacts from legacy schema/georef artifacts at `dossiers_data/artifacts/feature_graphs/`
- Index maintained at `dossiers_data/state/feature_graphs_index.json` for cross-dossier queries
- Service accepts optional root and state_dir overrides for test isolation (each test gets temp dirs)
- Index entries deduplicated by (dossier_id, artifact_id) and sorted by saved_at desc
- Direct import pattern in tests to avoid triggering services/__init__.py which imports heavy dependencies

### Tests added
- 13 new tests in `backend/feature_graph/test_persistence.py`
- Coverage includes:
  - Service initialization with temp roots
  - Save and retrieve for all 4 artifact types (IR, compile, judge, bundle)
  - Atomic write crash-safety validation
  - Index maintenance and query operations (list all, filter by dossier, filter by type)
  - Index deduplication (same artifact_id overwrites, no duplicates)
  - Delete operations with index cleanup
  - Nonexistent artifact handling (returns None)
  - Empty index handling (returns empty list)
  - Index sorting by saved_at (newest first)
  - Mixed artifact types filtering

### Notes
- All 13 tests pass with isolated temp directories (no shared state pollution)
- Persistence service matches schema_persistence_service patterns for consistency
- Artifacts separate from legacy pipelines (as required by PRD non-goal: "not replacing or refactoring existing pipelines")
- Index enables efficient queries across dossiers without scanning filesystem
- Service is production-ready: atomic writes ensure crash-safety, index maintains consistency

---

## Story S7: Add IR artifact API endpoints
**Status:** PASS
**Iteration:** 7

### What was built
- FastAPI router at `/api/feature-graph` with 4 CRUD endpoints for feature graph artifacts
- POST `/save` endpoint accepting IRArtifact, CompileArtifact, JudgeArtifact, or BundleArtifact with automatic type deserialization
- GET `/get/{dossier_id}/{artifact_id}` endpoint for retrieving artifacts by ID
- GET `/list/{dossier_id}` endpoint for listing artifacts within a dossier (with optional artifact_type filter)
- GET `/list-all` endpoint for listing artifacts across all dossiers (with optional artifact_type filter)
- Router registration in main API router with `/api/feature-graph` prefix
- Comprehensive test suite with direct async function calls (no TestClient dependency)

### Files changed
- `backend/api/endpoints/feature_graph.py` - new FastAPI router with 4 endpoints (~230 lines)
- `backend/api/router.py` - registered feature_graph router with `/api/feature-graph` prefix
- `backend/api/test_feature_graph_ir_endpoints.py` - comprehensive test suite with 10 tests (~360 lines)

### Key decisions
- Used direct import pattern (`sys.path.insert`) to avoid triggering `services/__init__.py` which requires nltk (follows existing test patterns)
- Endpoints accept artifact dicts and deserialize to appropriate Pydantic model based on artifact_type
- Router uses FeatureGraphPersistenceService for all CRUD operations (no direct file access)
- Tests call endpoint functions directly via asyncio.run (matches existing API test patterns)
- All endpoints return structured response models (SaveArtifactResponse, GetArtifactResponse, ListArtifactsResponse)
- Get endpoint returns `found: false` instead of 404 for missing artifacts (graceful degradation)
- List endpoints return count field for easy pagination/UI display
- Router prefix `/api/feature-graph` keeps endpoints separate from legacy pipelines (as required by PRD)

### Tests added
- 10 new tests in `backend/api/test_feature_graph_ir_endpoints.py`
- Coverage includes:
  - Save IR artifact via API
  - Get artifact via API (found and not found cases)
  - List artifacts by dossier (all types and filtered by type)
  - List all artifacts across dossiers (all types and filtered by type)
  - Save and retrieve compile artifact
  - Save and retrieve judge artifact
  - Save and retrieve bundle artifact
  - Error handling (missing dossier_id, unknown artifact_type)
- All tests use temp directories for isolation (no shared state)
- All 10 tests pass with 0 failures

### Notes
- All endpoints are HTTP POST/GET (no PUT/PATCH/DELETE yet, only basic CRUD)
- Endpoints run in parallel with legacy pipelines (no interference with existing text-to-schema or mapping pipelines)
- Persistence service is module-level singleton (instantiated once at router import time)
- Tests override persistence_service via monkeypatching for test isolation
- Router follows existing API patterns (same import structure, response models, error handling)
- Direct import pattern prevents nltk/biopython import issues during testing
- All acceptance criteria met: router created, CRUD endpoints working, tests pass

---

## Final Summary (append when run complete)

### Overview
<1-2 paragraph summary of what the entire run accomplished>

### Total changes
- Files created: <count>
- Files modified: <count>
- Tests added: <count>
- Lines of code: <implementation> + <tests> = <total>

### Architecture decisions
- <bullet: key technical choices made>
- <bullet: patterns established>

### Known limitations
- <bullet: deferred work>
- <bullet: technical constraints>

### Production readiness
<Brief assessment of whether this is ready for production use>
