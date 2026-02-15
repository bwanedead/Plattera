# PRD: Agent Kernel v0 (deterministic run harness)

## Context
We need a domain-agnostic, deterministic kernel that orchestrates runs above probabilistic cognition. It must persist durable artifacts, surface typed gaps via deterministic judges, and provide explicit state-machine driven behavior. Domain policy (FeatureGraphDeedToMapPolicy v0) lives outside the kernel.

## Goal
Deliver a library-first Agent Kernel v0 that can run a deterministic loop over IR/compile/judge/retrieve/patch actions with budgets, explicit states, and durable run artifacts.

## Non-goals
- Building domain semantics for deed meaning or mapping.
- UI integration or frontend changes.
- Implementing new retrieval lanes or evidence stores.
- Converting this into a production API endpoint in this leg.

## Users / Use cases
- As an engineer, I can call the kernel as a Python library and get a RunArtifact with refs to durable artifacts.
- As a policy author, I can provide routing and gap handling rules without modifying kernel mechanics.
- As an operator, I can see deterministic stop reasons and convergence decisions.

## Scope
- Backend library module for kernel models, state machine, and execution loop (lives under `backend/agent_kernel/`).
- Persistence for RunArtifact and step records (refs, not blobs).
- Policy interface and a minimal FeatureGraphDeedToMapPolicy v0 scaffold.
- CLI entry for deterministic local tests (optional, minimal).

## Constraints / invariants
- Kernel is deterministic orchestration above probabilistic cognition.
- Persistence is truth: run state and artifact refs are durable.
- Evidence-first retrieval: store EvidenceCard/Span refs from retrieval artifacts.
- Explicit state machine; no ad-hoc flow.
- Typed gaps and deterministic judges; no silent failure.
- Compile and Judge are separate truth streams.
- Library-first: core is Python module, not API.

## Success criteria
- KernelRequest/KernelResult models exist with budgets and goal flags.
- RunArtifact persists refs to IR/compile/judge/bundle/retrieval artifacts.
- Deterministic state machine advances through INIT -> DONE with explicit stop reasons.
- Kernel enforces budgets and no-progress detection deterministically.
- Policy interface exists with routing order and gap scoring hooks.

## Edge cases
- Missing anchor when global placement is required (typed gap routing).
- No progress across repair iterations (stop_reason = no_progress).
- Retrieval failures with stable reason codes.
- Judge/compile order variations (both must be supported).

## Implementation notes (optional)
- Reuse existing artifact persistence patterns in `backend/services`.
- Use retrieval run artifact path + card/span indices for evidence refs.
- Do not create a new evidence database in v0.
