# Run-centric persistence (Phase 20)

## Mental model

- **Logical run** — what operators and tests name in APIs (`tx-agent-{run_id}` prefix in transcript-edit orchestration). Owns HITL, terminal outcome, and run-feed rows.
- **Kernel session** — internal execution window: new `start_session` ⇒ new `RunArtifact` and idempotency ledger. Resume that starts a **new** session still belongs to the **same** logical run if the API reuses the same run id / registry entry.

## Fresh tests vs resume

- **Fresh run:** new logical id ⇒ new `request_id_prefix` in the domain pack ⇒ no shared idempotency with prior runs. Each `start_session` gets a new persisted artifact.
- **Resume:** same registry `run_id` / same `tx-agent-{uuid}` prefix; run feed **updates** the existing recent-runs row (dedupe by logical `run_id`), not a second row.

## Where to look

- Run feed + diagnostics: `backend/agents/transcript_edit/run_feed_persistence.py`
- API wiring: `backend/api/endpoints/transcript_edit_agent.py`
- Kernel idempotency: `KernelSessionManager.step` + `RunArtifact.idempotency_ledger`
