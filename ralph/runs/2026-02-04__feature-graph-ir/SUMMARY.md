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
