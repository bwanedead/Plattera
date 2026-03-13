# Transcript Edit Loop — CLI Agent Testing Guide

## Purpose

This document describes how to run and test the transcript-edit agent loop from the CLI,
specifically in agent-mode (non-interactive) where an AI agent acts as both the test driver
and the HITL feedback provider.

The pattern: run loop in background → watch for HITL/done → inject feedback → re-watch → repeat.

---

## Core Components

| Tool | Module | Purpose |
|------|--------|---------|
| `mission_runtime_cli` | `backend/api/mission_runtime_cli.py` | Run the loop (background process) |
| `hitl_watch` | `backend/harness/mission_runtime/hitl_watch.py` | Block until HITL arrives or loop finishes |
| `hitl_inject` | `backend/harness/mission_runtime/hitl_inject.py` | Inject feedback into the feedback store |

---

## Step-by-Step Pattern

### 1. Start the loop (background)

```bash
# From repo root, venv active
cd backend

python -m api.mission_runtime_cli \
  --initial-mode transcript_edit \
  --objective "transcript_edit_agent_loop_test" \
  --mission-id row1 \
  --tx-source-transcript-ref "C:/path/to/transcript.json" \
  --tx-max-iterations 12 \
  --done-file /tmp/done_row1.json \
  > /tmp/result_row1.json 2>/tmp/err_row1.txt &
```

Key args:
- `--mission-id row1` → predictable run_id: `mission-row1-tx` (used by watch/inject)
- `--tx-max-iterations 12` → enough iterations for mid-run feedback injection to land
- `--done-file /tmp/done_row1.json` → sentinel written when loop completes
- stdout → result file (JSON); stderr → error log

### 2. Block waiting for HITL or done

```bash
python -m harness.mission_runtime.hitl_watch \
  --run-id mission-row1-tx \
  --done-file /tmp/done_row1.json \
  --timeout 600
```

Exits immediately and prints **one JSON line**:

```json
// HITL arrived:
{"event": "hitl", "run_id": "mission-row1-tx", "prompt_id": "hitl_range_3_217f6ebf",
 "message": "Range conflict: Section 2 says 75, Sections 3-4 say 74. Which is correct?",
 "choices": ["Range 74 West", "Range 75 West"], "context": {...}}

// Loop finished:
{"event": "loop_done", "status": "waiting_human", "terminal": true, "reason_code": "tx_agent_waiting_feedback"}

// Timed out:
{"event": "timeout", "timeout_seconds": 600}
```

### 3a. If `event == "hitl"`: inject feedback, then re-watch

```bash
# Inject your choice — the runner is internally polling the feedback store right now
python -m harness.mission_runtime.hitl_inject \
  --run-id mission-row1-tx \
  --prompt-id hitl_range_3_217f6ebf \
  --choice "Range 75 West"

# Go back to blocking wait — the runner will pick up feedback, resume the controller,
# and either complete or emit another HITL event if more decisions are needed
python -m harness.mission_runtime.hitl_watch \
  --run-id mission-row1-tx \
  --done-file /tmp/done_row1.json \
  --timeout 600
```

Repeat until `event == "loop_done"`.

**Key point**: After you inject, the runner automatically resumes the loop — you do not need
to restart the background process. The runner blocks waiting for your feedback, picks it up
within 2 seconds of injection, and calls the controller again with resume params.

### 3b. If `event == "loop_done"`: read the result

```bash
cat /tmp/result_row1.json | python -m json.tool
```

---

## How HITL Works (Non-Blocking with Auto-Resume)

The loop does **not** pause for HITL. It:
1. Identifies a conflict → emits `human_feedback_needed` via `progress_cb`
2. Writes the HITL event to `{dossiers_root}/hitl_prompts/mission-row1-tx_pending.json`
3. Registers the pending prompt in blocker_registry
4. Continues working on what it can (other repairs, other tickets)
5. At the **start of each subsequent iteration**, calls `drain_pending_feedback` — if feedback
   has been injected, it picks it up and applies it immediately

If the loop exhausts its iteration budget while still waiting for feedback, the runner
**automatically blocks and waits** (polling every 2 seconds, up to 10 minutes). When feedback
is injected, the runner **resumes the controller** with the feedback as authority. This cycle
repeats up to 10 HITL rounds.

This means the loop will never stop at `waiting_feedback` while a tester is present — it keeps
going as long as feedback is provided.

**Use `--tx-max-iterations 12`** (or higher) so the loop has enough budget to act on feedback
before exhausting and handing back to the runner's block-poll.

---

## Run ID Convention

The run_id used by `hitl_watch` and `hitl_inject` is derived from `--mission-id`:

```
mission-{mission_id}-tx
```

So `--mission-id row1` → run_id `mission-row1-tx`.

The viewer_run_id (used internally by the feedback store) maps from `mission-row1-tx` via
`viewer_run_id_from_request_prefix`. Use the same `--run-id mission-row1-tx` for both
`hitl_watch` and `hitl_inject`.

---

## Practice Deed: Right-of-Way Deed

**Transcript ref** (absolute path):
```
C:/Users/<user>/AppData/Local/Plattera/Data/dossiers_data/views/transcriptions/practice_row_dossier/practice_row_t7/raw/practice_row_t7.json
```

**Full test command**:
```bash
python -m api.mission_runtime_cli \
  --initial-mode transcript_edit \
  --objective "audit and repair right_of_way deed transcript" \
  --mission-id row1 \
  --tx-source-transcript-ref "<abs path to practice_row_t7.json>" \
  --tx-dossier-id practice_row_dossier \
  --tx-max-iterations 12 \
  --done-file /tmp/done_row1.json \
  > /tmp/result_row1.json 2>/tmp/err_row1.txt &
```

**Expected HITL prompt**: Range 74 vs 75 conflict (Layer 2 — canonical sanity).
See `practice_deeds/right_of_way_deed_cheatsheet.md` for the correct answer and full 4-layer closure map.

---

## Reading Results

Key paths in the output JSON:
- `.mission_runtime.mission_status.terminal` — true/false
- `.mission_runtime.mission_status.terminal_class` — e.g. `"waiting_human"`, `"completed"`
- `.mission_runtime.mission_status.reason_code` — e.g. `"tx_agent_waiting_feedback"`
- `.mission_runtime.cycles[*].mode_result.validator_reports` — per-iteration audit findings
- `.mission_runtime.cycles[*].mode_result.runtime_hitl_state` — HITL state at completion

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Result file contains prompt text, not JSON | Interactive stdin in runner (old code) | Ensure runner uses file-based HITL only (no `input()`) |
| `event: loop_done` with `waiting_human` before feedback injected | Too few iterations, no_progress exhausted | Use `--tx-max-iterations 12` |
| `hitl_inject` says injected but loop didn't pick it up | Loop already terminated | Restart with more iterations |
| Empty done file / no sentinel | Loop crashed before writing | Check `/tmp/err_row1.txt` |
| HITL file not found / watcher times out | Loop ran without HITL (all repairs applied) | Check result for `"completed"` status |

---

## Links

- **HITL behavioral intent** (authoritative design intent): `docs/agent-testing/hitl-loop-behavioral-intent.md`
- Cheat sheet: `practice_deeds/right_of_way_deed_cheatsheet.md`
- Orchestration model: `docs/transcript-edit-loop-orchestration.md`
- CLI entry: `backend/api/mission_runtime_cli.py`
- HITL watch: `backend/harness/mission_runtime/hitl_watch.py`
- HITL inject: `backend/harness/mission_runtime/hitl_inject.py`
- CLI support / policy builder: `backend/harness/mission_runtime/cli_support.py`
- Feedback polling: `backend/agents/transcript_edit/iteration_repair_runtime.py` (line ~627)
