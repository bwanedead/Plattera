# agents.md

## Scope
- Folder: `backend/feature_graph/`
- Purpose: Universal intermediate representation for deed meaning substrate
  - Core IR models, compilation, validation, persistence, and API endpoints

## Contracts & invariants
- **Total representability:** any deed assertion MUST be encodable in IR, even if not compilable
- **No confidence scores:** record facts, provenance, and deterministic outcomes only
- **Explicit gaps:** compilation failures produce typed gaps, never silent failure
- **Provenance-aware:** all nodes/edges can cite source evidence (via provenance module)
- **JSON serialization:** all models must support stable round-trip serialization

## Allowed changes
- Extending FeatureKind enum with new feature types
- Adding new operation types to OpExpr (via op_name + params)
- Adding new edge types (via edge_type field)
- Extending metadata fields on nodes/edges/graphs
- Adding new query helpers to FeatureGraph

## Not allowed
- DO NOT add confidence scores or probability fields to any model
- DO NOT silently fail compilation (must produce typed gaps)
- DO NOT break JSON round-trip invariant
- DO NOT hard-code PLSS logic in IR models (PLSS is a frame plugin)

## Commands
- Test: `pytest backend/feature_graph/test_*.py -v`
- Quick validation: `python backend/feature_graph/_test_import.py`
- From repo root (with venv): `pytest backend/feature_graph -q`

## Gotchas
- All models use `frozen=False` to allow mutability during compilation
- OpExpr operands can be node IDs (str) or nested OpExpr for complex operations
- FeatureNode content types are mutually exclusive: geometry XOR op_expr XOR feature_ref
- Graph edges can form cycles (needed for constraint systems)
- Empty graphs are valid and must serialize correctly

## Patterns
- Naming: test files use `test_*.py`, co-located with modules they validate
- Models: follow existing Pydantic patterns (BaseModel, Field, Config)
- Extensibility: use enum values, edge_type strings, and metadata dicts for future expansion

## Links
- Docs: `ralph/runs/2026-02-04__feature-graph-ir/PRD.md`
- Related: `backend/agents/common/contracts.py` (Gap/CompileReport for S3)
- Repo ethos: `docs/ethos/architecture-ethos.md`, `docs/ethos/structure-ethos.md`, `docs/ethos/testing-ethos.md`
