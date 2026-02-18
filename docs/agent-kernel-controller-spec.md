## Agent Kernel Controller Spec (step-driven) — v0

### Scope
This spec defines the **Controller** that drives the step-driven kernel:
- Kernel: executes one action (`start_session` / `step`) + persists run artifact + returns dashboard/refusal.
- Controller: calls the LLM, validates proposals, enforces invariants, calls kernel tools.
- LLM: proposes the next step (action + inputs + intent + justification).

This spec is designed to align with:
- `build clouds/agent-kernel-step-driven-alignment-spec-v0.md`
- `build clouds/agent-kernel-controller-loop-build-cloud.md`

---

## 1) Controller API (library-first)

### Proposed module placement
- `backend/agents/controller/` (new package)
  - `controller.py` (core loop)
  - `contracts.py` (Pydantic models for LLM I/O)
  - `retrieval_intents.py` (intent → query-pack mapping)
  - `prompting/` (prompt templates)

### Controller entrypoints (v0)
- `run_controller_loop(...) -> ControllerRunResult`
  - Inputs:
    - kernel session start request (or request_id + bootstrap inputs)
    - model selection (e.g. `gpt-5-mini`)
    - max controller iterations / max tokens budget
  - Output:
    - terminal outcome
    - controller transcript artifact ref
    - last kernel dashboard

Note: controller should be unit-testable with a fake LLM provider and an in-memory kernel persistence.

---

## 2) LLM output contract: NextStepProposal (strict JSON)

The controller MUST require the LLM to output a single JSON object matching this schema.

### 2.1 Fields
- `action_type` (required): string enum matching kernel `ActionType`
- `idempotency_key` (required): string, controller-generated is allowed; must be stable on retry for same proposal
- `inputs` (required): object (refs-not-blobs; controller enforces bounds)
- `why` (required): string (<= 500 chars)
- `retrieval_intent` (optional): string enum, used only when `action_type == "retrieve_evidence"`
- `declare_done` (optional): object, required when `action_type == "declare_done"`
- `notes` (optional): string (<= 500 chars)

### 2.2 RetrievalIntent enum
- `ANCHOR_HUNT`
- `DEPENDENCY_HUNT`
- `EXEMPLAR_LOOKUP`
- `TERMINOLOGY_CHECK`
- `GENERAL`

### 2.3 DeclareDoneJustification
Required when `action_type == "declare_done"`:
- `artifact_refs`:
  - `ir_ref` (string or object ref)
  - `compile_ref`
  - `judge_ref`
  - `bundle_ref` (optional)
  - `georef_ref` (optional)
  - `validate_ref` (optional)
  - `render_ref` (optional)
- `evidence_links`: array (1..20) of:
  - `source`: enum `DEED` | `RAG`
  - `ref`: artifact ref (e.g. retrieval artifact with card/span indices) or corpus entry ref
  - `claim`: short string (<= 200 chars) describing what the evidence supports
- `accepted_deviations`: array (0..20) of:
  - `kind`: string enum (controller-owned) e.g. `APPROXIMATION`, `ASSUMPTION`, `MISSING_DATA_ACCEPTED`
  - `reason`: short string (<= 200 chars)

---

## 3) Controller invariants (must enforce)

### 3.1 Tool existence + menu enforcement
- The controller MUST NOT submit an action not present in kernel `tool_menu`.
- If missing, controller returns a refusal-like controller error:
  - `reason_code="action_not_in_tool_menu"`

### 3.2 Idempotency discipline
- Controller must supply idempotency keys and re-use them on retry of the same proposed step.
- If the kernel returns `idempotency_key_payload_mismatch`, controller must treat it as non-retryable and generate a new key for a new proposal.

### 3.3 Refs-not-blobs enforcement
- Controller must reject proposals that include:
  - large inline geometry
  - oversized payloads
  - unbounded text dumps
- Controller should prefer:
  - `OPEN_ARTIFACT` for inspection
  - persisted artifacts for large payloads

### 3.4 Verify-before-commit as *gate*, not *branch*
- The controller MUST NOT force a fixed sequence.
- But it MUST enforce that `DECLARE_DONE` is only attempted if:
  - kernel claimability is ready (or the kernel will refuse)
  - AND justification schema is present

Optional (v0.1): artifact “freshness” requirement that judge/compile occur after last IR mutation.

---

## 4) Retrieval intent mapping (deterministic)

Controller maps `retrieval_intent` → query-pack used in `RETRIEVE_EVIDENCE.inputs`.

### 4.1 Query-pack shape (inputs)
- `query: str`
- `intent: RetrievalIntent`
- `options: {limit:int, expand:bool,...}` (bounded)
- `routing: {lanes:[...], pool:..., view:..., filters:{...}}` (controller-owned, deterministic)

### 4.2 Degradation behavior
- If semantic worker unavailable, controller may:
  - retry with lexical-only routing, OR
  - ask the agent to choose a different move

This must be surfaced to the agent via observation and stable reason codes.

---

## 5) Prompting strategy (controller-owned)

### 5.1 System/developer prompt goals
- Explain: agent chooses one next action only.
- Explain: kernel can refuse; refusals are data; do not argue with refusals.
- Require: output strict JSON matching NextStepProposal schema.
- Provide: tool_menu + dashboard + a compact working set, not raw blobs.

### 5.2 Plan cadence
- Encourage a short plan at session start and on major surprises.
- Discourage re-planning every step.

---

## 6) Acceptance tests (controller)

Controller test suite should cover:
- Parses strict NextStepProposal JSON
- Rejects actions not in tool_menu
- Enforces payload bounds (oversized inputs rejected)
- Retrieval intent mapping is deterministic
- DECLARE_DONE requires justification object, otherwise controller refuses before calling kernel
- Idempotency: retries reuse key; mismatched payload generates new key

---

## 7) Links
- Build clouds:
  - `build clouds/agent-kernel-step-driven-alignment-spec-v0.md`
  - `build clouds/agent-kernel-controller-loop-build-cloud.md`
  - `build clouds/agent-kernel-mismatch-report-step-driven-vision.md`
- Kernel code:
  - `backend/agent_kernel/session.py`
  - `backend/agent_kernel/models.py`
  - `backend/agent_kernel/actions.py`

