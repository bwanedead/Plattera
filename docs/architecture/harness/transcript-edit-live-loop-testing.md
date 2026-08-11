# Transcript-Edit Live Loop Testing Guide

This is the single entrypoint doc for getting a fresh testing agent up to
speed on transcript-edit live-loop testing.

Read this doc first, then follow the links in sections 2 and 6.

If the intended test is the downstream **deed-to-IR** stage, use
[`docs/architecture/harness/deed-to-ir-live-loop-testing.md`](./deed-to-ir-live-loop-testing.md)
instead. That guide starts from the frozen transcript-edit handoff and covers
the deed-to-IR launch, foreground watcher, timeline, and artifact review flow.

---

## 1. What You Are Testing

You are testing whether the generic harness can run the
`mapping / transcript_edit` domain against a real practice dossier and whether
the model behaves like a useful transcript-edit agent.

Expected high-level loop behavior:

1. inspect the startup inventory of source image refs and peer T0 draft refs
2. hydrate one or more draft refs and source-image context as needed
3. maintain model-authored work state through `state_patch`
4. save transcript-edit working draft revisions when the model has authored a
   useful edit
5. publish transcript-edit output only when explicitly ready
6. surface contradictions or missing source content instead of silently guessing
7. request human input when a contradiction is genuinely blocked on HITL

For domain semantics and architecture boundaries, read
[`docs/architecture/harness/transcript-edit-domain.md`](./transcript-edit-domain.md).

For family-level mission intent, read
[`docs/architecture/mapping/mapping-family-intent.md`](../mapping/mapping-family-intent.md).

---

## 2. Non-Negotiable Standards

Before running or modifying anything, read:

- [`AGENTS.md`](../../../AGENTS.md)
- [`docs/architecture/harness/harness-constitution.md`](./harness-constitution.md)
- [`docs/architecture/harness/agent-engine-constitution.md`](./agent-engine-constitution.md)
- [`docs/architecture/harness/agent-sanity-baseline.md`](./agent-sanity-baseline.md)
- [`docs/architecture/harness/hitl-constitution.md`](./hitl-constitution.md)
- [`docs/architecture/harness/cli-constitution.md`](./cli-constitution.md)
- [`docs/architecture/harness/domain-pack-constitution.md`](./domain-pack-constitution.md)
- [`docs/architecture/harness/domain-runtime-adapter-architecture.md`](./domain-runtime-adapter-architecture.md)
- [`docs/ethos/agent-engine-ergonomics-theory.md`](../../ethos/agent-engine-ergonomics-theory.md)
- [`docs/ethos/testing-ethos.md`](../../ethos/testing-ethos.md)

Tester rule of thumb:

- report whether failures are reasoning failures or seam/contract failures
- if the model repeatedly expresses a sane near-miss action shape, preserve that
  evidence because it may be an ergonomics signal
- do not “fix” behavior by introducing deterministic semantic scripting in the
  harness

---

## 3. Choose the Intended Test

Transcript edit has one domain, one harness loop, and the same five action IDs.
The launch scope changes what that same agent can see and publish:

| Tester request | Launch scope | Approved practice input |
|---|---|---|
| right-of-way / single-transcription test | `transcription` (or selector absent) | existing right-of-way dossier below |
| curve / station-chain / multi-page dossier test | `dossier` | `curve_station_chain` below |
| new-deed mixed-instrument test | setup pending | source is usable; logical instrument spans must be configured first |

`dossier` mode is not a separate transcript-edit pipeline. It gives one
continuous transcript-edit run the ordered segments of one instrument. The
agent keeps one holistic work universe while using bounded, self-chosen
attention windows over individual segments or adjacent boundaries.

The runtime does not spawn a fresh agent per page and does not mechanically
decide the rolling windows. Each segment keeps its own exact working-revision
lineage so edits and evidence remain source-local. At publication, the agent
names one exact working revision per segment, and the tooling mechanically
assembles the ordered dossier-level transcript.

### 3.1 Single-transcription right-of-way input

The current app-generated right-of-way practice dossier is:

- `dossier_id = 9f5eecb6-cd7e-483c-b691-b76aa7132e8e`
- `transcription_id = draft_legal_text_image`
- source image:
  `backend/dossiers_data/images/original/draft_legal_text_image_original.jpg`
- T0 run folder:
  `backend/dossiers_data/views/transcriptions/9f5eecb6-cd7e-483c-b691-b76aa7132e8e/draft_legal_text_image/`

Read
[`practice_deeds/right_of_way_deed_cheatsheet.md`](../../../practice_deeds/right_of_way_deed_cheatsheet.md)
before judging whether behavior is good or bad.

Key expected practice-deed observations:

- the deed image is cut off at the bottom; Plot 2 is incomplete
- `Range 75` vs `Range 74` is an intrinsic source contradiction and should
  become a HITL/blocker, not a silent deterministic choice
- `1.4 acres` in one T0 draft should be corrected to `1.9 acres` from source
  evidence
- Plot 1 should remain forwardable to mapping once the range conflict is
  resolved; Plot 2 should be marked blocked/incomplete

### 3.2 Dossier-scale curve / station-chain input

The approved first dossier-scale live test is:

- `dossier_id = 892abc34-ed4d-4e85-a0cb-9a5ddc133f31`
- ordered segment 1: `draft_curve_deed_part1`
- ordered segment 2: `draft_curve_deed_part2`
- frozen baseline:
  `practice_deeds/dependency_chain/curve_station_chain/`
- source images expected by the app dossier:
  - `backend/dossiers_data/images/original/draft_curve_deed_part1_original.jpg`
  - `backend/dossiers_data/images/original/draft_curve_deed_part2_original.jpg`

Read
[`docs/architecture/harness/dependency-practice-dossiers.md`](./dependency-practice-dossiers.md)
before judging this run.

This is a real continuity test. Segment 1 ends mid-description with
`... 144.9 feet to`; segment 2 continues the legal description. Peer T0 drafts
also disagree on material station, bearing, curve, and distance readings. The
agent should therefore inspect both T0 candidates and source evidence, follow
the cross-segment continuation, and author supported per-segment revisions. It
must not treat the end of segment 1 as missing merely because the sentence
continues on segment 2.

The stored T0 drafts are also materially incomplete: they focus on highlighted
canal descriptions and omit substantial unhighlighted page text. The full
source includes references to Lake Hattie/Pioneer Canal interests acquired
under separately recorded Pioneer Canal Company lease instruments. The
transcript-edit agent should recover supported omitted source text, not merely
choose the best highlighted T0 candidate. Those external references are a real
dependency-discovery signal; because the referenced instruments are absent,
the honest downstream posture is unmatched/pending rather than an invented
link.

Before launch, verify both expected source-image files exist. If either is
missing, do not run a source-evidence test and do not silently substitute
another image. Report the missing path so the frozen baseline can be restored.

### 3.3 Mixed-instrument `new_deed` source packet

Dossier `64b66561-6c0a-4702-a6b6-b8b5c076d891` contains usable source and
should not be discarded. Its two physical pages contain two legal instruments:

1. the left page and top of the right page contain the conveyance and
   acknowledgment for a town-lot deed; and
2. the lower part of the right page begins a Lake Hattie right-of-way deed and
   cuts off mid-description.

Every visible word remains valid transcript-edit work. The setup gap is at
publication scope: publishing both whole pages as one dossier transcript would
merge two instruments. Before using this packet for a live dossier-scale test,
configure logical instrument spans so the shared right page can finish the
first deed and independently begin the second deed. The partial second deed may
then proceed honestly as partial source; incompleteness is not a reason to omit
or refuse to transcribe it.

---

## 4. How To Run the Loop from CLI

Use PowerShell from repo root and activate the repo venv first:

```powershell
cd C:\projects\Plattera
. .venv\scripts\activate.ps1
cd backend
```

Start a single-transcription run:

```powershell
$runId = "practice-row-live-20"
$ctx = "{""dossier_id"":""9f5eecb6-cd7e-483c-b691-b76aa7132e8e"",""transcription_id"":""draft_legal_text_image"",""workspace_id"":""$runId"",""run_id"":""$runId"",""max_iterations"":100}"
python -m harness.cli.start --run-id $runId --loop-kind transcript_edit --run-collection transcript_edit_right_of_way --python-module harness.runtime.runner.entrypoint --module-arg=--domain-id --module-arg=transcript_edit --module-arg=--launch-context-json --module-arg=$ctx
```

Optional model override from CLI (stronger explicit alternative):

```powershell
python -m harness.cli.start --run-id $runId --loop-kind transcript_edit --run-collection transcript_edit_right_of_way --model gpt-5.6-terra --python-module harness.runtime.runner.entrypoint --module-arg=--domain-id --module-arg=transcript_edit --module-arg=--launch-context-json --module-arg=$ctx
```

Other supported overrides use the same `--model` flag (for example
`gpt-5.4-mini` or an explicit `gpt-5.6-luna`).

`--run-collection` is storage/retention identity only. Both right-of-way and
curve launches remain ordinary `transcript_edit` runs (`loop_kind` and domain
unchanged). Reuse the same collection for repeated attempts against the same
source so each source keeps an independent latest-five history. Keep
`workspace_id == run_id` fresh and equal on every clean attempt so the same
dossier is reused without inheriting previous working artifacts. Each retained
CLI run keeps its full timeline and turn-level audit package under
`by_loop_kind/<run_collection>/<run_id>/`.

### Dossier-scale curve / station-chain run

This uses the same `transcript_edit` loop and domain. The explicit scope
selector is the only launch-class difference. Do not include
`transcription_id` or `segment_id` in dossier mode.

For the first model-calibration run, use Terra explicitly:

```powershell
$runId = "curve-station-chain-<fresh-unique-suffix>"
$ctx = "{""dossier_id"":""892abc34-ed4d-4e85-a0cb-9a5ddc133f31"",""transcript_edit_scope_mode"":""dossier"",""workspace_id"":""$runId"",""run_id"":""$runId"",""max_iterations"":100}"
python -m harness.cli.start --run-id $runId --loop-kind transcript_edit --run-collection transcript_edit_curve_station_chain --model gpt-5.6-terra --python-module harness.runtime.runner.entrypoint --module-arg=--domain-id --module-arg=transcript_edit --module-arg=--launch-context-json --module-arg=$ctx
```

Then use the same foreground `watch` / HITL loop documented below. Do not
launch a separate child run for each segment.

Expected dossier-scale behavior:

1. inventory both ordered segments and all peer T0 drafts
2. investigate the material T0 disagreements with source evidence
3. recover material full-page text omitted by the highlight-focused T0 drafts
4. preserve the separately recorded Pioneer Canal lease references as
   dependency evidence
5. review the segment-1 ending jointly with the segment-2 beginning
6. save authored work into the appropriate qualified per-segment lineages
7. keep unresolved material honestly open, blocked, or in HITL
8. select one exact working revision for every topology segment
9. publish once with plural `source_revision_refs`
10. produce `transcript_edit:output` and an immutable
   `transcript_edit:dossier_output:sha256:<fingerprint>` ref

The first Terra run is also a calibration run after the model change. Preserve
the raw timeline evidence needed to distinguish model reasoning drift from a
tool-contract or continuity seam. Do not generalize a new harness rule from one
model run.

Guidance:

- use a fresh unique `run_id` for every live run
- keep `workspace_id == run_id` for live testing unless you have a specific
  reason not to
- for transcript-edit live behavior testing, prefer a roomier turn budget such
  as `max_iterations: 100` so the model has space to orient, itemize, verify,
  localize, re-check, and escalate honestly instead of compressing everything
  into a shallow few-turn pass
- omit `model` from launch context unless you explicitly want to override the
  harness default model
- the development harness default is `muse-spark-1.2-contributor`; omitting
  `--model` on a new run selects Muse Contributor via provider `meta`
- place provider credentials in `backend/.env` (Git-ignored). API and harness
  source-mode entrypoints load that file automatically; an explicitly exported
  process variable always wins. Resume/fork workers reload the same file when
  their new process starts:

```dotenv
# Model provider API keys
META_MODEL_API_KEY=your_key_here
```

- optional `META_MODEL_API_BASE_URL`; blank/absent uses `https://api.meta.ai/v1`
- explicit OpenAI overrides remain supported (for example
  `--model gpt-5.6-terra` or `--model gpt-5.6-luna`)
- if both launch context `model` and CLI `--model` are set, launch context
  wins; CLI `--model` is a convenience fallback for runs where the context JSON
  omits `model`
- resume and fork preserve the run’s recorded model rather than adopting the
  current default
- Contributor-route traffic may be retained/used by Meta; this is a development
  default and must be reconsidered before production launch

Check status:

```powershell
python -m harness.cli.status --run-id $runId
```

Request a graceful operator pause or stop:

```powershell
python -m harness.cli.pause --run-id $runId --reason "optional pause reason"
python -m harness.cli.stop --run-id $runId --reason "optional stop reason"
```

Control semantics:

- `pause` and `stop` are **graceful** operator controls; they do not kill the
  child process and they do not cancel a tool mid-call
- the runner honors them only at safe boundaries, including while waiting on a
  blocking HITL prompt
- while a live process has an unconsumed control request, `status` may show:

```json
{
  "control": {
    "command": "pause",
    "status": "pending"
  }
}
```

- once honored, the run writes `result.json` and `done.json` with status
  `paused` or `stopped`
- paused/stopped runs remain resumable from `kernel_resume.json`

Wait for either HITL or terminal completion:

```powershell
python -m harness.cli.watch --run-id $runId --timeout 60
```

`watch` is a blocking poll, not a background monitor.  It returns exactly one
JSON event, then exits:

- `{"event":"hitl", ...}` — answer the returned `prompt_id`, then watch again
- `{"event":"loop_done", ...}` — the run reached a terminal state; inspect it
- `{"event":"timeout", ...}` — no event arrived inside this watch window; keep
  watching the same run unless you intentionally want to stop monitoring
- `{"event":"error", ...}` — inspect `status`, run-state files, and logs

For live testing, the tester should keep `watch` in the foreground and stay in
this monitor loop until `loop_done` or an explicit operator decision to
pause/stop.  Do not launch the watcher in a detached/background shell; the
testing agent needs the foreground JSON event so it can answer HITL promptly and
then continue watching the same run.

```powershell
while ($true) {
  $watchEvent = python -m harness.cli.watch --run-id $runId --timeout 7200 --poll-interval 3 | ConvertFrom-Json

  if ($watchEvent.event -eq "timeout") {
    continue
  }

  if ($watchEvent.event -eq "hitl") {
    # Choose an answer from $watchEvent.choices when choices are provided. Use
    # $watchEvent.prompt_id exactly as returned by watch.
    python -m harness.cli.answer --run-id $runId --prompt-id $watchEvent.prompt_id --choice "<operator answer>" --note "<optional note>"
    continue
  }

  if ($watchEvent.event -eq "loop_done") {
    break
  }

  break
}
```

Important mechanical detail: when `watch` returns a HITL event, it consumes the
operator-side pending prompt sidecar so the same prompt is not repeatedly shown.
That is expected.  The prompt remains answerable using the `prompt_id` returned
by `watch`; do not rely on a later `status` call to rediscover that same prompt.

If `watch` returns a HITL prompt, answer it:

```powershell
python -m harness.cli.answer --run-id $runId --prompt-id <prompt_id_from_watch> --choice "<your answer>" --note "<optional note>"
```

### User-to-agent messages / tester corrections

HITL is agent-initiated: the agent asks, the tester answers.  The
user-message channel is tester/user-initiated: if you notice a concrete
mistake or need to give the agent context while observing a run, inject an
exact message for the next turn.

Use this when you see an incorrect detail, stale draft value, missing
operator instruction, or other user-observed issue that the agent should
repair.  Keep the message specific and actionable.  Do not treat it as a
truth override in your report; it is exact user-authored context delivered to
the agent, and the agent must integrate it through normal state/artifact
edits.

Example correction:

```powershell
python -m harness.cli.message --run-id $runId --text "Correction: parcel1_tie_bearing_to_nw_corner is wrong. Change the determined value and draft text from N. 2° 00' W. to N. 4° 00' W.; preserve/update the evidence note so it reflects the localized source crop." --source tester
```

Recommended correction shape:

- name the item/atom if you can (`item_id`, `unit_id`, or title)
- state the wrong value and the corrected value
- say what should be repaired: graph, draft/output artifact, evidence note, or
  all of them
- include a short why only when useful; avoid broad critique when a precise
  correction is enough

Then keep watching the same live run:

```powershell
python -m harness.cli.watch --run-id $runId --timeout 120
```

If the run has already stopped/failed/paused and `status` reports a resumable
checkpoint, inject the message first, then resume:

```powershell
python -m harness.cli.message --run-id $runId --text "Correction: <specific item and repair request>." --source tester
python -m harness.cli.resume --run-id $runId
python -m harness.cli.watch --run-id $runId --timeout 120
```

Current CLI boundary: completed runs are not reopened by `harness.cli.resume`.
If a mistake is discovered only after a `completed` terminal state, record it
in the test report and either start a follow-up run/workspace or ask for a
separate reopen capability.  Do not claim that the current resume path can
resume completed runs.

If a run dies because the child process exited, the network disconnected, or
the provider returned a resumable failure, check status before starting over:

```powershell
python -m harness.cli.status --run-id $runId
```

If status includes:

```json
{
  "interrupted": {
    "kind": "interrupted_resumable"
  }
}
```

resume the same logical run instead of launching a new run:

```powershell
python -m harness.cli.resume --run-id $runId
python -m harness.cli.watch --run-id $runId --timeout 120
```

Resume is mechanical. It restores the last completed `kernel_resume.json`
checkpoint and starts the next turn in the same run directory. It does not
replay a half-failed LLM call and it does not infer mission meaning. If the run
was started with an explicit or recorded model, the resumed child preserves that
model rather than adopting the current harness default
(`muse-spark-1.2-contributor`).
If the run had a pending `control.json`, resume consumes that stale control
request before spawning the child so the resumed run does not immediately stop
again.

If status reports `interrupted_no_checkpoint`, the run cannot be resumed from
the CLI control plane and should be treated as a failed/incomplete test run.

If status reports:

```json
{
  "interrupted": {
    "kind": "paused_by_operator"
  }
}
```

or:

```json
{
  "interrupted": {
    "kind": "stopped_by_operator"
  }
}
```

the run was intentionally interrupted by operator control and should normally be
resumed with:

```powershell
python -m harness.cli.resume --run-id $runId
```

Architectural rule:

- `HITL` semantics are harness-owned, not CLI-owned
- async `HITL` (`wait_for_human = false`) does not pause the logical run — the
  loop continues immediately and the eventual answer becomes visible to future
  turns
- blocking `HITL` (`wait_for_human = true`) pauses the run and resumes it
  automatically when the active blocking prompt is answered; no manual restart
  is required

Normal blocking-HITL testing flow (current implementation):

```powershell
# 1. Start run
python -m harness.cli.start --run-id $runId --loop-kind transcript_edit ...

# 2. Wait for HITL prompt in the foreground; do not background this command
python -m harness.cli.watch --run-id $runId --timeout 120

# 3. If event=hitl: answer — the live runner detects the answer and resumes
#    automatically
python -m harness.cli.answer --run-id $runId --prompt-id <prompt_id> --choice "74"

# 4. Watch again for the resumed run to reach its next terminal state
python -m harness.cli.watch --run-id $runId --timeout 120
```

The harness owns the resume: answering the active blocking prompt triggers
auto-resume in the live runner process.  The CLI `answer` command is only an
ingress surface; it does not decide whether or when to resume.

Normal operator-control testing flow:

```powershell
# 1. Start run
python -m harness.cli.start --run-id $runId --loop-kind transcript_edit ...

# 2. Observe the live run
python -m harness.cli.watch --run-id $runId --timeout 120

# 3. Request a graceful pause or stop
python -m harness.cli.pause --run-id $runId --reason "inspect current state"
# or
python -m harness.cli.stop --run-id $runId --reason "end this slice cleanly"

# 4. Check whether the control is pending or already honored
python -m harness.cli.status --run-id $runId

# 5. After the run reaches paused/stopped, resume the same logical run if desired
python -m harness.cli.resume --run-id $runId
python -m harness.cli.watch --run-id $runId --timeout 120
```

Expected control behavior:

- `watch` should eventually report a terminal event for `paused` / `stopped`
  after the control is honored
- during a blocked-HITL wait, pause/stop should still be honored without
  waiting for HITL answer or timeout
- the last turn record remains the kernel fact (for example `wait_for_human`);
  run-level audit surfaces may show a separate terminal override for the
  operator interruption

HITL wait timeout: the live runner process polls for feedback for up to
`hitl_wait_timeout_seconds` (default: 7200 s / 2 h).  If the timeout expires
without an answer, the run returns `waiting_human` as the terminal state.
`result.json` will include `kernel_resume_snapshot` so a fresh process restart
remains possible as a fallback, but is not the normal path.

---

## 5. Where To Inspect Artifacts

Harness CLI run-state and child logs for **new runs** (namespaced by
`--run-collection`, defaulting to `--loop-kind` when omitted):

```text
backend/harness/cli_artifacts/cli_runs/by_loop_kind/<run_collection>/<run_id>/
  state.json
  control.json
  kernel_resume.json
  stdout.log
  stderr.log
  result.json
  done.json
  retention.json
  audit/events.jsonl
  audit/index.json
  audit/review.md
  audit/human/timeline.md
  audit/turn_0001.json
  audit/turn_0002.json
  ...
```

Practice collections for transcript-edit sources:

- `transcript_edit_right_of_way`
- `transcript_edit_curve_station_chain`

Both remain ordinary `transcript_edit` loops; collection names affect storage
and latest-five retention only.

Legacy flat runs remain at `backend/harness/cli_artifacts/cli_runs/<run_id>/` (for
example `practice-row-live-20260619-76` from earlier live testing).

What the audit files are for:

- `audit/events.jsonl`: canonical append-only event stream for the run
- `audit/review.md`: quick human-readable run summary
- `audit/human/timeline.md`: live-updating readable per-turn timeline with
  model-authored prose, action inputs, tool results, state patch feedback,
  HITL facts, mission snapshots, resolution items, closure state, and
  observability flags; use this first when monitoring a live run
- `audit/index.json`: run-level audit index
- `audit/turn_000N.json`: exact turn ledger including prompt text, raw LLM
  response text, repair I/O when applicable, parsed action plan, tool
  request/result, and before/after state snapshots; these are forensic
  per-turn expansions, not the canonical event stream
- `kernel_resume.json`: last completed-turn checkpoint used by
  `harness.cli.resume`; it is a mechanical snapshot, not a semantic summary
- `control.json`: optional operator-authored pause/stop request; present only
  while a live control request is pending and normally consumed before resume

This `cli_runs/` folder is operator control-plane metadata. The transcript-edit
domain data path itself is app-native backend plumbing, not a CLI-only sandbox:
the CLI invokes the real `transcript_edit` domain adapter, loads dossier/T0
inputs from `dossiers_data`, and writes transcript-edit working/output artifacts
to the normal `artifacts/transcript_edit/...` tree below.

Harness CLI run/session artifacts:

```text
backend/harness/cli_artifacts/
```

Retention / reset notes:

- normal CLI run retention keeps the latest **5 unpinned runs per collection**
  (`transcript_edit`, `deed_to_ir`, and legacy flat runs each independently)
- a sixth deed-to-IR run removes only the oldest unpinned deed-to-IR run; it does
  not evict transcript-edit runs
- a one-time blank-slate purge helper exists for emergency reset scenarios; do
  not use it as part of normal testing flow

Transcript-edit working/output draft artifacts:

```text
backend/dossiers_data/artifacts/transcript_edit/<dossier_id>/<transcription_id>/<workspace_id>/
  working/rev_0001.json
  working/latest.json
  output/output.json
  manifest.json
```

Dossier-scale transcript-edit publication artifacts:

```text
backend/dossiers_data/artifacts/transcript_edit_dossier/<dossier_id>/<workspace_id>/
  output/latest.json
  output/revisions/<candidate_fingerprint>.json
```

The dossier-level revision contains the mechanically assembled full transcript
in canonical segment order, plus the exact source revision refs and evidence
provenance used to build it. It is the downstream handoff artifact; it is not a
second model-authored giant draft.

T0 source draft inputs remain under:

```text
backend/dossiers_data/views/transcriptions/<dossier_id>/<transcription_id>/raw/
```

Do not treat the legacy pointer alias `raw/<transcription_id>.json` as an
independent peer T0 draft. The startup inventory should expose only real peer
T0 draft refs from `run.json.completed_drafts`.

---

## 6. What To Read If Something Looks Wrong

Current domain + harness docs:

- [`docs/architecture/mapping/mapping-family-intent.md`](../mapping/mapping-family-intent.md)
- [`docs/architecture/harness/transcript-edit-domain.md`](./transcript-edit-domain.md)
- [`docs/architecture/harness/harness-constitution.md`](./harness-constitution.md)
- [`docs/architecture/harness/agent-engine-constitution.md`](./agent-engine-constitution.md)
- [`docs/architecture/harness/agent-sanity-baseline.md`](./agent-sanity-baseline.md)
- [`docs/architecture/harness/hitl-constitution.md`](./hitl-constitution.md)
- [`docs/architecture/harness/cli-constitution.md`](./cli-constitution.md)
- [`docs/architecture/harness/domain-pack-constitution.md`](./domain-pack-constitution.md)
- [`docs/ethos/agent-engine-ergonomics-theory.md`](../../ethos/agent-engine-ergonomics-theory.md)

Current code entrypoints:

- [`backend/harness/cli/`](../../../backend/harness/cli)
- [`backend/harness/runtime/runner/`](../../../backend/harness/runtime/runner)
- [`backend/harness/runtime/orchestration/`](../../../backend/harness/runtime/orchestration)
- [`backend/domains/mapping/transcript_edit/runtime_adapter/`](../../../backend/domains/mapping/transcript_edit/runtime_adapter)
- [`backend/tooling/mapping/transcript_edit/`](../../../backend/tooling/mapping/transcript_edit)

Practice deed interpretation:

- [`practice_deeds/right_of_way_deed_cheatsheet.md`](../../../practice_deeds/right_of_way_deed_cheatsheet.md)

## 7. What To Report After a Test Run

Always report:

- run id and launch context
- terminal status/reason
- whether the run was resumed from `kernel_resume.json`, and from which
  status/reason if applicable
- whether operator control (`pause` / `stop`) was used, whether it was pending
  or honored, and at what stage of the run it landed
- which tools the model called and in what order
- whether `state_patch` was applied/rejected/not_applied and why
- what transcript-edit working/output refs were produced
- whether HITL was requested and whether that request was warranted
- whether the model caught the known practice-deed quirks from the cheat sheet
- whether a failure was a model reasoning failure or a system/contract seam
  failure
- the key observations from `audit/human/timeline.md` when diagnosing turn
  coherence, repeated reads, or itemization quality

For a dossier-scale run, also report:

- whether the agent treated the dossier as one continuous instrument
- which segment boundaries it reviewed together and why
- the exact working revision selected for each segment
- whether it incorrectly treated a page ending as a missing source conclusion
- whether it used plural `source_revision_refs` with complete segment coverage
- the dossier output ref and immutable dossier output revision ref
- whether it recovered the unhighlighted external-instrument references omitted
  by T0
- whether observed differences appear attributable to the selected model

If behavior reveals a repeated sane near-miss action shape, preserve the raw
payload and cite
[`docs/ethos/agent-engine-ergonomics-theory.md`](../../ethos/agent-engine-ergonomics-theory.md)
when recommending contract changes.
