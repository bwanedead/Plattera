# agents.md

## Scope
- Folder: `backend/harness/mission_runtime/`
- Purpose: generic mission-runtime shell utilities for CLI testing, trace export, and HITL file/watch helpers.

## Contracts & invariants
- `hitl_pending_path(run_id)` is the canonical location for HITL event files. Both `cli_support.py` (writer) and `hitl_watch.py` (reader) must agree on this path.
- The HITL event file is consumed (deleted) by `hitl_watch` on read — it is a one-shot signal, not a persistent record.
- The done-sentinel file (`--done-file`) is written by `mission_runtime_cli` on completion. It is NOT deleted by hitl_watch.
- `viewer_run_id` used by the feedback store is derived from `request_prefix` via `viewer_run_id_from_request_prefix`. For prefix `mission-row1-tx`, run_id = `mission-row1-tx`.

## Allowed changes
- Safe: modify watcher/inject/cli_support logic.
- Do not change the `hitl_pending_path` filename pattern without updating both `cli_support.py` and `hitl_watch.py`.

## Commands
- Run loop (background): `python -m api.mission_runtime_cli --initial-mode <mode> --objective "..." --mission-id row1 --done-file /tmp/done_row1.json > /tmp/result_row1.json 2>/tmp/err_row1.txt &`
- Watch (blocking): `python -m harness.mission_runtime.hitl_watch --run-id <run_id> --done-file /tmp/done_row1.json --timeout 600`
- Inject feedback: `python -m harness.mission_runtime.hitl_inject --loop-kind mission_runtime_cli --run-id <run_id> --prompt-id <prompt_id> --choice "<feedback>"`

## Gotchas
- Mission-runtime HITL helpers are loop-namespace agnostic. Always pass the same `--loop-kind` the producer/consumer uses in the feedback store.
- Some domain runners keep iterating while feedback is pending and may also resume automatically after feedback arrives; that behavior belongs to the domain-side bridge, not this harness folder.
- The runner must NOT use stdin (`input()`). Backgrounded processes have stdin closed, causing immediate EOFError.

## Links
- **HITL behavioral intent** (read this first if behavior seems wrong): `docs/agent-testing/hitl-loop-behavioral-intent.md`
- Full agent testing guide: `docs/agent-testing/transcript-edit-loop-cli-testing.md`
- Domain-side feedback polling: `backend/agents/`
