## Agent Kernel Step-Driven Alignment Spec v0 (build cloud)

### Scope
This spec defines the **exact implementation** needed to close the mismatch described in:
- `build clouds/agent-kernel-mismatch-report-step-driven-vision.md`

It locks the v0 architecture decision:
- **Kernel** is a *dumb step executor + ledger* (executes/refuses/stops; never substitutes actions).
- **Controller/agent** (GPT‑5.2 or other provider) is the strategist (chooses next step).
- **Deterministic engines** are physics gates (compile/judge/georef/validate/render).

---

## 0) Non‑negotiables (must be enforced in code + tests)
- **One action per step**: kernel executes exactly the requested action, or refuses/stops.
- **No substitution**: kernel may refuse or stop; it must never “do the next logical thing.”
- **Done is agent-declared, kernel-claimable** via `DECLARE_DONE` only.
- **Refs‑not‑blobs**: persist artifacts; inline payloads are compact and bounded.
- **Autopilot is a controller** built on `step()` (optional), not a second kernel interface.
- **semantic_ready is audit-only**: echoed/persisted but never used for acceptance/refusal logic.

---

## 1) Primary kernel surface (library-first)

### New module(s)
- `backend/agent_kernel/session.py` (primary implementation)
- `backend/agent_kernel/claimability.py` (claimability gates + evaluation)
- Optional: `backend/agent_kernel/dashboard.py` (pure helpers; keep small)

### Export surface
Update `backend/agent_kernel/__init__.py` to export:
- `start_session(...)`
- `step(...)`
- session models (start/step requests/results)

---

## 2) Contracts (Pydantic models) — implement before tools

### 2.1 KernelSessionStartRequest
Required:
- `request_id: str`
- `goal: KernelGoal` (existing)
- `budgets: KernelBudgets` (existing)
- `policy_id: str = "feature_graph_deed_to_map_v0"`

Bootstrap inputs (v0 acceptance rule):
Start is accepted iff **any** of:
1) `initial_ir_ref` provided, OR
2) `initial_graph_json` provided, OR
3) (`dossier_id` AND `source_entry_ref`) provided

Fields:
- `initial_ir_ref: Optional[str] = None`
- `initial_graph_json: Optional[dict[str, object]] = None`
- `dossier_id: Optional[str] = None`
- `source_entry_ref: Optional[dict[str, object]] = None`

If bootstrap invalid, return refusal with:
- `reason_code="bootstrap_missing_inputs"`
- `missing_inputs=[...]`
- `retryable=true`

### 2.2 KernelSessionStartResult
- `session_id: str`
- `run_id: str`
- `run_artifact_ref: str` (path or durable token)
- `tool_menu: list[str]` (string values of allowed ActionType in this build phase)
- `dashboard: KernelDashboard`
- `refusal: Optional[KernelRefusal] = None`

Important: start_session must not auto-run tools (no hydration, no retrieval, no drafting).

### 2.3 KernelStepRequest
- `session_id: str`
- `idempotency_key: str` (required)
- `action_type: ActionType`
- `inputs: dict[str, object]` (refs preferred; blobs rejected by invariants)
- `semantic_ready: Optional[bool] = None` (audit only)
- `notes: Optional[str] = None` (audit only)

### 2.4 KernelStepResult
- `session_id: str`
- `idempotency_key: str`
- `execution_state: Literal["executed","refused","deduped"]`
- `step_record: Optional[StepRecord]`
- `refusal: Optional[KernelRefusal]`
- `dashboard: KernelDashboard` (always returned)
- `terminal: Optional[TerminalOutcome]`

### 2.5 KernelRefusal (first-class refusal contract)
Fields:
- `reason_code: str`
- `missing_inputs: list[str] = []`
- `retryable: bool`
- `blocked_by_budget: bool = False`
- `blocked_by_invariant: bool = False`

Rule: refusal must not trigger other actions. No “auto-correction.”

### 2.6 KernelDashboard (“flight instruments”)
Bounded compact payload returned every step:
- `latest_refs`: `{ir, compile, judge, bundle, georef, validate, retrieval}` (ArtifactRef or None)
- `gap_summary`:
  - `gap_counts_by_kind: dict[str,int]`
  - `top_gap_kinds: list[str]` (cap N)
  - `top_reason_codes: list[str]` (cap N)
- `claimability`:
  - `claimable_ready: bool`
  - `missing_claimability: list[str]` (cap N)
- `semantic_ready: Optional[bool]` (echo only)
- `budgets_remaining`: snapshot
- `failure_classification`: `{stop_reason?: StopReason, reason_code?: str}`
- `no_progress_risk`: `{risk_score: float, basis: str}`
- `last_refusal: Optional[KernelRefusal]` (single object; no history growth)

Boundedness rules (v0):
- `top_gap_kinds`: max 10
- `top_reason_codes`: max 10
- `missing_claimability`: max 20
- any freeform string fields: max 500 chars (truncate)

---

## 3) Idempotency semantics (must be deterministic)

Store an idempotency ledger per session:
- `idempotency_key -> {request_fingerprint, step_result_ref}`

Fingerprint should cover:
- `action_type`
- normalized `inputs` (including artifact refs)
- normalized options subset (if present)

Rules:
- same key + same fingerprint: return prior result with `execution_state="deduped"`
- same key + different fingerprint: refuse deterministically
  - `reason_code="idempotency_key_payload_mismatch"`
  - `retryable=false`

---

## 4) Claimability gates (centralize in claimability.py)

Add `backend/agent_kernel/claimability.py`:
- defines gate name constants
- defines `evaluate_claimability(...) -> (claimable_ready, missing_claimability[])`

v0 gate set (strings returned to controller):
- `has_ir`
- `has_judge`
- `has_compile` (if policy requires)
- `has_georef` (if goal.requires_global_placement)
- `validation_passed` (if goal.requires_global_placement)

`DECLARE_DONE` behavior:
- accept only if `claimable_ready == True`
- otherwise refuse with `missing_claimability`

Kernel must not use `semantic_ready` in claimability logic.

---

## 5) Action menu (phased expansion to avoid dead actions)

### Phase 1 (step engine + claimability)
Required actions in ActionType/tool_menu:
- `DECLARE_DONE` (new)
- existing deterministic actions already backed by deps (as available)
- keep existing v0 actions, but enforce refusal if deps missing (stable reason codes)

### Phase 2 (context tools)
Add only when executor handlers exist + tests exist:
- `HYDRATE_DEED`
- `OPEN_ARTIFACT`

### Phase 3 (authoring tool)
Add only when interface + stub + persistence behavior exist:
- `DRAFT_IR` (LLM-backed tool boundary; controller decides when)

Do not add `RUN_PHYSICS_PASS` to kernel (controller macro only).

---

## 6) Kernel session manager behavior (implementation outline)

### start_session(request)
- Validate bootstrap acceptance rule (Section 2.1).
- Create `session_id` and `run_id`.
- Create/initialize a `RunArtifact`:
  - include initial refs if provided (IR ref or inline graph marker ref)
  - do not fabricate fake refs
- Persist run artifact (optional v0; but preferred for durability).
- Return tool_menu + dashboard snapshot (no actions executed).

### step(step_request)
Order of operations:
1) Load session/run artifact
2) Check idempotency ledger
3) Check budgets (refuse/stop if exceeded)
4) Validate request boundedness/invariants (refuse if violated)
5) Execute exactly one action through ActionExecutor
6) Append step record + update refs
7) Persist updated run artifact + update idempotency ledger
8) Compute dashboard + return StepResult

No-progress:
- compute and return `no_progress_risk` only
- do not hard stop by default (configurable per session later)

---

## 7) Tests (acceptance suite)
Add/extend tests to enforce:
- start_session bootstrap refusal (`bootstrap_missing_inputs`)
- step: execute one action, never substitute actions
- refusal contract shape stable
- idempotency: dedupe on same fingerprint; refuse on mismatch
- DECLARE_DONE: refuses with missing claimability; accepts when gates satisfied
- dashboard always returned; bounded fields enforced
- semantic_ready echoed but never influences accept/refuse logic

Verification:
- `.venv\\scripts\\activate.ps1; pytest backend/agent_kernel -q`

