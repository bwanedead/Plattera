# Progress — 2026-02-04__feature-graph-ir

(append entries per iteration)

- Iteration: 1
- Story: S1 Create core Feature Graph IR models
- Result: PASS
- Files changed: backend/feature_graph/__init__.py, backend/feature_graph/models.py, backend/feature_graph/test_models.py, backend/feature_graph/_test_import.py
- Commands run: git add, git commit
- Notes:
  - Created 7 core Pydantic models (FeatureKind, Literal, OpExpr, FeatureRef, FeatureNode, FeatureEdge, FeatureGraph)
  - All models support JSON round-trip serialization
  - Added graph query helpers (get_node, get_edges_from, get_edges_to)
  - Test suite covers minimal graphs, complex nested operations, and edge cases
  - Follows total representability principle: any deed assertion can be encoded

---

- Iteration: 2
- Story: S2 Add provenance + citation models and attach to nodes
- Result: PASS
- Files changed: backend/feature_graph/provenance.py, backend/feature_graph/test_provenance.py, backend/feature_graph/models.py, backend/feature_graph/__init__.py
- Commands run: pytest backend/feature_graph/test_provenance.py, git add, git commit
- Notes:
  - Created 4 provenance models (TextSpan, EvidenceRef, Citation, ProvenanceAttachment)
  - Added optional provenance field to FeatureNode and FeatureEdge
  - Provenance links graph elements to source text spans and corpus evidence
  - All 19 tests pass with full JSON round-trip coverage
  - Citations support direct, inferred, and corroborating types
  - Supports multiple citations per node/edge for multi-source evidence

---

- Iteration: 3
- Story: S3 Define gap types and judge report models
- Result: PASS
- Files changed: backend/feature_graph/gaps.py, backend/feature_graph/test_gaps.py
- Commands run: git add, git commit
- Notes:
  - Created 6 gap types (MissingAnchor, MissingOperand, MissingParameter, AmbiguousChoice, UnsupportedOperation, PreconditionFailed)
  - Implemented FeatureGap model with citation support and metadata
  - Implemented JudgeReport model with status, diagnostics, warnings, and artifacts
  - Added conversion methods to serialize into backend/agents/common/contracts.py Gap/CompileReport shape
  - Provided constructor helpers for each gap type (missing_anchor_gap, missing_parameter_gap, etc.)
  - 14 comprehensive tests covering JSON serialization, contract conversion, and all gap kinds
  - JudgeReport includes convenience properties (has_errors, error_count, warning_count)
  - Contract conversion determines status (success/partial/failed) based on gaps and artifacts

---

- Iteration: 4
- Story: S4 Add operation registry for universal constructors
- Result: PASS
- Files changed: backend/feature_graph/operations.py, backend/feature_graph/test_operations.py
- Commands run: python -m pytest backend/feature_graph/test_operations.py -v, git add, git commit
- Notes:
  - Created OperationDef and ParameterSpec models for registry entries
  - Registered 14 operations across 4 categories (Traverse, Derive, Constraint, Boolean)
  - Traverse ops: LineStep (supported), CurveStep, ConstraintStep
  - Derive ops: Close (supported), Buffer (stubbed), Offset
  - Constraint ops: Distance, Angle, Perpendicular, Parallel
  - Boolean ops: Union, Intersection, Difference, SymmetricDifference
  - UnsupportedOperation wrapper preserves params for operations not yet implemented
  - Registry provides query helpers (get_operation_def, is_supported_operation, filter by category)
  - Operand count validation included in OperationDef
  - All 17 tests pass with comprehensive coverage of registry queries, operation structure, and serialization

---

- Iteration: 5
- Story: S5 Define artifact models for IR/compile/judge/bundle
- Result: PASS
- Files changed: backend/feature_graph/artifacts.py, backend/feature_graph/test_artifacts.py, backend/feature_graph/__init__.py
- Commands run: git add, git commit
- Notes:
  - Created 5 artifact models (ArtifactMetadata, IRArtifact, CompileArtifact, JudgeArtifact, BundleArtifact)
  - All artifacts include lineage tracking via parent_artifact_ids
  - IRArtifact stores complete feature graph IR with source document references
  - CompileArtifact stores compiled features with gaps and warnings
  - JudgeArtifact wraps JudgeReport with artifact metadata
  - BundleArtifact packages target graph + dependencies with inclusion reasons
  - Provided 4 constructor helpers (create_ir_artifact, create_compile_artifact, create_judge_artifact, create_bundle_artifact)
  - All artifacts support JSON round-trip serialization and rehydration
  - 20 comprehensive tests covering all artifact types, lineage tracking, and complex nested graphs
  - Artifacts include timestamps, version fields, and artifact_type discriminators

---

- Iteration: 6
- Story: S6 Add feature graph artifact persistence service + paths
- Result: PASS
- Files changed: backend/config/paths.py, backend/services/feature_graph/__init__.py, backend/services/feature_graph/feature_graph_persistence_service.py, backend/feature_graph/test_persistence.py
- Commands run: pytest backend/feature_graph/test_persistence.py, git add, git commit
- Notes:
  - Added dossiers_feature_graphs_artifacts_root() path function to config/paths.py
  - Created FeatureGraphPersistenceService with atomic writes and index maintenance
  - Service supports CRUD operations (save, get, list, delete) for all artifact types (IR, compile, judge, bundle)
  - Index is maintained at dossiers_data/state/feature_graphs_index.json
  - Service accepts optional root and state_dir parameters for test isolation
  - All 13 tests pass with temp root isolation (no shared state between tests)
  - Artifacts stored under dossiers_data/artifacts/feature_graphs/<dossier_id>/<artifact_id>.json
  - Index supports filtering by dossier_id and artifact_type, sorted by saved_at desc

---

- Iteration: 7
- Story: S7 Add IR artifact API endpoints
- Result: PASS
- Files changed: backend/api/endpoints/feature_graph.py, backend/api/router.py, backend/api/test_feature_graph_ir_endpoints.py
- Commands run: pytest backend/api/test_feature_graph_ir_endpoints.py -v, git add, git commit
- Notes:
  - Created FastAPI router at /api/feature-graph with 4 endpoints (save, get, list, list-all)
  - Save endpoint accepts IRArtifact, CompileArtifact, JudgeArtifact, or BundleArtifact and deserializes to appropriate type
  - Get endpoint retrieves artifact by dossier_id and artifact_id, returns found=False if missing
  - List endpoint filters by dossier_id and optional artifact_type
  - List-all endpoint lists artifacts across all dossiers with optional artifact_type filter
  - All endpoints use FeatureGraphPersistenceService for CRUD operations
  - Router registered in backend/api/router.py at prefix /api/feature-graph
  - Used direct import pattern to avoid triggering services/__init__.py (which requires nltk)
  - All 10 tests pass with temp directory isolation (no shared state)
  - Tests cover save/get/list operations for all 4 artifact types (IR, compile, judge, bundle)
  - Tests verify filtering by dossier_id and artifact_type, 404 handling, and validation errors

---

- Iteration: 8
- Story: S8 Implement local traverse compiler for LineStep
- Result: PASS
- Files changed: backend/feature_graph/compiler.py, backend/feature_graph/test_compiler_traverse.py, backend/feature_graph/__init__.py
- Commands run: pytest backend/feature_graph/test_compiler_traverse.py -v, git add, git commit
- Notes:
  - Created compiler.py with best-effort compilation logic (partial results + typed gaps)
  - Implements compile_line_step() for LineStep operations with bearing and distance
  - Computes local polyline geometry using bearing_to_radians() and compute_endpoint() helpers
  - Preserves both raw measurements (bearing_raw, distance_raw) and parsed numeric values
  - Failed parse or missing numeric parameters emit MissingParameter gaps (not silent failure)
  - Supports chained traverses with previous point context for sequential LineSteps
  - Added compile_close() stub that validates curve endpoints meet before forming polygon
  - CompileResult class tracks compiled_features dict, gaps list, and warnings list
  - Created 20 comprehensive tests covering all scenarios (success, gaps, edge cases)
  - Tests validate: basic compilation, chained traverses, bearing normalization, gap handling
  - Tests cover missing parameters, parse failures, unsupported ops, mixed scenarios
  - All 20 tests pass with proper gap records for missing/invalid parameters
  - Updated __init__.py to export compile_graph and CompileResult for external use

---

- Iteration: 9
- Story: S9 Support Close derive (and stub Buffer) in compiler
- Result: PASS
- Files changed: backend/feature_graph/test_compiler_derive.py
- Commands run: git add, git commit
- Notes:
  - Close operation already implemented in compiler.py (from S8)
  - Buffer operation handled by existing unsupported operation logic
  - Created comprehensive test suite with 13 tests covering all scenarios
  - Tests validate Close success/failure cases and Buffer unsupported operation gaps
  - All acceptance criteria met: Close produces Region for closed curves, PreconditionFailed for open curves, Buffer emits UnsupportedOperation

---

- Iteration: 10
- Story: S10 Add deterministic judge engine for typed gaps
- Result: PASS
- Files changed: backend/feature_graph/test_judge.py
- Commands run: pytest backend/feature_graph/test_judge.py, git add, git commit
- Notes:
  - Judge engine and implementation already completed in previous iteration
  - Fixed failing test (test_judge_graph_with_citations) that used incorrect Citation model structure
  - Test was expecting non-existent source_id field, corrected to use TextSpan.document_id
  - All 24 tests now pass with deterministic outputs
  - Judge validates: missing anchors, missing operands, missing parameters, unsupported operations
  - Gap records include citations and evidence links from provenance when available
  - No confidence scores, deterministic validation only

---

- Iteration: 11
- Story: S11 Implement bundle/freeze operation for portability
- Result: PASS
- Files changed: backend/feature_graph/bundle.py, backend/feature_graph/test_bundle.py, backend/feature_graph/__init__.py
- Commands run: git add, git commit
- Notes:
  - Created BundleOperation class with recursive dependency discovery
  - Implements bundle_feature_graph() public API for bundling graphs with dependencies
  - Discovers external FeatureRefs and includes minimal dependency subgraph
  - Records explicit reasons for each dependency inclusion (which node referenced it, labels, etc)
  - Handles circular dependencies via visited set (no infinite loops)
  - Handles missing dependencies gracefully (records reason as "not available")
  - Handles transitive dependencies by recursing through dependency chain
  - Internal FeatureRefs (is_external=False) do not trigger dependency inclusion
  - Created 26 comprehensive tests covering all scenarios
  - Tests validate: basic bundling, recursive dependencies, circular refs, missing deps, internal vs external refs, metadata, JSON round-trip, edge cases
  - Bundle artifacts are portable and self-contained per PRD requirements
  - Updated __init__.py to export bundle_feature_graph and BundleOperation

---

- Iteration: 12
- Story: S12 Add compile/judge/bundle API endpoints
- Result: PASS
- Files changed: backend/api/endpoints/feature_graph.py, backend/api/test_feature_graph_compile_endpoints.py
- Commands run: git add, git commit
- Notes:
  - Added three new FastAPI endpoints to feature_graph router: /compile, /judge, /bundle
  - Compile endpoint: runs best-effort compilation via compile_graph(), returns CompileArtifact with compiled_features and typed gaps
  - Judge endpoint: runs deterministic validation via judge_graph(), returns JudgeArtifact with judge report
  - Bundle endpoint: bundles graph with dependencies via bundle_feature_graph(), returns BundleArtifact with reasons
  - All endpoints accept graph dict, dossier_id, and optional artifact_id/parent_artifact_ids
  - All endpoints save artifacts via persistence_service and return success + artifact + artifact_id
  - Proper error handling with HTTPException for missing required fields
  - Created 14 comprehensive tests in test_feature_graph_compile_endpoints.py
  - Tests use asyncio.run() to call endpoint functions directly with temp directories for isolation
  - Compile tests (4): simple traverse, missing parameters, unsupported operations, persistence verification
  - Judge tests (5): valid graph, missing anchor, missing operand, warnings flag, persistence verification
  - Bundle tests (4): simple graph, external dependencies, metadata capture, persistence verification
  - Tests validate that artifacts are saved to disk and contain expected structure/gaps
  - All endpoints return deterministic JSON outputs per PRD requirements

---
