## Agent Kernel Controller Spec (step-driven) — v0.1

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

## 2) Pivot: simplify LLM interface layer (tool calling + local validation)

### 2.1 Why we are pivoting
We experimented with OpenAI Structured Outputs (`response_format: json_schema`, `strict: true`) for controller proposals.
In practice, that approach introduces hard coupling to OpenAI’s supported JSON Schema subset and quickly becomes brittle for
agent-loop protocols (which are dynamic and evolve frequently).

Observed failure modes included strict-schema validation rejections for common schema constructs (e.g. `additionalProperties`,
`required` semantics, and later `oneOf` not permitted). These failures block execution entirely with `400 Bad Request`, which is
the opposite of what we want in an agent loop.

**First principles:** the kernel is the truth oracle and safety gate. The LLM is an unreliable proposer. We want misfires to be
recoverable via deterministic refusals and feedback, not to hard-fail at the API boundary.

Therefore:
- We keep **strictness inside our code** (Pydantic validation + tool/menu gating + kernel refusals).
- We keep the **LLM boundary minimal and stable** (one tool call with bounded args).

### 2.2 End-state interface: single tool call (`kernel_step`)
The controller requests that the model propose exactly one next kernel step by calling a single tool/function.
This keeps the interface tiny, avoids JSON Schema unions, and leverages model training around tool calling.

Tool/function name: `kernel_step`

Arguments (controller-owned contract):
- `action_type` (required): string enum matching kernel `ActionType`
- `args` (required): object (bounded; refs-not-blobs; validated locally per action)
- `idempotency_key` (required): string (controller may generate if missing)
- `why` (required): short string (bounded; primarily for transcript/debug)
- `semantic_ready` (optional): bool
- `notes` (optional): short string (bounded)

**Important:** we do NOT attempt to encode per-action argument typing into the OpenAI schema. We validate per-action args locally.

### 2.3 Fallback transport (allowed): JSON-only message (`json_object`)
If tool calling is temporarily unavailable for a target model/runtime, the controller may fall back to JSON mode:
- `response_format: { "type": "json_object" }`
- developer instruction: “Return exactly one JSON object; no markdown; no extra text.”

The JSON object must match the same minimal contract as the tool call: `{ action_type, args, idempotency_key, why, ... }`.

---

## 3) Controller invariants (must enforce)

The controller MUST require the LLM to output exactly one next-step proposal per iteration, either as:
- a single tool call to `kernel_step` (preferred), or
- a single JSON object in `json_object` mode (fallback).

### 3.1 Tool existence + menu enforcement
- The controller MUST NOT submit an action not present in kernel `tool_menu`.
- If missing, controller returns a refusal-like controller error:
  - `reason_code="action_not_in_tool_menu"`

---

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

### 3.4 Validate locally before calling the kernel
Controller must validate:
- minimal proposal contract shape (`action_type`, `args`, `idempotency_key`, `why`)
- action in tool_menu
- boundedness of `args`
- per-action required fields (controller-owned typed validators)

### 3.5 Verify-before-commit as *gate*, not *branch*
- The controller MUST NOT force a fixed sequence.
- But it MUST enforce that `DECLARE_DONE` is only attempted if:
  - kernel claimability is ready (or the kernel will refuse)
  - AND a bounded justification payload is present in `args` (controller validates locally)

Optional (v0.1): artifact “freshness” requirement that judge/compile occur after last IR mutation.

---

## 4) Retrieval intent mapping (deterministic)

Controller maps a high-level retrieval intent → a deterministic query-pack used in `kernel_step.args` for `RETRIEVE_EVIDENCE`.

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
- Require: output exactly one `kernel_step` tool call (or one JSON object in fallback mode).
- Provide: tool_menu + dashboard + a compact working set, not raw blobs.

### 5.2 Plan cadence
- Encourage a short plan at session start and on major surprises.
- Discourage re-planning every step.

---

## 6) Acceptance tests (controller)

Controller test suite should cover:
- Parses/handles exactly one proposal per iteration (tool call preferred; JSON fallback supported)
- Rejects actions not in tool_menu
- Enforces payload bounds (oversized inputs rejected)
- Retrieval intent mapping is deterministic
- DECLARE_DONE requires justification payload in `args`, otherwise controller refuses before calling kernel
- Idempotency: retries reuse key; mismatched payload generates new key

---

## 7) Migration plan: update current implementation to the end-state

This section lists the concrete adjustments needed in the current codebase to reach the end-state described in §2.

### 7.1 Replace strict structured outputs with tool calling (or JSON-only fallback)
Files to change:
- `backend/agents/controller/openai_client.py`

Changes:
- Stop using `response_format: { type: "json_schema", strict: true }` for controller proposals.
- Prefer tool calling:
  - define a single tool/function `kernel_step` with minimal args described in §2.2
  - request exactly one tool call per step
  - parse tool-call arguments as JSON and validate locally
- If tool calling is unavailable in a target environment, fall back to:
  - `response_format: { "type": "json_object" }` with the same minimal contract

### 7.2 Simplify controller contracts to a minimal proposal model
Files to change:
- `backend/agents/controller/contracts.py`

Changes:
- Replace the OpenAI-facing strict-schema envelope/union with a minimal proposal model:
  - `action_type: ActionType | str`
  - `args: dict[str, object]` (bounded)
  - `idempotency_key: str`
  - `why: str`
- Keep per-action typed validators locally (dispatch table) but do not attempt to export them as OpenAI JSON Schemas.

### 7.3 Controller loop: refusal-first retries
Files to change:
- `backend/agents/controller/controller.py`

Changes:
- On parse/validation errors, emit a structured `controller_refusal` event containing:
  - reason_code
  - missing/invalid fields
  - a corrected skeleton for the minimal proposal contract
- Limit retries per step (typically 1–2).

### 7.4 Update docs and prevent regression
Files to update:
- This spec (`docs/agent-kernel-controller-spec.md`)
- `backend/agents/controller/agents.md` (sticky note for the folder)
- `backend/services/llm/openai_config.md` (explain: strict JSON Schema is for stable extraction tasks, not dynamic agent protocols)

### 7.5 Keep observability and eval hooks weight-bearing
Ensure the following stay intact:
- `openai_next_step_error {...}` structured logs and transcript capture
- kernel step results recorded with refs and reason codes
- metrics or summaries for: refusal distribution, retries, steps, cost

---

## 8) Links
- Build clouds:
  - `build clouds/agent-kernel-step-driven-alignment-spec-v0.md`
  - `build clouds/agent-kernel-controller-loop-build-cloud.md`
  - `build clouds/agent-kernel-mismatch-report-step-driven-vision.md`
- Kernel code:
  - `backend/agent_kernel/session.py`
  - `backend/agent_kernel/models.py`
  - `backend/agent_kernel/actions.py`

