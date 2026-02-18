## Plattera Agent Kernel — Controller Loop Build Cloud (step-driven)

### Purpose
This “build cloud” describes the **Controller/Agent Loop** that sits *above* the step-driven kernel:
- The **LLM** is the strategist (proposes the next move).
- The **Controller** is a thin runtime wrapper (validates, enforces invariants, calls tools).
- The **Kernel** is a dumb step executor + ledger (`start_session` / `step`).
- Deterministic engines (Feature Graph compile/judge/bundle, georef/validate, RAG retrieval) are “physics gates.”

This document is intentionally **design-forward** (why / shape / sharp edges). The companion “spec” doc locks the exact contracts.

---

## Core principle: preserve agency without babysitting

**The Controller must not become an autopilot.**

Allowed Controller responsibilities:
- Validate step proposals (shape, bounds, tool exists, budget, idempotency key).
- Normalize / canonicalize inputs (refs-not-blobs, bounded strings).
- Map high-level intents to safe deterministic “query packs.”
- Persist artifacts and return refs.
- Enforce **preconditions** and **claimability gates** via refusal (never substitution).

Disallowed Controller responsibilities:
- Deciding the “correct” next action (“now you must compile”).
- Running multi-step sequences automatically inside one call.
- Quietly changing agent intent.

Practical translation:
- The agent proposes `KernelStepRequest`.
- The controller either **submits it** to kernel, or **refuses** with a stable reason code.

---

## The generic loop pattern (OODA/ReAct with verification gates)

The controller loop runs a cycle:
- **Observe**: latest dashboard + tool_menu + last step record + artifact refs.
- **Orient**: update a minimal plan (bounded) + detect phase and missing gates.
- **Decide**: agent proposes exactly one next action + inputs.
- **Act**: controller validates and calls kernel `step`.
- **Verify**: verification is enforced as *gates* (freshness/claimability), not as a scripted sequence.

Key rule:
- “Creative/meaning-changing” actions (draft/patch) must be followed by physics-gate artifacts (compile/judge, and optionally validate) **before** `DECLARE_DONE` is accepted.

This is enforced as:
- **claimability/freshness requirements** on `DECLARE_DONE`, and/or
- controller refusal of `DECLARE_DONE` with `missing_claimability` / `stale_artifacts` lists.

---

## Controller phases (conceptual)

These are not kernel states; they’re controller “orientation” categories.

1) **Bootstrap**
- Ensure we have deed text or initial IR graph.
- If missing, ask user/upload (or refuse with `needs_upload`).

2) **Draft IR**
- Agent produces a Feature Graph IR candidate (bounded, representable).
- Persist as IR artifact ref.

3) **Physics pass (local)**
- Compile + judge to produce deterministic gaps.

4) **Repair**
- Use gaps to drive targeted patches to IR (or ask user questions / retrieval).

5) **Physics pass (global)**
- Bundle + georef + validate if global placement required.

6) **Declare done**
- Agent initiates `DECLARE_DONE` with evidence-bound justification.
- Kernel accepts only if deterministic gates are satisfied.

---

## Retrieval design: intent vs mechanics

Do not let the agent micromanage lane/pool knobs every time; it leads to fragile behavior.

Instead:
- Agent outputs `retrieval_intent` (high-level).
- Controller maps intent → deterministic query pack (lanes + pool + filters + limits).

Example intents:
- `ANCHOR_HUNT`: find POB/anchor hints, PLSS corner ties, monuments.
- `DEPENDENCY_HUNT`: find referenced deed/dossier/section descriptions.
- `EXEMPLAR_LOOKUP`: find similar previously-solved graphs for pattern reuse.
- `TERMINOLOGY_CHECK`: clarify meaning of ambiguous legal phrases.
- `GENERAL`: catch-all.

Query-pack mapping is deterministic and repo-aware (views/pools):
- `ANCHOR_HUNT` → hybrid_semantic + FINAL_SEGMENTS + view=final_segments (if available)
- `EXEMPLAR_LOOKUP` → semantic + EVERYTHING + filter artifact_type=feature_graph_bundle (later)
- If semantic worker unavailable → degrade to lexical with explicit reason code surfaced to agent.

---

## Done is agent-initiated but evidence-bound

`DECLARE_DONE` should be “agent chooses when to try,” but not “vibes-only.”

The agent must provide structured justification:
- Which artifacts it is relying on (compile/judge/georef/validate/render refs).
- Which deed spans/evidence support each major decision.
- Any deviations/approximations accepted, with typed reasons.

This is critical for:
- auditability
- regression evaluation
- preventing premature completion

---

## Context compression as a tool

Long-horizon loops need explicit context management to avoid silent summarization.

Add a controller-accessible action like:
- `SUMMARIZE_STATUS` (already exists in ActionType) or a new `COMPRESS_CONTEXT`

Output should be a small persisted artifact (or bounded inline summary) containing:
- current objective
- current plan (short)
- current gaps summary
- current refs
- next 3 candidate moves

---

## No-progress detection: “semantic thrash” not “same action twice”

No-progress should key off:
- action type + normalized inputs
- AND resulting artifact digests / gap signature

Example: multiple retrieval attempts with different queries is fine.
Repeated identical retrieval with no state change should raise risk.

Return a risk signal; do not hard-stop by default.

---

## Controller deliverables (next build)

Minimum viable controller (MVC):
- One loop that can:
  - start session
  - hydrate/open deed text
  - ask LLM for a `next_step` JSON object
  - validate + submit step
  - persist LLM outputs (IR drafts, patch proposals, summaries)
  - iterate until `DECLARE_DONE` accepted or kernel terminal stop

Instrumentation:
- Persist a controller transcript artifact (bounded).
- Record token usage + model choices + step latency.

---

## Open questions (deliberate)
- Freshness semantics: do we require “compile/judge after last IR mutation” by hash comparison, or by explicit “stale flags” on refs?
- Render: do we add a deterministic render artifact gate to claimability (`goal.render_required`)?
- Multi-agent critique: do we add critic/judge roles only on stuck/no-progress, not by default?

