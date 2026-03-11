# Controller Loop (Step-Driven Kernel)

## What this is
- Thin controller runtime over `KernelSessionManager.start_session()` + `step()`.
- LLM proposes one tool call per iteration from the controller-provided action tool list; kernel remains one-action executor.
- Persists bounded controller transcripts as artifact refs.

## Main modules
- `contracts.py`: minimal proposal contract + local per-action validators.
- `controller.py`: stable public facade (`run_controller_loop`, `ControllerLoopError`, `ControllerRunResult`, transcript hook seam).
- `controller_runtime.py`: runtime public surface/types and coordinator entry into loop impl.
- `controller_runtime_loop.py`: main controller loop sequencing and terminal branching.
- `controller_runtime_step_prep.py`: proposal sanitization/autofill/validation + guard checks before kernel step.
- `controller_bootstrap.py`: bootstrap context + deed/span-seed bootstrap helpers.
- `controller_context.py`: context packet assembly, recent-trace extraction, inline artifact hints.
- `controller_proposals.py`: next-step/refusal-repair proposal calls and coercion.
- `controller_summary.py`: digest/run-summary/docket shaping and no-progress terminal result helpers.
- `controller_transcript.py`: bounded transcript append, display-delta synthesis/dedupe, transcript persistence.
- `controller_guardrails.py`: idempotency/refusal streak helpers, parse-resync, and thrash/quality gate checks.
- `openai_client.py`: OpenAI tool-calling adapter with `json_object` fallback.
- `retrieval_intents.py`: deterministic intent -> query-pack + degradation mapping.
- `cli.py`: backend hello-loop runner.

## Commands
- Controller tests: `.venv\scripts\activate.ps1; pytest backend/agents/controller -q`
- CLI run (from `backend/`):
  `..\.venv\scripts\activate.ps1; python -m agents.controller.cli --dossier-id <ID> --model gpt-5-mini`
- UI-parity agent-loop CLI (from `backend/`):
  `..\.venv\scripts\activate.ps1; python -m api.agent_loop_cli --dossier-id <ID>`
  or `..\.venv\scripts\activate.ps1; python -m api.agent_loop_cli --text-file <path-to-deed.txt>`

## Invariants
- No controller autopilot sequences inside one step.
- Kernel refusal payload is passed through unchanged.
- `semantic_ready` is audit-only.
- Refs-not-blobs + bounded transcripts enforced.
