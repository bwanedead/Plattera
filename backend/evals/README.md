# `backend/evals/`

Home for evaluation + telemetry hooks so they don’t get scattered across services/agents.

v0 intent:

- record retrieval events (query, filters, lane, result counts)
- record schema attempts + compile outcomes (success/partial/fail, diagnostics)
- support curated regression datasets later


