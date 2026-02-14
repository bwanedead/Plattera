## Plattera Technical Rebase: Feature Graph IR + RAG System + Agent Loop Goals

### Purpose
This document is a **deep technical rebase** of what exists in the Plattera codebase today (RAG/retrieval + Feature Graph IR) and the **intended end-state**: an AI agent loop that converts deed text into a **verified mapped artifact** with explicit provenance, deterministic validation, and durable outputs.

This is written to be shareable with another LLM or engineer as a “truth map” of:
- **Architecture and terminology**
- **Module responsibilities and wiring**
- **API/CLI contract surfaces**
- **Deterministic verification and accuracy standards**
- **What the eventual agent loop must accomplish**

### Repo ethos alignment (non-negotiables)
These are the design constraints this system is built around:
- **Structural soundness over cleverness**: modular boundaries, no dumping grounds. See `docs/ethos/architecture-ethos.md`, `docs/ethos/structure-ethos.md`.
- **Persistence as truth**: important state is stored as artifacts; UI hydrates from disk, not memory.
- **Evidence-first retrieval**: “evidence is the common output” regardless of lane; embeddings are a finder, provenance is correctness. See `docs/Evidence_First_Hybrid_Retrieval_for_Plattera.md`.
- **Deterministic judges and explicit gaps**: no silent failure; failures return typed reason codes/gaps that downstream loops can act on.
- **Co-located tests protect invariants**: tests live near the modules they validate. See `docs/ethos/testing-ethos.md`.

---

## System A: RAG / Retrieval (evidence production)

### Mental model
Retrieval is a multi-lane system that converts:

- **Corpus (what exists)** → enumerated refs + hydrated content
- **Lanes (how we search)** → EvidenceCards/EvidenceSpans
- **Engine (how we orchestrate lanes)** → one unified RetrievalResult

The downstream agent loop should treat retrieval as a **tool that returns evidence**, not “text.”

### Core data types (currency)
Primary types live in:
- `backend/corpus/types.py`
- `backend/retrieval/evidence/models.py`

Key shapes:
- **`CorpusEntryRef`**: stable identifier for an entry. Retrieval must not pass raw filesystem paths.
- **`CorpusEntry`**: hydrated entry (text + metadata + provenance).
- **`EvidenceSpan`**: citeable span of text, with links back to source entry/chunk and optional trace mapping.
- **`EvidenceCard`**: lane-scored wrapper around one or more spans (the thing we rank and return).
- **`RetrievalResult`**: `{ query, cards, debug }`.

### Corpus substrate
The corpus is a read-oriented projection over the dossier and artifact stores.

Entry enumeration and hydration are implemented under:
- `backend/corpus/virtual_provider.py`
- `backend/corpus/hydrate.py`
- `backend/corpus/views/*`
- `backend/corpus/adapters/*`

Views are important because they define **high-signal subsets**:
- `FINALIZED`: canonical stitched dossier text
- `FINAL_SEGMENTS`: user-finalized per-segment drafts
- `EVERYTHING`: broad transcription universe
- `ARTIFACTS`: schema/georef artifacts

This “one universe, multiple views” pattern is the basis of evidence-first hybrid retrieval.

### Retrieval lanes
Lanes live under `backend/retrieval/lanes/` and each lane produces EvidenceCards.

Conceptual lanes (implemented):
- **Lexical**: exact-ish text matches over hydrated entries.
- **Semantic**: vector similarity search over prebuilt HNSW index pools.
- **Hybrid / HybridSemantic**: combine lanes; semantic finds the neighborhood, other lanes assemble canonical evidence.
- **Provenance**: deterministic traversal/assembly of canonical artifact bundles (correctness lane).

The orchestrator is:
- `backend/retrieval/engine/retrieval_engine.py`

### Semantic retrieval: stability architecture (Windows crash containment)
#### Why a worker exists
On Windows, native `hnswlib` calls can crash the Python process (access violation) in some call paths.
The stable architecture is:
- run HNSW querying **only in an isolated worker process**
- keep the main process safe and able to degrade gracefully
- supervise the worker, restart on failure, and return explicit reason codes when unavailable

This is implemented as a **persistent TCP worker per pool**:
- `backend/retrieval/lanes/semantic/worker/server.py` (server)
- `backend/retrieval/lanes/semantic/worker/client.py` (client)
- `backend/retrieval/lanes/semantic/worker/supervisor.py` (self-healing + backoff + budget)
- `backend/retrieval/lanes/semantic/worker/protocol.py` (message + base64 float32 vector encoding)
- `backend/retrieval/lanes/semantic/worker/README.md` (contract doc)

#### Protocol essentials
- Transport: **TCP** (local loopback by default).
- Framing: **one JSON request per line** / **one JSON response per line**.
- Vector payload: **base64 float32 bytes** (avoids JSON float bloat and dtype hazards).
- Operations: `ping`, `stats`, `reload`, `shutdown`, `knn`.
- Safety: bounded queue; returns `busy` when queue full; request timeout emits `semantic_worker_timeout`.

#### Supervisor behavior (operational contract)
The supervisor (`supervisor.py`) owns:
- **port adoption**: probe existing worker on port; reuse if pool matches; otherwise return `semantic_worker_port_in_use`.
- **exponential backoff** after failures (cap).
- **query budget** across (initial call + restart + one retry): `HNSW_WORKER_QUERY_BUDGET_MS` (default 1500ms).
- **log capture**: worker stdout/stderr routed to `backend/logs/hnsw_worker_<pool>.log`.

The semantic lane (`backend/retrieval/lanes/semantic/lane.py`) is now explicitly “metadata local + HNSW remote”:
- embedding computed in main process (with caching)
- HNSW KNN executed in worker
- metadata lookup in SQLite metadata store remains in main process

#### Semantic pools
Two semantic pools exist today:
- `FINAL_SEGMENTS` (default)
- `EVERYTHING`

Ports are configurable:
- `HNSW_WORKER_PORT_FINAL_SEGMENTS` (default 9351)
- `HNSW_WORKER_PORT_EVERYTHING` (default 9352)
- `HNSW_WORKER_HOST` (default 127.0.0.1)

Queue and timeout knobs:
- `HNSW_WORKER_QUEUE_SIZE` (default 64)
- `HNSW_WORKER_REQUEST_TIMEOUT_SEC` (default 10)
- `HNSW_WORKER_CLIENT_TIMEOUT_SEC` (default 3)
- `HNSW_WORKER_QUERY_BUDGET_MS` (default 1500) — end-to-end budget in supervisor across initial call + restart + one retry

#### Worker request/response fields (contract sketch)
Requests are JSON objects with a stable shape (see `backend/retrieval/lanes/semantic/worker/protocol.py`):
- common:
  - `request_id`: unique id (hex)
  - `op`: `"ping" | "stats" | "reload" | "shutdown" | "knn"`
  - `pool_identifier`: `"FINAL_SEGMENTS" | "EVERYTHING"`
- knn-specific:
  - `k`: number of neighbors
  - `ef`: optional HNSW ef parameter
  - `embedding_dim`: expected vector dim
  - `vector_b64`: base64 float32 bytes
  - `manifest_fingerprint`: optional fingerprint to ensure the worker loaded the same index identity as the caller expects

Responses are JSON objects:
- common:
  - `request_id`
  - `status`: `"ok" | "error" | "busy"`
  - `reason_code`: stable machine token for non-ok outcomes
- knn-specific:
  - `results`: list of `(label, distance)` pairs
- stats-specific:
  - `worker_stats`: `{ pool_identifier, total_vectors, embedding_dim, manifest_fingerprint, uptime_s }`

#### Semantic worker reason codes (non-exhaustive but canonical)
The worker/supervisor layer uses stable reason codes so callers can branch deterministically. Common examples:
- `semantic_worker_unavailable`: cannot connect / timed out at socket layer
- `semantic_worker_timeout`: worker did not respond within timeout/budget
- `semantic_worker_busy`: queue full; backpressure signal (not a crash)
- `semantic_worker_manifest_mismatch`: caller fingerprint/dim does not match worker state
- `semantic_worker_reload_failed`: worker failed to reload index/manifest
- `semantic_worker_port_in_use`: port is occupied by a non-worker or wrong-pool worker (supervisor enters backoff)
- `semantic_worker_in_backoff`: supervisor backoff window active after repeated failures

#### Latency model (observability)
Semantic retrieval latency tends to be dominated by **embedding** time unless the embedding provider is kept warm.
The semantic lane is instrumented to include timing fields in `RetrievalResult.debug` (see `backend/retrieval/lanes/semantic/lane.py`):
- `embed_ms`
- `manifest_ms`
- `metadata_open_ms`
- `worker_knn_ms`
- `total_lane_ms`

The CLI also supports an interactive mode to keep the embedding model loaded in-process:
- `backend/retrieval/tools/retrieval_cli.py --interactive`

### Index maintenance and truthful health reporting
Index maintenance endpoints live in:
- `backend/api/endpoints/index_maintenance.py` (prefix `/api/index`)

Key invariants:
- The on-disk HNSW index (`hnsw.bin`) must be persisted after mutations.
- Health reports must never claim “ready” when the vector store is empty/mismatched.
- Diagnostics must surface both **metadata counts** and **HNSW counts** with explicit mismatch reason codes.

Semantic index on-disk layout (per pool) is managed under the assets root (dev: `<repo>/assets`, frozen: `%LOCALAPPDATA%/Plattera/Data/assets`):
- `assets/semantic_indexes/<POOL>/hnsw.bin` (HNSW graph)
- `assets/semantic_indexes/<POOL>/metadata.db` (vector-label → chunk/entry metadata)
- `assets/semantic_indexes/<POOL>/manifest.json` (index identity: embedding dim, model id/fingerprint, chunking policy id, etc)

Operational support:
- `/api/index/diagnose?pool_identifier=...&include_worker=true` includes worker health stats (supervisor-driven).
- After a successful index maintenance job, the worker is restarted to reload updated `hnsw.bin`.

### Retrieval surfaces (for humans and agents)
#### CLI
The CLI is the primary “durable testing surface”:
- `backend/retrieval/tools/retrieval_cli.py`

Capabilities:
- single-query retrieval (multiple lanes)
- batch query-set evaluation (durable artifacts per run)
- optional index health snapshots
- optional full-text expansion (guardrailed/truncated)
- interactive mode to keep embedding model warm

Artifacts land under:
- `assets/rag_runs/`

#### API
The retrieval API surface is:
- `POST /api/retrieval/search`
- `backend/api/endpoints/retrieval.py`

Response shape:
- `result`: `{ query, cards, debug }`
- optional `index_health`
- optional `expanded_entries`

---

## System B: Feature Graph IR (universal deed meaning substrate)

### Purpose and stance
Feature Graph IR is a universal, extensible internal language for representing the meaning of a deed as:
- **typed features** (point/curve/region/frame/constraint/etc)
- **operations** that derive features from other features
- **explicit references/dependencies** across graphs (external FeatureRefs)
- **provenance** (citations to source spans + evidence refs)
- **typed gaps** for deterministic failures (no silent failure)

The IR is designed for **total representability**:
> Any deed assertion must be encodable in IR, even if it cannot yet be compiled or georeferenced.

### Core modules
- **IR models**: `backend/feature_graph/models.py`
- **Provenance models**: `backend/feature_graph/provenance.py`
- **Typed gaps + judge report**: `backend/feature_graph/gaps.py`
- **Operation registry**: `backend/feature_graph/operations.py`
- **Compiler (best-effort)**: `backend/feature_graph/compiler.py`
- **Judge (deterministic validation)**: `backend/feature_graph/judge.py`
- **Bundler (portability)**: `backend/feature_graph/bundle.py`
- **Artifact models**: `backend/feature_graph/artifacts.py`
- **Persistence service**: `backend/services/feature_graph/feature_graph_persistence_service.py`
- **Paths**: `backend/config/paths.py` (`dossiers_feature_graphs_artifacts_root`)
- **API endpoints**: `backend/api/endpoints/feature_graph.py` (prefix `/api/feature-graph`)

### IR model: nodes, edges, and the “content source” invariant
`FeatureGraph` contains:
- `graph_id`
- `nodes: List[FeatureNode]`
- `edges: List[FeatureEdge]`
- `metadata`

`FeatureNode` has a critical invariant:
- A node must be defined by **at most one** of:
  - `geometry` (direct geometry)
  - `op_expr` (operation expression)
  - `feature_ref` (reference)

This is enforced with a Pydantic model validator in `models.py`.

Feature kinds (`FeatureKind`) include:
- `point`, `curve`, `region`, `frame`, `constraint`, `annotation`, `unknown`

`OpExpr`:
- `op_name: str`
- `params: Dict[str, Any]`
- `operands: List[Union[str, OpExpr]]`

`FeatureRef` supports cross-graph dependencies:
- `{ feature_id, graph_id?, label?, is_external }`

### Provenance: citations as first-class attachments
Provenance types exist to attach evidence to graph elements:
- `TextSpan`: precise location in a source document
- `EvidenceRef`: reference to corpus evidence (doc/chunk/segment)
- `Citation`: bundles span + evidence refs
- `ProvenanceAttachment`: attach citations to nodes/edges, plus lineage fields

### Operation registry vs compiler support
The operation registry (`backend/feature_graph/operations.py`) is the **vocabulary of allowed computations** expressible in IR.

Key design choices:
- **Operations are representable even if not yet compilable.** This protects total representability.
- Each operation definition includes:
  - category (traverse / derive / constraint / boolean)
  - parameter specs (required/optional, units, raw-string fields)
  - operand arity constraints (min/max operands)
  - `supported: bool` which indicates compiler support today

What “supported” means:
- `supported=True` indicates the compiler can produce concrete outputs for that op.
- `supported=False` indicates the compiler must emit a typed `unsupported_operation` gap (deterministically).

Current compiler support (as implemented today in `backend/feature_graph/compiler.py`):
- `LineStep` (traverse straight segment using bearing + distance)
- `Close` (derive region from a closed curve)

Everything else can exist in IR and be judged, but will not compile into geometry until implemented.

### Typed gaps and deterministic reports (compiler + judge)
Typed gaps are the deterministic “currency of failure,” designed to power an agent loop.

Gap kinds live in `backend/feature_graph/gaps.py`:
- `missing_anchor`
- `missing_operand`
- `missing_parameter`
- `ambiguous_choice`
- `unsupported_operation`
- `precondition_failed`

Gaps are designed to be:
- **machine-actionable** (kind + metadata)
- **human-readable** (message)
- **evidence-linked** (citations)

The judge returns a `JudgeReport` that can be converted to an existing agent contract shape:
- `JudgeReport.to_contract_report()` returns `status ∈ {success, partial, failed}` plus diagnostics.

### Compiler: best-effort local geometry (partial outputs, never silent)
Compiler entrypoint:
- `backend/feature_graph/compiler.py::compile_graph(graph: FeatureGraph) -> CompileResult`

Stance:
- **best-effort** compilation: produces partial outputs plus typed gaps for what couldn’t be compiled.
- **local-first**: compiled outputs are in a local coordinate frame unless/until explicitly anchored and georeferenced downstream.

Compiler outputs:
- `compiled_features: Dict[node_id, Any]` where each entry typically includes:
  - `geometry` in a GeoJSON-like shape (`LineString`, `Polygon`, etc) in local units (feet today)
  - metadata about how it was produced (source, bearing/distance, start/end points, etc)

Current traversal chaining behavior:
- A simple `previous_point` heuristic is used to chain `LineStep` nodes in list order.
- Long-term, robust compilation will use **edges/topological order** (and/or explicit traverse groups).

### Judge: deterministic validation and “local-first missing anchors”
Judge entrypoint:
- `backend/feature_graph/judge.py::judge_graph(graph: FeatureGraph, include_warnings: bool = True) -> JudgeReport`

Judge responsibilities:
- missing operands (refs to nonexistent feature IDs)
- missing required parameters (by op definition)
- unsupported operations (by registry/compiler support flags)
- precondition failures (e.g., cannot close an unclosed curve)
- missing anchors (only when global placement is explicitly required)

Important semantic choice: **missing anchors are opt-in**.
- By default, a feature graph can be purely local.
- Anchoring is required only when:
  - `graph.metadata["global_placement_required"]` is true, or
  - a node has `node.metadata["requires_global_placement"]` true

This is designed to allow a clean staged pipeline:
1) represent meaning locally
2) compile locally
3) request anchoring/georeference only when the workflow requires a global map

### Bundle: portability and explicit dependency policy (Policy A)
Bundle entrypoint:
- `backend/feature_graph/bundle.py::bundle_feature_graph(...) -> BundleArtifact`

Bundles exist to make feature graphs portable and dependency-closed.
They package:
- the target graph
- the minimal dependency subgraphs
- reasons for inclusion or omission

**Policy A (explicit external dependency nodes):**
- Dependencies are discovered only from explicit `FeatureNode.feature_ref` objects where `is_external=true`.
- If “external-like references” are found inside nested `op_expr` payloads, they are **not included**, but a reason is recorded so the omission is explicit and testable.

This prevents “hidden dependencies” from silently breaking portability.

### Feature Graph artifacts (durable pipeline states)
Artifact models live in `backend/feature_graph/artifacts.py`:
- `IRArtifact`: stores the full `FeatureGraph`
- `CompileArtifact`: stores compiled outputs + serialized gaps + warnings
- `JudgeArtifact`: stores the full `JudgeReport`
- `BundleArtifact`: stores target graph + dependencies + reasons

All artifacts include:
- `artifact_id`
- `artifact_type`
- `metadata: ArtifactMetadata` including `created_at`, `created_by`, `parent_artifact_ids`, `version`

This implements “persistence as truth” for the feature graph pipeline.

### Feature Graph persistence (atomic, indexed, isolated from legacy artifacts)
Persistence service:
- `backend/services/feature_graph/feature_graph_persistence_service.py`

Storage layout (dev and frozen-safe via `backend/config/paths.py`):
- Artifacts:
  - `backend/dossiers_data/artifacts/feature_graphs/<dossier_id>/<artifact_id>.json`
- Index:
  - `backend/dossiers_data/state/feature_graphs_index.json`

Write semantics:
- atomic write using temp file + `os.replace`
- index entry deduped by `(dossier_id, artifact_id)` and sorted by `saved_at` desc

### Feature Graph API surface (agent-facing tool surface)
Router:
- `backend/api/endpoints/feature_graph.py`
- mounted at `/api/feature-graph` in `backend/api/router.py`

Endpoints:
- `POST /api/feature-graph/save`
  - Save an artifact (ir/compile/judge/bundle) by deserializing into the correct artifact model.
- `GET /api/feature-graph/get/{dossier_id}/{artifact_id}`
- `GET /api/feature-graph/list/{dossier_id}?artifact_type=...`
- `GET /api/feature-graph/list-all?artifact_type=...`
- `POST /api/feature-graph/compile`
  - Input: `{ dossier_id, graph, artifact_id?, parent_artifact_ids? }`
  - Output: persisted `CompileArtifact` (gaps serialized to dicts)
- `POST /api/feature-graph/judge`
  - Input: `{ dossier_id, graph, include_warnings, artifact_id?, parent_artifact_ids? }`
  - Output: persisted `JudgeArtifact`
- `POST /api/feature-graph/bundle`
  - Input: `{ dossier_id, target_graph, available_graphs?, bundle_purpose?, ... }`
  - Output: persisted `BundleArtifact`

---

## System C: Mapping / Georeference (deterministic numeric core)

### Current state
Mapping and georeference are deterministic and already robust; they are treated as the “truth engine” for global placement.

Key API router files:
- `backend/api/endpoints/georeference.py` (`/api/georeference/*`)
- `backend/api/endpoints/mapping.py` (`/api/mapping/*`)

The “native” georeference primitive today is:
- `POST /api/georeference/project`
  - input includes `local_coordinates`, `plss_anchor`, optional `starting_point` tie-to-corner, and `options`
  - delegates into `pipelines.mapping.georeference.georeference_service.GeoreferenceService.georeference_polygon(...)`

There is also a legacy-convenience endpoint:
- `POST /api/georeference/project-from-schema`
  - extracts anchor + local coords from legacy schema + polygon data

Validation primitive:
- `POST /api/mapping/validate-georef`
  - validates a georeferenced polygon against PLSS context using deterministic checks

Persistence:
- `backend/services/georeference/georeference_persistence_service.py`

### Intended integration stance (native seam for Feature Graph)
Long-term, the goal is **not** to force Feature Graph outputs to conform to legacy schema shapes.
Instead, the goal is to make mapping/georeference ergonomic to Feature Graph outputs by introducing an explicit adapter seam:

- **Input**: `CompileArtifact` + `target_feature_id` (the compiled region/polygon) + anchor description
- **Adapter**: extracts local geometry and converts to the internal `local_coordinates` payload shape
- **Georeference**: uses the existing deterministic engine to produce geographic coordinates
- **Validation**: runs `/api/mapping/validate-georef` to produce objective QA metrics
- **Persistence**: saves a georef artifact linked by lineage to the feature graph artifacts

This keeps the numeric engine authoritative and stable while evolving the meaning substrate.

---

## The agent loop: purpose, capabilities, and outputs (north star)

### North star purpose
Given deed(s) and context, the system should produce a mapped artifact the user can trust:
- a georeferenced polygon (and supporting overlays/metadata)
- a deterministic validation report
- explicit provenance and lineage
- durable persisted artifacts for rehydration, debugging, and reuse

### What the agent produces (primary output)
The agent’s primary authored object should be:
- **Feature Graph IR**: a `FeatureGraph` JSON object

Persisted form:
- **IR artifact** (`artifact_type="ir"`) stored under the feature graph artifacts root.

### What the application (non-agent) must do after IR is produced
The application should own deterministic downstream steps:
- compile (`/api/feature-graph/compile`)
- judge (`/api/feature-graph/judge`)
- (when required) georeference + validate + persist
- generate renderable map overlays for UI (and optionally agent review)

The agent loop should not need to understand low-level persistence details; it should rely on stable contract surfaces.

### Required agent capabilities (eventual)
The eventual loop must be able to:
- **Read corpus evidence** using retrieval (lexical/semantic/provenance) and cite it in provenance attachments.
- **Construct FeatureGraph IR** that is representationally complete and structurally valid (mutual exclusivity, stable ids).
- **Resolve dependencies**:
  - represent external references using explicit `FeatureRef(is_external=true)`
  - request bundling when portability is required
- **Iterate based on deterministic gaps**:
  - interpret judge/compiler gaps as typed “needs”
  - retrieve evidence targeted to those needs
  - patch IR deterministically (smallest change that addresses the gap)
- **Request global placement** only when needed:
  - set `global_placement_required` when generating a map is required
  - otherwise allow local-only partials during early interpretation
- **Produce explainable outcomes**:
  - SUCCESS: compiled + judged + georeferenced + validated
  - PARTIAL: local-only or missing anchor (explicit)
  - NEEDS_USER_CHOICE: ambiguous gap that requires a selection
  - NEEDS_UPLOAD: missing dependency document
  - FAILED: budgets exceeded or irreconcilable contradictions

### Agent-facing contract surfaces (recommended stable “toolbox”)
These are the seams the agent loop should call:
- Retrieval:
  - `POST /api/retrieval/search`
  - CLI `backend/retrieval/tools/retrieval_cli.py` for offline evaluation
- Feature Graph:
  - `POST /api/feature-graph/compile`
  - `POST /api/feature-graph/judge`
  - `POST /api/feature-graph/bundle`
  - `POST /api/feature-graph/save` (artifact persistence)
- Index ops (ops/diagnosis):
  - `GET /api/index/diagnose?pool_identifier=...&include_worker=true`
- Georeference + validation:
  - `POST /api/georeference/project` (low-level primitive)
  - `POST /api/mapping/validate-georef` (deterministic QA)

Long-term, introduce higher-level “ergonomic” endpoints so the agent doesn’t have to manually assemble low-level payloads:
- `POST /api/feature-graph/map` (compile → judge → georef → validate → persist)
- `POST /api/feature-graph/render` (create a visual artifact for review)

---

## Accuracy standards (what “good” means)

### Retrieval standards (RAG)
Retrieval is correct when it:
- returns EvidenceCards that are **traceable to corpus entry refs**
- provides citeable spans (with preview/trace where applicable)
- is robust under scale:
  - embeddings are a finder, not a correctness dependency
  - provenance lane assembles the deterministic canonical artifact bundle once anchored

Operational truth standards:
- health reporting must not claim readiness when indexes are empty/mismatched
- semantic worker failures must degrade gracefully with explicit reason codes

### Feature Graph standards (IR + validation)
IR correctness is not “confidence”; it is structural and evidential:
- total representability: the deed’s meaning can be encoded without inventing unsupported shortcuts
- provenance-first: major assertions should carry citations
- deterministic validation: same IR produces the same judge result
- no silent failure: unsupported ops/missing params produce typed gaps

### Mapping standards (global placement)
Global placement is correct when:
- a deterministic georeference run succeeds and produces a geographic polygon
- deterministic validation passes or returns explicit diagnostics
- precision and bounds checks are satisfied (per validator design)
- any ties/anchors are explicit and evidence-linked (not implicit guesses)

### Outcome classification (agent loop)
The loop must always end in an explicit, durable state:
- **SUCCESS**: judged success (or acceptable partials) + georeferenced + validated + persisted
- **PARTIAL**: local-only geometry exists; explicit gaps explain what blocks global placement
- **NEEDS_USER_CHOICE**: ambiguity is irreducible without a selection (e.g., ambiguous reference)
- **NEEDS_UPLOAD**: dependency missing from corpus
- **FAILED**: budget exceeded or contradictions; must include diagnostic summary

Budgets should be first-class:
- iteration cap
- retrieval budget (lane limits)
- semantic worker query budget (already enforced)
- artifact emission per iteration (“persistence as truth”)

---

## RAG + Feature Graph integration (future-facing, deliberate)

### Making Feature Graph artifacts retrievable (without “just embed the JSON”)
The preferred integration is to make feature graph artifacts **retrievable as evidence cards** via a dedicated artifact/provenance lane, rather than naively embedding raw JSON.

Recommended approach:
- generate deterministic text summaries of feature graphs and judge outcomes (op names, kinds, gap kinds, anchor requirements)
- index those summaries with stable IDs pointing back to artifacts
- return results as EvidenceCards with spans pointing to the artifact content

This gives agents:
- “example mining” (successful graphs)
- dependency retrieval (external referenced graphs)
- fast filtering by status (success/partial/failed)

### Bundles as portable knowledge
Bundles (`BundleArtifact`) should be treated as the “portable unit of meaning”:
- dependency-closed
- reasoned inclusion/exclusion
- safe to share/export

---

## Roadmap (high-signal next builds)

### Near-term (unlock the agent loop)
- Define a formal “agent contract” doc for:
  - IR submission
  - compile/judge
  - map/georef/validate
  - outcomes and reason codes
- Add an ergonomic FeatureGraph→Georeference adapter endpoint (so agents don’t build low-level coordinate payloads).
- Add an optional render artifact (image or vector overlay) so an agent (and a human) can visually sanity-check.
- Add a “feature graph artifact lane” to retrieval so agents can retrieve successful examples and dependencies as evidence.

### Medium-term (expand geometric expressiveness)
- Implement more operations in the compiler in a principled order:
  - traversal: `CurveStep` (with clear parameterization rules)
  - derive: `Buffer`, `Offset`
  - boolean region ops
  - constraints (if/when the compiler is extended beyond pure geometry emission)
- Replace node-order chaining with edge/toposort compilation for traverses.

---

## Glossary (canonical terms)
- **Artifact**: durable JSON written to disk with metadata + lineage; source of truth.
- **Corpus**: enumerated/hydratable projection of stored content into stable entry refs.
- **Evidence**: citeable spans packaged as EvidenceCards/Spans; output currency of retrieval.
- **Feature Graph IR**: universal intermediate representation of deed meaning (`FeatureGraph`).
- **Gap**: typed deterministic failure record used to drive repair loops.
- **Judge**: deterministic validator producing a `JudgeReport`.
- **Compile**: best-effort local geometry emission producing compiled outputs + gaps.
- **Bundle**: portable packaging of a graph with its minimal dependency subgraphs.
- **Semantic worker**: isolated HNSW querying process for crash containment and robustness.

---

## Reference map (files and surfaces)
### Feature Graph
- IR: `backend/feature_graph/models.py`
- Ops: `backend/feature_graph/operations.py`
- Compiler: `backend/feature_graph/compiler.py`
- Judge: `backend/feature_graph/judge.py`
- Gaps: `backend/feature_graph/gaps.py`
- Bundle: `backend/feature_graph/bundle.py`
- Artifacts: `backend/feature_graph/artifacts.py`
- Persistence: `backend/services/feature_graph/feature_graph_persistence_service.py`
- API: `backend/api/endpoints/feature_graph.py` (`/api/feature-graph/*`)

### Retrieval / RAG
- Spec: `docs/retrieval_system_spec.md`
- Ethos: `docs/Evidence_First_Hybrid_Retrieval_for_Plattera.md`
- CLI: `backend/retrieval/tools/retrieval_cli.py`
- API: `backend/api/endpoints/retrieval.py` (`POST /api/retrieval/search`)
- Semantic lane: `backend/retrieval/lanes/semantic/lane.py`
- Worker: `backend/retrieval/lanes/semantic/worker/*`
- Index ops: `backend/api/endpoints/index_maintenance.py` (`/api/index/*`)

### Mapping / Georeference
- Georef API: `backend/api/endpoints/georeference.py` (`/api/georeference/*`)
- Mapping API: `backend/api/endpoints/mapping.py` (`/api/mapping/*`)
- Georef persistence: `backend/services/georeference/georeference_persistence_service.py`

---

## Suggested verification commands (for humans/coding agents)
Always activate the repo venv first (PowerShell):

```bash
.venv\scripts\activate.ps1
```

High-signal checks:
- Feature Graph unit tests:

```bash
pytest backend/feature_graph -q
```

- Feature Graph API tests:

```bash
pytest backend/api/test_feature_graph_ir_endpoints.py -q
pytest backend/api/test_feature_graph_compile_endpoints.py -q
```

- Semantic worker protocol test:

```bash
pytest backend/retrieval/lanes/semantic/test_worker_protocol.py -v
```

- Retrieval CLI smoke (semantic lane):

```bash
python -m retrieval.tools.retrieval_cli "thence" --lanes semantic --semantic-pool FINAL_SEGMENTS --limit 5 --include-index-health
```

- Index + worker health (backend running):

```bash
curl "http://127.0.0.1:8000/api/index/diagnose?pool_identifier=FINAL_SEGMENTS&include_worker=true"
```
