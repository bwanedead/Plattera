# `backend/agents/`

Agent loops live here.

Agents should be **composition code** that orchestrates:

- `backend/corpus/` for corpus views/hydration
- `backend/retrieval/` for evidence retrieval + formatting
- `backend/services/llm/` for model calls
- `backend/pipelines/` for deterministic compilation/judging

Agents **must not** be imported by pipelines. Pipelines remain deterministic and independent.


