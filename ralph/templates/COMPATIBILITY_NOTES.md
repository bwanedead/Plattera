# Compatibility Notes (Prep Agent Must Follow)

A run must be compatible with:
- Claude Code ralph-loop plugin
- Completion promise tag: `<promise>...</promise>`
- Max iterations may stop early: design stories so each is small and ordered.

Therefore:
- Run folder must include `run.json`, `control.json`, `events.ndjson`, and `orchestration.json` so ralph-engine can list and schedule the run.
- Project must include `ralph/config.json` for harness drivers (claude_code, codex_cli, shell). It must define `driver.name`, `driver.worker_cmd`, and `driver.reviewer_cmd`.
- The engine writes `worker_summary.md` from worker stdout and `review_result.json` from reviewer stdout when the CLI doesn't write those files itself.
- Use a CLI command that prints to stdout; only `{task_file}` is required in the command.
- If your CLI does not accept a prompt file path, wrap a shell that reads `{task_file}` and forwards the contents (e.g., PowerShell on Windows, bash on macOS/Linux).
- Windows: use `.cmd` shims (e.g., `claude.cmd`, `codex.cmd`) because extensionless shims can fail under `subprocess` with `shell=False`. macOS/Linux: use the extensionless command.
- Orchestration defaults live in `ralph/config.json` under `orchestration.scheme` (default `W5R`).
- Worker may signal completion by writing `output/worker_result.json` with `{ "complete": true, "reason": "worker_done" }`, which triggers a final reviewer.
- Reviewer task envelopes include `review_mode` (`periodic`, `adhoc`, or `final`).
- `run.json` must include UTC ISO 8601 timestamps.
- Use atomic writes for JSON outputs.
- Run ids must not contain `/` or `\`.
- `PROMPT.md` must instruct selection by `"passes": false`.
- `prd.json` must contain `passes` booleans.
- Acceptance criteria must be testable without human judgment.
- `progress.md` must exist for short-term memory.
- Run folder must be fully self-contained and referenced by prompt.
