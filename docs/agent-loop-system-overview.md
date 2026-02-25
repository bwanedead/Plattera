# Plattera Agent Loop System Overview

## Purpose
- This document gets a new engineer/agent up to speed on the **current agent loop system** at both:
  - high-level conceptual scope (what the loop is for, why it exists)
  - concrete technical scope (which modules do what, how data flows, where to edit)
- It is an onboarding companion to:
  - `docs/agent-kernel-controller-spec.md` (contract/spec detail)
  - `build clouds/agent-kernel-controller-loop-build-cloud.md` (design intent / tradeoffs)

## What This System Is Trying To Accomplish
- Core mission: **convert deed text into a FeatureGraph IR**, then drive deterministic passes until the work is semantically complete.
- Practical loop objective (local-first / serviceable path):
  - obtain canonical deed text
  - draft/update FeatureGraph IR
  - compile the IR
  - judge the IR (typed gaps/warnings)
  - repair IR based on gaps
  - bundle outputs
  - `DECLARE_DONE` when claimability + semantic justification are satisfied
- The system is intentionally split so:
  - the **LLM proposes**
  - the **controller enforces**
  - the **kernel executes + persists**
  - deterministic engines act as **physics gates**

## Mental Model (the short version)
- Think of this as a constrained strategist loop over a durable ledger.
- The LLM is not trusted as a source of truth.
- Artifacts + refs + deterministic reason codes are the truth.
- The loop should be able to recover from:
  - malformed tool calls
  - invalid IR drafts
  - unsupported operations
  - temporary parse hiccups
- The loop should not silently “autopilot” multi-step sequences.

## Architecture (Layers and Responsibilities)

## 1) Agent Kernel (one-step executor + ledger)
- Location: `backend/agent_kernel/`
- Primary API:
  - `KernelSessionManager.start_session(...)`
  - `KernelSessionManager.step(...)`
- Responsibilities:
  - execute exactly one action per call (except `DECLARE_DONE` special handling)
  - persist run artifact + step records
  - maintain latest refs / dashboard
  - enforce budgets and deterministic invariants
  - return refusals with stable reason codes
- Important properties:
  - idempotency-aware
  - refs-not-blobs
  - durable artifacts are the source of truth

## 2) Controller (LLM runtime wrapper + policy enforcement)
- Location: `backend/agents/controller/`
- Primary entrypoint:
  - `run_controller_loop(...)` in `backend/agents/controller/controller.py`
- Responsibilities:
  - build context packet (current state + bounded continuity memory)
  - call LLM adapter with provider-neutral prompts + per-action tools
  - validate proposal locally
  - enforce tool-menu gating and payload bounds
  - apply deterministic autofill (IDs/refs and a few safe scaffolds)
  - call kernel `step(...)`
  - append transcript events + emit compact “Agent Tape” updates
- Non-responsibilities (intentional):
  - does not decide a fixed action sequence
  - does not silently substitute agent intent with a different action

## 3) Provider Adapter (transport only)
- Current provider: OpenAI (`backend/agents/controller/openai_client.py`)
- Prompting is provider-agnostic and lives in:
  - `backend/agents/controller/prompting.py`
- Tool specs are provider-agnostic:
  - `backend/agents/controller/tool_specs.py`
  - `backend/agents/controller/contracts.py`
- Adapter responsibilities:
  - send developer/user messages + tool definitions
  - force one tool call
  - parse tool call output
  - return structured diagnostics on failure (`openai_next_step_error` payload fields)

## 4) Deterministic Engines (“Physics Gates”)
- FeatureGraph toolchain:
  - compile (`backend/feature_graph/compiler.py`)
  - judge (`backend/feature_graph/judge.py`)
  - bundle (`backend/feature_graph/bundle.py`)
- Retrieval engine (RAG):
  - `backend/retrieval/...`
  - controller maps retrieval intent -> deterministic query pack
- These engines are what make the loop “real”:
  - they convert guesses into typed gaps, warnings, and artifacts

## Current Runtime Flow (One Iteration)
1. Controller receives latest kernel dashboard + refs + transcript history (bounded view).
2. Controller builds a **Context Packet**:
   - inputs (dossier_id, deed refs, excerpts, fingerprints, etc.)
   - progress (latest refs, gap summary, claimability, IR health, judge excerpts)
   - memory (`run_summary_log`, span memory, recent digest-derived entries)
   - tool cheatsheet / how-to
   - recent trace + last refusal
   - inline artifact hints (safe, bounded)
   - `ir_ops_menu` (compilable op vocabulary + warnings)
3. Controller asks the model to call exactly one action tool from the provided tool list.
4. Controller parses and validates locally:
   - tool call shape
   - action in `tool_menu`
   - per-action required args
   - payload bounds (size/depth/geometry)
5. Controller optionally autofills deterministic fields (refs/IDs/justifications).
6. Controller calls kernel `step(...)`.
7. Kernel executes action (or refuses), persists artifacts/steps, returns updated dashboard.
8. Controller logs/transcripts the outcome and repeats until terminal.

## What the Agent Loop Is “Doing” in Plattera Terms
- It is a backend orchestration layer for **deed interpretation into a weight-bearing IR**, not a chat assistant.
- It should:
  - encode deed meaning into a FeatureGraph that is representable and compilable enough for the current milestone
  - use deterministic feedback to repair itself
  - preserve provenance and auditability via artifact refs + reason codes
- It should not:
  - improvise unsupported operations endlessly
  - rely on hidden chain-of-thought
  - pass giant unbounded JSON blobs around

## FeatureGraph (Adjacency System) — How It Fits
- Location: `backend/feature_graph/`
- Role:
  - universal IR for deed meaning (total representability)
  - compilation + judging provide deterministic checks and partial outputs
- Key concepts:
  - `FeatureGraph` with `nodes`, `edges`, `metadata`
  - `FeatureNode` can be one of:
    - direct `geometry`
    - `op_expr`
    - `feature_ref`
  - compiler supports a subset of operations; judge reports typed gaps for the rest

## Serviceable Compiler Path (Current State)
- Goal is not full geodesy/boolean math yet; goal is a **serviceable local path** so the loop can finish useful work.
- Supported/usable path now includes:
  - `LineStep`
  - `Close`
  - `CourseTraverse` (schematic line from course list)
  - `TiedPoint` (schematic point with warning)
  - `Collection` (semantic grouping, no geometric boolean claim)
- Implication:
  - the agent should prefer these ops (or direct geometry + annotations) until richer lowering exists.

## Retrieval / RAG (Adjacency System) — How It Fits
- Role:
  - optional evidence lookup to resolve ambiguity, anchors, terminology, dependencies
- Controller owns deterministic routing:
  - model proposes intent + query
  - controller maps to query pack/lanes/filters
- Degradation is deterministic:
  - semantic worker issues are mapped to stable reason codes
  - controller can degrade or ask for another move
- Retrieval is not the canonical deed source:
  - canonical deed is the deed text artifact / finalized corpus view

## Deed Access, Span Bookmarks, and Verification Loops
- Canonical deed source is a deed text artifact ref (dossier-backed and persisted).
- Verbatim deed recall path:
  - `OPEN_TEXT_SPANS` (bounded verbatim text)
- Bookmarking path:
  - `UPSERT_DEED_SPAN_INDEX`
  - store `span_id`, labels, ranges, fingerprint, intent
- Verification loop:
  - capture/open span -> inspect exact text -> confirm/adjust
- This reduces full-deed reloading and improves repeatable source verification.

## Persistence and Artifacts (What Gets Written, Where)

## Artifact philosophy
- Refs-not-blobs:
  - steps pass refs whenever possible
  - large payloads are persisted first
- Artifacts are the durable truth across runs/restarts.

## Key artifact families
- Agent kernel/controller artifacts:
  - under `config.paths.agent_kernel_artifacts_root()`
  - run artifacts, transcripts, rejected payloads, deed span indexes, tool outputs, summaries
- FeatureGraph artifacts:
  - under `config.paths.dossiers_feature_graphs_artifacts_root()`
  - IR, compile, judge, bundle artifacts + latest/final pointers
- Dossier finalized views:
  - under `config.paths.dossiers_views_root()`
  - finalized deed snapshots (`dossier_final.json`)

## Pointer semantics (important)
- Working/latest pointers (mutable):
  - `latest_ir.json`, `latest_compile.json`, `latest_judge.json`, `latest_bundle.json`
- Final pointers (immutable intent):
  - `final_ir.json`, optional `final_bundle.json`
- Kernel latest refs dashboard reflects current working truth.

## Controller Context Packet (Why It Exists)
- The loop does not rely on rolling raw chat history.
- Instead it constructs a bounded, structured packet each iteration with:
  - current inputs and refs
  - deterministic progress signals
  - repair hints
  - continuity memory (`run_summary_log`)
  - tool cheatsheet and examples
  - inline artifact hints (safe excerpts)
  - ops menu (`ir_ops_menu`)
- This gives continuity while keeping token growth bounded and predictable.

## Memory / Continuity (Current Mechanism)
- Single-pipe memory (no second summarizer model in runtime):
  - model may emit optional `iteration_summary` (Memory Docket v0)
  - controller treats it as untrusted (Pattern A)
  - controller normalizes/bounds it into a consistent docket shape
  - controller appends to a byte-bounded `memory.run_summary_log`
- Deterministic fallback summary exists when the model omits/mangles the summary.
- Summary memory is continuity-only:
  - not used for kernel inputs
  - not used for idempotency
  - canonical truth remains artifacts + refs + reason codes

## How the System Avoids Common Failure Modes (Current Hardening)
- Empty args thrash:
  - per-action tool schemas (mechanical required fields)
  - refusal repair sub-loop (1 attempt)
  - deterministic autofill for IDs/refs
- Parse-fail blindness:
  - `controller_parse_failed` includes bounded diagnostics (`structured_data_keys`, excerpts, tool info)
  - deterministic parse-fail resync step can inspect latest judge/compile/ir artifact
- Inspection churn:
  - repeated `OPEN_ARTIFACT` on same ref triggers a controller brake (`repeated_inspection_no_progress`)
- Stale physics refs after IR update:
  - kernel invalidates compile/judge/bundle refs when `DRAFT_IR` updates the IR ref
- Unsupported op thrash:
  - `repair_view.top_gaps[]` includes deterministic `suggested_replacement_ops` + `rewrite_hint`
  - controller now exposes richer judge excerpts + ops menu
- `DECLARE_DONE` parse-fail trap:
  - controller no longer fails proposal parse if `declare_done` payload is missing
  - can autofill minimal `declare_done` justification from latest refs
  - otherwise routes through normal refusal path

## Observability / How To Watch A Run

## Canonical runtime record
- Controller transcript artifact (bounded event stream)
- Kernel run artifact + step records

## Operator-friendly live status (Agent Tape)
- Backend emits compact `agent_tape_update` events over SSE:
  - stage, phase, iteration, action, line1/line2 status blurbs
- Polling snapshot also exposes:
  - `live_status`
  - `last_agent_tape_event`
- Frontend mini widget (Text→Schema, Agent Loop mode) displays:
  - current status
  - recent activity feed
  - SSE/polling state

## What to inspect first when a run stalls
- `controller_parse_failed` transcript/log payloads
- latest `judge_ref` / `compile_ref` repair views
- `progress.latest_refs` freshness (did IR change without recompile/rejudge?)
- `tool_menu` vs proposed action
- repeated inspection brake events / refusal streaks

## Key Modules and Where To Edit (Practical Map)

## Controller loop + policy
- `backend/agents/controller/controller.py`
  - loop control, context packet, refusals, autofill, brakes, memory, logging

## Prompting (provider-agnostic)
- `backend/agents/controller/prompting.py`
  - mission text, protocol text, repair prompts

## Proposal contracts + tool guidance
- `backend/agents/controller/contracts.py`
  - proposal model, per-action arg validators, tool cheatsheet/how-to, examples

## Provider adapter
- `backend/agents/controller/openai_client.py`
  - tool-call transport/parsing + error extraction

## Kernel session semantics
- `backend/agent_kernel/session.py`
  - step execution, latest refs, claimability, terminal handling, persistence wiring

## Concrete tool behavior (kernel deps)
- `backend/agent_kernel/tooling.py`
  - deed open/hydrate, span tools, IR draft proposer, compile/judge/bundle wrappers, repair views

## FeatureGraph capability surface
- `backend/feature_graph/operations.py`
  - registry + `supported` truth
- `backend/feature_graph/compiler.py`
  - what actually compiles
- `backend/feature_graph/judge.py`
  - deterministic gaps/warnings

## API + SSE integration
- `backend/api/endpoints/agent_loop.py`
  - run start/poll/open endpoints and event streaming formatting

## Frontend status + launch surface
- `frontend/src/components/TextToSchemaWorkspace.tsx`
- `frontend/src/components/text-to-schema/TextToSchemaControlPanel.tsx`
- `frontend/src/services/agentLoopApi.ts`

## How To Think About “Done” (Current Practical Standard)
- “Done” is two-part:
  - **Kernel claimability**: deterministic prerequisites exist (refs/gates)
  - **Agent semantic decision**: justification says the outputs are semantically acceptable for the goal
- The loop is working well when:
  - it reaches `draft_ir -> compile -> judge -> repair -> ... -> bundle -> declare_done`
  - failures become actionable refusals or gap-driven rewrites (not silent stalls)

## Known Limits / Expected Future Work
- Serviceable compiler path is still intentionally partial.
  - more surface ops and lowering will continue to be added (e.g., richer traverse variants)
- Global placement / georef/validate is not the primary local-path focus yet.
- Some controller heuristics (cadence shaping, thrash brakes) are intentionally soft and may evolve.

## Recommended First Read Order For New Agents
1. `docs/agent-loop-system-overview.md` (this file)
2. `docs/agent-kernel-controller-spec.md`
3. `backend/agents/controller/agents.md`
4. `backend/agent_kernel/session.py`
5. `backend/agents/controller/controller.py`
6. `backend/agent_kernel/tooling.py`
7. `backend/feature_graph/operations.py`
8. `backend/feature_graph/compiler.py`
9. `backend/feature_graph/judge.py`

## Quick Operational Checklist (When Making Changes)
- Preserve:
  - kernel = one-step executor
  - controller = enforcer, not autopilot
  - refs-not-blobs
  - stable reason codes / bounded diagnostics
- Add tests next to the module you touch.
- Prefer deterministic feedback over hidden heuristics.
- If adding a new op:
  - update `operations.py`
  - implement compiler behavior (or mark unsupported)
  - ensure judge behavior is coherent
  - add repair hints if unsupported
  - update controller guidance/ops menu expectations if needed
