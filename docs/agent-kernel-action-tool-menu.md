# Agent Kernel Action/Tool Menu Reference

## Purpose
This document answers:
1. What action types exist in the kernel action universe.
2. What actions are actually available in each runtime context.
3. What can exist but is not wired in a specific loop yet (for example RAG retrieval in transcript-edit).

This is the practical menu map for operators and loop designers.

---

## 1) Action Universe (declared enum)
Action universe is defined by `ActionType` and includes:

- `set_graph_requirements`
- `hydrate_deed`
- `open_artifact`
- `open_text_spans`
- `draft_ir`
- `declare_done`
- `retrieve_evidence`
- `compile`
- `judge`
- `bundle`
- `georeference`
- `validate`
- `render`
- `propose_patch`
- `summarize_status`
- `upsert_deed_span_index`
- `tx_audit_transcript`
- `tx_open_transcript_spans`
- `tx_verify_transcript_with_image`
- `tx_save_transcript_span_seeds`
- `tx_apply_edit_plan`
- `tx_promote_transcript_for_mapping`

Source:
- `backend/agent_kernel/models.py`

---

## 2) How tool menu is computed
The runtime menu is not hardcoded in one list.

Mechanism:
1. `ActionExecutor` exposes `available_actions(allow_stubbed=False)`.
2. `KernelSessionManager.start_session` calls `_tool_menu(action_executor)`.
3. `_tool_menu` includes:
   - `declare_done` always
   - every action whose dependency interface is currently present

Important:
- If an action exists in `ActionType` but its dependency is not configured, it is absent from tool menu.
- Tool menu shown to controller reflects configured dependencies, not enum superset.

Sources:
- `backend/agent_kernel/actions.py`
- `backend/agent_kernel/session.py`

---

## 3) Runtime contexts (wired now)

### 3.1 Default kernel session manager (broad menu)
When `KernelSessionManager()` is created with defaults, dependencies include:

- corpus/deed hydration + artifact open + text spans
- draft IR proposer
- deed span index upserter
- retrieval evidence tool (includes semantic retrieval path)
- compile/judge/bundle/georeference/validate/render
- transcript-edit tools (`tx_*`)

So default context can expose both feature-graph and transcript-edit action families together.

Source:
- `KernelSessionManager.__init__` default deps in `backend/agent_kernel/session.py`

### 3.2 Transcript-edit post-T0 pipeline context (narrow menu)
In post-T0 transcript-edit path, `KernelSessionManager` is explicitly constructed with a narrowed dependency set:

- `tx_audit_transcript`
- `tx_open_transcript_spans`
- `tx_verify_transcript_with_image`
- `tx_apply_edit_plan`
- `tx_save_transcript_span_seeds`
- `tx_promote_transcript_for_mapping`

Not wired there:
- `retrieve_evidence` (RAG/deed retrieval action)
- compile/judge/bundle/georeference/validate/render
- patch/status/deed-open helpers

Sources:
- `backend/pipelines/image_to_text/pipeline.py`
- `backend/api/endpoints/transcript_edit_agent.py`

---

## 4) Availability matrix (current)
Legend:
- `Yes`: currently wired in that runtime context.
- `Potential`: action exists in kernel/action layer but not wired into that context.

### 4.1 Transcript-edit run contexts (post-T0 + transcript_edit_agent endpoint)
- `tx_audit_transcript`: Yes
- `tx_open_transcript_spans`: Yes
- `tx_verify_transcript_with_image`: Yes
- `tx_apply_edit_plan`: Yes
- `tx_save_transcript_span_seeds`: Yes
- `tx_promote_transcript_for_mapping`: Yes
- `retrieve_evidence`: Potential (not wired in tx context now)
- `open_artifact` / `open_text_spans`: Potential
- `compile` / `judge` / `bundle`: Potential
- `georeference` / `validate` / `render`: Potential
- `propose_patch` / `summarize_status`: Potential

### 4.2 Default kernel context (feature-graph/controller style)
- `retrieve_evidence`: Yes
- `compile` / `judge` / `bundle`: Yes
- `georeference` / `validate` / `render`: Yes
- `open_artifact` / `open_text_spans`: Yes
- `draft_ir`: Yes
- `upsert_deed_span_index`: Yes
- `tx_*`: Yes

---

## 5) RAG/retrieval in transcript-edit loop: current reality
Current transcript-edit orchestration does not call `retrieve_evidence` action.

What this means:
- There is no explicit retrieval step in tx iteration pipeline today.
- Dependency-style closure blockers can be represented in ledger semantics, but automated retrieval attempts are not first-class in tx flow yet.

Implication:
- If desired behavior is "agent tries RAG/deed retrieval before human escalation", wiring work is needed:
1. add `evidence_retriever` dependency in tx session manager construction
2. add explicit retrieval stage(s) in tx iteration pipeline
3. feed retrieval evidence into ledger/update + escalation policy

---

## 6) Action contracts: where to inspect required inputs
Action argument coercion and required input hints are documented in:
- `backend/agents/controller/contracts.py`

Kernel-side execution/refusal behavior is in:
- `backend/agent_kernel/actions.py`

Tool implementation logic is in:
- `backend/agent_kernel/tooling.py`

---

## 7) Practical interpretation for loop design
If you are redesigning transcript-edit loop authority toward LLM-led decisions:
- Keep deterministic actions for orchestration safety (`tx_apply_edit_plan`, hashing, validation contracts).
- Add LLM-owned decision stages as explicit actions or planner phases.
- Wire `retrieve_evidence` into tx loop only if you want automated dependency closure before HITL.

The key is to distinguish:
- action universe (possible)
- tool menu in this run context (actual)
- policy/iteration flow (what is invoked)
