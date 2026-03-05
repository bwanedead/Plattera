# Transcript-Edit Loop Refactor Progress (Session Report)

Date: March 4, 2026
Scope: Re-architecture toward semantic startup orientation + deterministic control plane
Audience: External planning/review agent without repository access

## 1) Executive Summary
This session implemented the core architecture shift requested in the March 2026 brief:

- Added a new first-class kernel action `tx_orient_and_baseline` for startup semantic orientation.
- Removed authoritative pre-LLM regex disagreement heuristics from the decision path.
- Removed non-essential `orient` startup theater event.
- Kept the deterministic state-machine control plane and decision-ledger gatekeeping.
- Enforced backend-authoritative HITL prompting (frontend synthetic fallback removed).
- Preserved T0 handoff gate, terminal summary contract, and existing `tx_*` action invariants.

The loop now computes startup semantic baseline via one typed LLM action, then commits it deterministically into the decision ledger before branch decisions.

## 2) Before vs After

Before:
- Startup semantics came from deterministic disagreement hint extraction + conflict-map heuristics.
- `orient` emitted narrative checklist before substantive semantic baseline.
- Frontend could synthesize actionable closure prompts.
- HITL prompt targeting focused on disagreement-hint range flow.

After:
- Startup semantics come from `tx_orient_and_baseline` (text-only LLM) with typed output.
- `orient` phase removed from active path.
- Ledger baseline committed via deterministic coercion/validation code.
- HITL prompt builder is ledger-driven (highest-priority unresolved mapping-blocking decision).
- Frontend only renders backend-emitted actionable prompts (`human_feedback_needed`).

## 3) Core Architectural Changes Implemented

### 3.1 New Kernel Action: `tx_orient_and_baseline`
Added across kernel stack:

- Action enum and dashboard ref model:
  - `backend/agent_kernel/models.py`
- Action protocol/dependency wiring/execution:
  - `backend/agent_kernel/actions.py`
- Session default dependency wiring + latest refs propagation:
  - `backend/agent_kernel/session.py`
- Run artifact storage pointer:
  - `backend/agent_kernel/run_artifact.py`

New ref key:
- `tx_orient_baseline_ref`

### 3.2 New Tool Implementation
Implemented `TranscriptOrientBaselineTool` in:
- `backend/agent_kernel/tooling.py`

Behavior:
- Accepts source transcript ref/text and optional candidate texts.
- Calls model with strict JSON output contract (no planning/apply authority).
- Retries with deterministic repair prompt on invalid JSON.
- Persists raw model output artifact for debugging.
- Coerces/validates normalized orient items.
- Persists span-seed artifact from orient output.
- Persists orient baseline artifact and returns:
  - `tx_orient_items`
  - `tx_orient_summary`
  - `tx_span_seeds_ref`
  - source ref/hash

Failure mode:
- If repair attempts fail, returns deterministic refusal (`tx_orient_baseline_invalid_output`) with raw output artifact reference preserved.

### 3.3 Startup Flow Rewire (Controller)
Updated `backend/agents/transcript_edit/controller.py`:

New startup sequence:
1. preflight countdown
2. starting event
3. deterministic canonical audit (advisory)
4. `tx_orient_and_baseline`
5. deterministic ledger commit from orient output
6. emit startup `investigation_baseline_result`
7. enter iteration loop

Removed:
- `orient_payload` emission
- startup authoritative dependence on disagreement hints

### 3.4 Ledger Commit Path for Orient Output
Updated `backend/agents/transcript_edit/decision_ledger.py`:

- Added `update_ledger_from_orient_baseline(...)`.
- Added orient-aware item fields:
  - `layer_tag`
  - `operational_impact`
  - `provenance`
  - `verification_required`
- Ensured closure requirements are preserved/normalized and remain deterministic.
- Stopped using `disagreement_hints` as authoritative update input in `update_ledger_from_iteration`.

### 3.5 Repair Path / Waterfall Adjustments
Updated `backend/agents/transcript_edit/iteration_pipeline.py`:

- Conflict map now derives from ledger state, not disagreement-hint buckets.
- Deterministic consensus shortcut plan path removed from active decision path.
- Planner receives empty `candidate_disagreement_hints` context (non-authoritative).
- HITL prompt generation now uses `decision_ledger` closure requirements.
- Baseline-result -> HITL ordering preserved.

### 3.6 HITL Prompting Changes
Updated `backend/agents/transcript_edit/hitl_feedback.py`:

- `build_human_feedback_prompt(...)` now consumes `decision_ledger`.
- Chooses highest-priority unresolved mapping-blocking decision key.
- Prompt id format generalized to:
  - `hitl_<decision_key>_<iteration>_<suffix>`
- Uses closure requirement fields for prompt text/options.

### 3.7 Image Verification Input Discipline
Updated `backend/agents/transcript_edit/image_verification.py`:

- Removed disagreement-hint-derived checks from authoritative image verify flow.
- Image verification now driven by findings-focused checks and explicit calls.

### 3.8 Viewer Prompt Authority
Updated `frontend/src/components/agent-viewer/hooks/useAgentViewerFeedback.ts`:

- Removed synthetic closure prompt derivation (`closure_req_*`) from active prompt selection.
- Active actionable prompt now comes only from backend `human_feedback_needed` events.

## 4) Docs Updated

Updated:
- `docs/transcript-edit-loop-orchestration.md`

Changes include:
- Startup sequence now includes `tx_orient_and_baseline`.
- Kernel action list includes `TX_ORIENT_AND_BASELINE`.
- Phase catalog no longer lists `orient`.
- Section 20 updated to reflect synthetic frontend prompt removal.
- Pseudocode updated to orient-baseline commit model.

## 5) Test and Build Validation

Executed in this session:

- `pytest backend/agent_kernel -q` -> passed
- `pytest backend/agents/transcript_edit -q` -> passed
- `npm --prefix frontend run build` -> passed

Targeted suites updated:
- `backend/agent_kernel/test_actions.py`
- `backend/agent_kernel/test_session.py`
- `backend/agents/transcript_edit/test_controller.py`
- `backend/agents/transcript_edit/test_decision_ledger.py`
- `backend/agents/transcript_edit/test_run_reporting.py`

## 6) Explicitly Preserved Invariants

- T0 -> tx handoff gate remains unchanged.
- Deterministic branch/terminal gate decisions remain ledger-driven.
- Existing tx action family retained; one new action added.
- HITL still emitted only after `investigation_baseline_result`.
- Terminal recap contract remains compatible (`status`, `reason_code`, `mapping_ready`, unresolved closure requirements, layer statuses).
- Artifact-centric continuity preserved (refs and persisted payloads).

## 7) What Was Intentionally Scrapped

- `orient` startup phase as actionable signal.
- Authoritative regex disagreement extraction from decision path.
- Deterministic disagreement conflict-map authority from startup semantics.
- Deterministic consensus shortcut planning from disagreement hints.
- Frontend synthetic actionable prompt fallback.

## 8) Current Known Gaps / Follow-Up Targets

1. Dependency retrieval stage is still not wired in tx runtime (`retrieve_evidence` remains future insertion).
2. Retrieval attempt count is currently `0` placeholder in HITL evidence counters until retrieval stage is added.

## 9) Review Questions for Planning Agent

1. Should `tx_orient_and_baseline` output contract be promoted into a dedicated formal schema doc with versioning (`v1`) and compatibility rules?
2. Should we add explicit evidence-attempt counters into `human_feedback_needed` payloads to prove machine-first effort per escalation?
3. Should we add per-decision closure timeline history (attempts/outcomes) into terminal summary for operator auditability?
4. Should optional layer-4 unresolved items be separated into a dedicated terminal field for cleaner mapping-readiness interpretation?

## 10) File-Level Change List (Session)

- `backend/agent_kernel/actions.py`
- `backend/agent_kernel/models.py`
- `backend/agent_kernel/run_artifact.py`
- `backend/agent_kernel/session.py`
- `backend/agent_kernel/tooling.py`
- `backend/agent_kernel/test_actions.py`
- `backend/agent_kernel/test_session.py`
- `backend/agents/transcript_edit/controller.py`
- `backend/agents/transcript_edit/decision_ledger.py`
- `backend/agents/transcript_edit/hitl_feedback.py`
- `backend/agents/transcript_edit/image_verification.py`
- `backend/agents/transcript_edit/iteration_pipeline.py`
- `backend/agents/transcript_edit/run_reporting.py`
- `backend/agents/transcript_edit/test_controller.py`
- `backend/agents/transcript_edit/test_decision_ledger.py`
- `backend/agents/transcript_edit/test_run_reporting.py`
- `frontend/src/components/agent-viewer/hooks/useAgentViewerFeedback.ts`
- `docs/transcript-edit-loop-orchestration.md`

## 11) Additive Hardening Completed (post-review pass)

Completed from planning review recommendations:

1. Added dedicated orient schema doc:
- `docs/tx_orient_and_baseline_schema_v1.md`

2. Added evidence-attempt counters in authoritative HITL payload:
- `human_feedback_needed` now includes:
  - `evidence_attempts.open_spans_count`
  - `evidence_attempts.image_verify_count`
  - `evidence_attempts.retrieval_count`

3. Added closure timeline in terminal payload:
- `closure_history[]` (per-decision event timelines with timestamp/action/outcome/evidence_ref)
- `decision_ledger.items[].closure_history[]`

4. Added optional unresolved separation in terminal payload:
- `unresolved_optional_items[]` (parallel to `unresolved_closure_requirements`)
