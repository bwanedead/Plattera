## Agent Kernel Mismatch Report — Current vs Intended Step-Driven Vision (Plattera)

### Purpose
Explain the **current mismatch** between the shipped Agent Kernel and the clarified intent/vision, in a way that prevents drift and is implementation-driving for the next alignment work.

---

## 1) Intended vision (non-negotiable intent)
Plattera’s loop has three layers:

- **Deterministic engines (“physics”)**: compile/judge/georef/validate/render are authoritative and never negotiate.
- **Kernel (“harness/flight-control + black box”)**: executes *exactly one* action the controller requests, enforces budgets/invariants, persists artifacts, returns observations. **Kernel does not plan or choose actions.**
- **Agent/controller (“strategist/author”)**: GPT‑5.2 (model-agnostic long-term) decides the next move, authors IR, interprets deterministic feedback, retrieves evidence/exemplars, asks the user when needed, and iterates.

The loop should feel like repeated cycles:
**controller chooses move → kernel executes → physics evaluates → kernel returns observations → controller chooses next move**.

---

## 2) “Done” is agent-declared, kernel-claimable (critical refinement)
- The controller is the arbiter of **semantic correctness** (“this IR reflects the deed”).
- The kernel/physics are the arbiters of **claimability** (“you may declare done only if required validators/requirements are satisfied”).

**Required tool/action:** `DECLARE_DONE`

- Controller may call `DECLARE_DONE` when it believes the goal is met.
- Kernel must accept only if claimability gates pass (required artifacts exist, required validators pass, invariants hold).
- If claimability gates are missing, kernel must **refuse deterministically** and return an explicit list of missing gates (no substitution or “helpful next step” execution).

---

## 3) What the current kernel actually does (today)
The current primary entrypoint is **run-driven/autopilot-like**:
- `backend/agent_kernel/kernel.py::KernelLoop.run()` / `run_kernel()`

It internally selects a sequence of actions (with branches), e.g. retrieval → compile → judge → bundle → georef → validate → repair.

This is useful as a deterministic harness, but it is not the intended primary interface for the agent-driven system.

---

## 4) Core mismatch (one sentence)
**The kernel currently selects the next action internally; the vision requires the controller to select the next action, with the kernel only executing exactly the requested action (or refusing/stopping deterministically).**

This is a mismatch of **sequencing authority**, not intelligence.

---

## 5) Step-driven is absolute: kernel executes / refuses / stops — never substitutes
To prevent autopilot creep:

- Kernel may **execute** the requested action.
- Kernel may **refuse** an invalid action deterministically (budget exceeded, missing refs, blob too large, invariant violation).
- Kernel may **stop** for safety stops (budget/no-progress/etc.).
- Kernel must **not substitute** a different action (“do the next logical thing”), even if it seems obvious.

Refusal must return explicit reason codes and missing inputs; not alternate execution.

---

## 6) Specific mismatch areas (implementation-relevant)

### A) Interface shape mismatch: run-driven vs session/step-driven
**Current:** one call (`run_kernel`) attempts to complete a whole run and chooses actions internally.
**Intended:** the primary kernel surface is a **session + step API**:
- `start_session(...)` → returns session/run handle + budgets + tool menu + initial observation
- `step(action_request)` → executes exactly one requested action; returns result + updated observation + persisted refs

Autopilot may remain, but should be implemented as **a controller** that repeatedly calls `step()`, not as the kernel’s primary interface.

### B) Input mismatch: kernel requires IR instead of starting from deed/dossier
**Current:** kernel expects `initial_ir_ref` or `initial_graph_json` to proceed.
**Intended:** sessions begin from **deed/dossier context** (dossier_id / source_entry_ref), and the controller decides what to do first.

Important nuance:
- The session may optionally accept an existing IR ref (resume/replay), but it must not be required as the only entry door.

### C) Tool menu mismatch: missing “draft IR” as a first-class tool
**Current:** LLM seam is primarily patch/summarize.
**Intended:** the controller must be able to create initial IR via a first-class tool:
- `DRAFT_IR` / `PROPOSE_IR` (LLM-backed, bounded, persisted)

Nuance (prevent misread):
- `DRAFT_IR` is a tool; the controller decides when to call it (not assumed step 1).

### D) Conversation ownership: user choice tool must be ledger-only
To keep kernel non-conversational:
- Prefer action/tool: `EMIT_USER_QUESTION` (writes durable “question/options/context refs” artifact)
- Terminal outcome: `NEEDS_USER_CHOICE`

The controller/UI decides when/how to present the question to the user.

### E) Tools include context acquisition, without prescribing order
Tools are a **menu**, not a pipeline. Include explicit context tools so the controller can investigate without “faking” steps:
- `HYDRATE_DEED` (deterministic)
- `RETRIEVE_EVIDENCE`
- optional `PULL_EXEMPLARS` (thin retrieval wrapper)
- optional read-only convenience `OPEN_ARTIFACT` / `LOAD_EXISTING_IR`

### F) Observations contract missing: add “flight instruments” every step
To reduce controller thrash, every `step()` should return a compact standardized observation payload, e.g.:
- latest artifact refs (ir/judge/compile/bundle/georef/validate/retrieval)
- gap summary (counts + top kinds + top reason codes)
- claimability flags (`can_declare_done`, `missing_claimability[]`)
- budget remaining snapshot
- last deterministic failure classification (worker unavailable, validation failed, needs capability, etc.)

This is stable “flight instruments,” not giant blobs.

### G) No-progress detection is a safety brake; parameterized; intent-aware
In agent-driven stepping, no-progress should be conservative:
- based on `(action_type + inputs fingerprint + resulting artifact/gap fingerprints)`, not action type alone
- thresholds configurable per session (looser early exploration, stricter later)
- should not terminate legitimate exploration within budgets

---

## 7) What is already correct / reusable (do not rewrite)
Most kernel v0 work remains valuable:
- Action execution boundary (`ActionExecutor` + dependency interfaces)
- Budgets
- No-progress primitives (need adjusted semantics for step mode)
- RunArtifact spine + persistence/index
- Stop reasons + terminal taxonomy
- Worker-unavailable classification and reason-code propagation
- CLI/tests

So the alignment work is primarily **API shape + sequencing authority shift**, not rebuilding the harness.

---

## 8) Autopilot is still useful (explicit)
Autopilot (`run_kernel`) is **not “wrong.”** It is useful as a:
- smoke test harness
- deterministic fallback runner
- regression surface

But it must be treated as a **secondary controller** (a policy that drives the step API), not the primary kernel interface for the intended system.

---

## 9) Desired end state (alignment acceptance criteria)
You’re aligned with vision when:
1) Primary kernel interface is **session + step**, not “kernel-run pipeline.”
2) Controller chooses the next action; kernel executes/refuses/stops deterministically; never substitutes actions.
3) Sessions can start from deed/dossier context; IR can be created via `DRAFT_IR` tool; IR ref optional for resume.
4) `DECLARE_DONE` exists and kernel enforces claimability gates (controller declares; kernel/physics decide claimability).
5) Every step returns compact “flight instruments” observations for stable controller behavior.

