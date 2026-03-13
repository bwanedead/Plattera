# agents.md

## Scope
- Folder: `backend/harness/mission_runtime/`
- Purpose: CLI harness for exercising mission-runtime modes (deed_to_ir, transcript_edit) in dev/testing.

## Contracts & invariants
- `hitl_pending_path(run_id)` is the canonical location for HITL event files. Both `cli_support.py` (writer) and `hitl_watch.py` (reader) must agree on this path.
- The HITL event file is consumed (deleted) by `hitl_watch` on read — it is a one-shot signal, not a persistent record.
- The done-sentinel file (`--done-file`) is written by `mission_runtime_cli` on completion. It is NOT deleted by hitl_watch.
- `viewer_run_id` used by the feedback store is derived from `request_prefix` via `viewer_run_id_from_request_prefix`. For prefix `mission-row1-tx`, run_id = `mission-row1-tx`.

## Allowed changes
- Safe: modify watcher/inject/cli_support logic.
- Do not change the `hitl_pending_path` filename pattern without updating both `cli_support.py` and `hitl_watch.py`.

## Commands
- Run loop (background): `python -m api.mission_runtime_cli --initial-mode transcript_edit --objective "..." --mission-id row1 --tx-source-transcript-ref <path> --tx-max-iterations 12 --done-file /tmp/done_row1.json > /tmp/result_row1.json 2>/tmp/err_row1.txt &`
- Watch (blocking): `python -m harness.mission_runtime.hitl_watch --run-id mission-row1-tx --done-file /tmp/done_row1.json --timeout 600`
- Inject feedback: `python -m harness.mission_runtime.hitl_inject --run-id mission-row1-tx --prompt-id <prompt_id> --choice "Range 75 West"`

## Gotchas
- The transcript-edit loop is NON-BLOCKING for HITL. It keeps iterating while feedback is pending. Feedback is polled at the start of each iteration via `drain_pending_feedback`.
- When the loop exhausts its budget with `waiting_feedback`, the runner automatically block-polls the feedback store (every 2s, up to 10 min). Once feedback is injected, the runner resumes the controller — the background process does NOT need to be restarted.
- Use `--tx-max-iterations 12` (not the default 4) when agent-testing so the resumed controller has enough budget to act on the injected feedback.
- The runner must NOT use stdin (`input()`). Backgrounded processes have stdin closed, causing immediate EOFError.

## Links
- **HITL behavioral intent** (read this first if behavior seems wrong): `docs/agent-testing/hitl-loop-behavioral-intent.md`
- Full agent testing guide: `docs/agent-testing/transcript-edit-loop-cli-testing.md`
- Practice deed cheat sheet: `practice_deeds/right_of_way_deed_cheatsheet.md`
- Feedback polling: `backend/agents/transcript_edit/iteration_repair_runtime.py` (~line 627)
