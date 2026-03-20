# Transcript Edit Loop — CLI Agent Testing Guide

## Purpose

This guide describes how to run and test the transcript-edit agent loop from the CLI in
agent-mode (non-interactive), where an AI agent acts as both test driver and HITL feedback
provider.

For the shared testing baseline, read `docs/agent-testing/transcript-edit-loop-holistic-intent.md`
first. This guide is the execution protocol; the holistic intent doc is the "what are we testing"
reference.

**The kernel is the default path.** As of Phase 12, `--tx-use-orchestration-kernel` is on by
default. No extra flag is needed. Use `--tx-use-legacy-controller` to opt back to the legacy
path for debugging.

Pattern: run loop → watch for HITL/done → inject feedback → re-watch → repeat.

**Do not start the backend API server for transcript-edit loop testing.**
This loop is exercised directly through the CLI and local filesystem/HITL plumbing.
The backend server is only needed for upstream setup steps such as t0 fixture creation.

---

## Prerequisite: t0 Transcription (One-Time Fixture Setup)

**The transcript-edit loop does not call the image pipeline.** The loop takes an existing
transcript artifact as input — that artifact is created by a separate upstream step called **t0**
(initial transcription: image → `gpt-o4-mini`, redundancy=3).

Before running the loop for the first time, create the canonical practice fixture:

```powershell
# Backend must be running (python main.py in another terminal)
# From repo root C:\projects\Plattera

curl.exe -s -X POST "http://localhost:8000/api/dossier/process" `
  -F "file=@practice_deeds\legal_text_image.jpg" `
  -F "dossier_id=live-validation-practice-legaltext" `
  -F "model=gpt-o4-mini" `
  -F "redundancy=3" `
  -F "auto_llm_consensus=false" `
  | python -m json.tool
```

This writes `draft_legal_text_image_v2.json` (and v1, v3) under
`dossiers_data/views/transcriptions/live-validation-practice-legaltext/`.
Once those files exist, `--tx-scenario practice_legaltext` resolves the path automatically and
**you do not need to re-run t0** unless the fixture data is deleted.

> See `docs/agent-testing/practice-deed-t0-setup.md` for full details, verification steps,
> and why the model and redundancy settings are fixed.

---

## Core Components

| Tool | Module | Purpose |
|------|--------|---------|
| `mission_runtime_cli` | `backend/api/mission_runtime_cli.py` | Run the loop |
| `hitl_watch` | `backend/harness/mission_runtime/hitl_watch.py` | Block until HITL arrives or loop finishes |
| `hitl_inject` | `backend/harness/mission_runtime/hitl_inject.py` | Inject feedback into the feedback store |

> All commands below assume: repo root is `C:\projects\Plattera`, venv is active, working
> directory is `backend\`. Adjust paths for your machine.
>
> For this loop, launch the CLI directly. Do **not** start `python main.py` or any backend
> server process unless you are explicitly running the separate t0 fixture setup.
>
> **`tmp\` convention**: use a repo-local `tmp\` folder for done-sentinel and result files.
> It keeps everything in one place and avoids `/tmp` path differences between shells.
> Add `tmp/` to `.gitignore` if not already present.

---

## Quick Start — Practice Deed (Canonical Scenario)

The canonical test scenario is **`practice_legaltext`** — a legal-text image deed with a
known range 74 vs 75 conflict. Pass `--tx-scenario practice_legaltext` and the CLI resolves
the dossier id and transcript seed automatically.

### PowerShell (two-terminal pattern — recommended on Windows)

**Terminal 1 — run the loop:**
```powershell
cd C:\projects\Plattera\backend

python -m api.mission_runtime_cli `
  --initial-mode transcript_edit `
  --objective "audit and repair legal text transcript" `
  --mission-id row1 `
  --tx-scenario practice_legaltext `
  --tx-validation-mode live_hitl `
  --tx-max-iterations 12 `
  --done-file tmp\done_row1.json `
  > tmp\result_row1.json 2> tmp\err_row1.txt
```

**Terminal 2 — watch (run immediately after starting Terminal 1):**
```powershell
cd C:\projects\Plattera\backend

python -m harness.mission_runtime.hitl_watch `
  --run-id mission-row1-tx `
  --done-file tmp\done_row1.json `
  --timeout 600
```

### Bash / Git Bash (background operator available)

```bash
cd /c/projects/Plattera/backend

python -m api.mission_runtime_cli \
  --initial-mode transcript_edit \
  --objective "audit and repair legal text transcript" \
  --mission-id row1 \
  --tx-scenario practice_legaltext \
  --tx-validation-mode live_hitl \
  --tx-max-iterations 12 \
  --done-file tmp/done_row1.json \
  > tmp/result_row1.json 2>tmp/err_row1.txt &

python -m harness.mission_runtime.hitl_watch \
  --run-id mission-row1-tx \
  --done-file tmp/done_row1.json \
  --timeout 600
```

---

## Step-by-Step Pattern

### 1. Start the loop

Run the CLI command above (foreground in its own terminal, or background via `&` in bash).

Key args:
- `--mission-id row1` → predictable run id: `mission-row1-tx` (used by watch/inject)
- `--tx-scenario practice_legaltext` → resolves dossier id + transcript seed automatically
- `--tx-validation-mode live_hitl` → enables the HITL lifecycle for the range conflict
- `--tx-max-iterations 12` → enough budget for mid-run feedback integration
- `--done-file tmp\done_row1.json` → sentinel file written when the loop finishes

Without `--tx-scenario`, supply the transcript ref explicitly:
```
--tx-dossier-id live-validation-practice-legaltext
--tx-source-transcript-ref "C:\path\to\draft_legal_text_image_v2.json"
```

CLI-only reminder:
- no backend API server is required for this loop
- `hitl_watch` and `hitl_inject` operate against the local run files / feedback store
- if you need the practice transcript seed, create it once via the separate t0 setup doc

### 2. Block waiting for HITL or done

`hitl_watch` exits immediately and prints **one JSON line**:

```json
// HITL arrived:
{"event": "hitl", "run_id": "mission-row1-tx", "prompt_id": "hitl_range_3_217f6ebf",
 "message": "Range conflict: Section 2 says 75, Sections 3-4 say 74. Which is correct?",
 "choices": ["Range 74 West", "Range 75 West"], "context": {...}}

// Loop finished normally:
{"event": "loop_done", "status": "completed", "terminal": true, "reason_code": "..."}

// Loop paused waiting for feedback (slow path):
{"event": "loop_done", "status": "waiting_feedback", "terminal": true, "reason_code": "..."}

// Timed out:
{"event": "timeout", "timeout_seconds": 600}
```

### 3a. If `event == "hitl"` — inject feedback, then re-watch

```powershell
# Inject — runner is already polling the feedback store
python -m harness.mission_runtime.hitl_inject `
  --run-id mission-row1-tx `
  --prompt-id hitl_range_3_217f6ebf `
  --choice "Range 75 West"

# Re-watch — runner picks up feedback within ~2 seconds and resumes
python -m harness.mission_runtime.hitl_watch `
  --run-id mission-row1-tx `
  --done-file tmp\done_row1.json `
  --timeout 600
```

Repeat watch → inject until `event == "loop_done"`.

### 3b. If `event == "loop_done"` — read the result

```powershell
Get-Content tmp\result_row1.json | python -m json.tool
```

---

## How HITL Works

The loop does **not** pause. It:
1. Identifies the range conflict → emits `human_feedback_needed` via `progress_cb`
2. Writes the HITL event to the pending file watched by `hitl_watch`
3. Keeps working on everything else while waiting
4. Picks up feedback at the start of the next iteration (**fast path**) **or** the runner
   block-polls and resumes the loop when feedback arrives (**slow path**)

Both paths are transparent to the tester — the observable outcome is identical.

See `docs/agent-testing/hitl-loop-behavioral-intent.md` for the full design intent.

---

## Kernel Routing

| Flag | Effect |
|------|--------|
| *(default, no flag)* | Transcript-edit routes through the orchestration kernel |
| `--tx-use-legacy-controller` | Opt back to legacy controller loop (debug escape hatch) |
| `--deed-use-orchestration-kernel` | Route deed-to-IR through kernel (off by default) |

The kernel path persists a `trace_artifact_ref` in `latest_refs` — a canonical trace artifact
covering every phase boundary, move decision, execution result, and terminal outcome. Its
presence in the result confirms you ran the kernel path.

## Human Review Surface

After a run completes, inspect the projected transcript-edit run feed:
- Stable last run: `dossiers_data/state/transcript_edit/run_feed/latest_transcript_edit_run.json`
- Recent runs feed: `dossiers_data/state/transcript_edit/run_feed/transcript_edit_recent_runs.json`

Use the stable last-run file when you want the most recent recap and freshness posture. Use the
recent-runs feed when you want to compare the last few completions without opening terminal logs.

---

## Run ID Convention

```
mission-{mission_id}-tx
```

`--mission-id row1` → run id `mission-row1-tx`. Use the same value for both `hitl_watch`
and `hitl_inject`.

---

## Practice Deed: Legal-Text Image (Canonical Scenario)

| Field | Value |
|-------|-------|
| Scenario flag | `--tx-scenario practice_legaltext` |
| Dossier id | `live-validation-practice-legaltext` |
| Transcript seed | `draft_legal_text_image_v2.json` (auto-resolved from local dossiers store) |
| Expected HITL | Range contradiction: 74 West vs 75 West |
| Correct answer | Range 75 West |
| Validation mode | `--tx-validation-mode live_hitl` |

The `--tx-scenario` flag resolves the dossier id and searches the local dossiers store for
`draft_legal_text_image_v2.json`. If the file is not found, the CLI prints a clear error and
asks you to supply `--tx-source-transcript-ref` manually.

**Expected lifecycle**: see `docs/transcript-edit-live-validation-path-2026-03-08.md` for
checkpoints A–D (waiting owner → feedback accepted → post-resume integration → terminal
explainability).

---

## Reading Results

Key paths in the output JSON:
- `.mission_runtime.mission_status.terminal` — `true`/`false`
- `.mission_runtime.mission_status.terminal_class` — e.g. `"exhausted"`, `"completed"`
- `.mission_runtime.mission_status.reason_code`
- `.mission_runtime.cycles[*].mode_result.runtime_hitl_state` — HITL state at completion
- `.mission_runtime.cycles[*].mode_result.latest_refs.trace_artifact_ref` — kernel trace path

---

## Agent-Mode Scriptable Checklist

When running this as an automated agent:

1. **Start** the loop command (foreground Terminal 1 or background bash `&`).
2. **Run `hitl_watch`** (blocking). Parse the single JSON output line.
3. **On `event == "hitl"`**:
   - Read `prompt_id` and `choices` from the output.
   - For `practice_legaltext`: inject `--choice "Range 75 West"`.
   - Run `hitl_inject --run-id ... --prompt-id ... --choice "..."`.
   - Return to step 2.
4. **On `event == "loop_done"`**:
   - Check `status`. `"completed"` or `"needs_review"` are expected terminals.
   - Read `tmp\result_row1.json` for the full payload.
   - Verify `.mission_runtime.cycles[0].mode_result.latest_refs.trace_artifact_ref` is
     present — confirms kernel path was active.
5. **On `event == "timeout"`**: inspect `tmp\err_row1.txt`; the loop may have hung or
   the dossier store path may be wrong.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Scenario 'practice_legaltext': transcript seed not found` | t0 fixture not created yet | Run the t0 setup step — see `docs/agent-testing/practice-deed-t0-setup.md` |
| `event: loop_done` with `waiting_feedback` immediately | Too few iterations | Use `--tx-max-iterations 12` or higher |
| `hitl_inject` says injected but loop didn't pick it up | Loop already terminated | Restart with more iterations |
| No `tmp\result_row1.json` or empty file | Loop crashed before writing | Check `tmp\err_row1.txt` |
| `trace_artifact_ref` missing in result | Legacy controller path active | Remove `--tx-use-legacy-controller` (kernel is the default) |

---

## Links

- Holistic test intent and success criteria: `docs/agent-testing/transcript-edit-loop-holistic-intent.md`
- **t0 fixture setup** (run first, one-time): `docs/agent-testing/practice-deed-t0-setup.md`
- **HITL behavioral intent** (authoritative): `docs/agent-testing/hitl-loop-behavioral-intent.md`
- **Live validation scenario + expected lifecycle**: `docs/transcript-edit-live-validation-path-2026-03-08.md`
- CLI entry: `backend/api/mission_runtime_cli.py`
- CLI support / scenario resolver: `backend/harness/mission_runtime/cli_support.py`
- HITL watch: `backend/harness/mission_runtime/hitl_watch.py`
- HITL inject: `backend/harness/mission_runtime/hitl_inject.py`
