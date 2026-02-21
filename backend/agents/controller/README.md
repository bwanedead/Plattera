# Controller Loop (Step-Driven Kernel)

## What this is
- Thin controller runtime over `KernelSessionManager.start_session()` + `step()`.
- LLM proposes one `kernel_step` tool call at a time; kernel remains one-action executor.
- Persists bounded controller transcripts as artifact refs.

## Main modules
- `contracts.py`: minimal proposal contract + local per-action validators.
- `controller.py`: loop runtime, refusal handling, transcript boundedness.
- `openai_client.py`: OpenAI tool-calling adapter with `json_object` fallback.
- `retrieval_intents.py`: deterministic intent -> query-pack + degradation mapping.
- `cli.py`: backend hello-loop runner.

## Commands
- Controller tests: `.venv\scripts\activate.ps1; pytest backend/agents/controller -q`
- CLI run (from `backend/`):
  `..\.venv\scripts\activate.ps1; python -m agents.controller.cli --dossier-id <ID> --model gpt-5-mini`

## Invariants
- No controller autopilot sequences inside one step.
- Kernel refusal payload is passed through unchanged.
- `semantic_ready` is audit-only.
- Refs-not-blobs + bounded transcripts enforced.
