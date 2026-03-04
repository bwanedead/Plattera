# Transcript Edit Pre-LLM Deep Dive

## Purpose
This document explains only one boundary:
- what happens after T0 handoff
- before the first new LLM/vision call

It is intentionally detailed and explicit so the mechanics are auditable and discussable without reading code.

Related broader doc:
- `docs/transcript-edit-loop-orchestration.md`

---

## Hard Boundary: What "Pre-LLM" Means
Pre-LLM here means:
- no fresh remote model inference request is sent
- all behavior is deterministic runtime logic

Deterministic means:
- same transcript input + same config -> same findings/events
- changes in timing can occur from machine load, but semantic outputs remain stable

First post-T0 stage that is model-dependent:
- `image_verify` (vision checks)

Everything before `image_verify` is local code path behavior.

---

## Stage Map (Pre-LLM only)
1. Handoff state assembly
2. Countdown ticker
3. `starting` event payload build
4. Candidate disagreement hint generation
5. `orient` event payload build (currently non-essential)
6. Canonicalization of transcript input
7. Deterministic audit validators
8. `audit_result` synthesis
9. Decision ledger update
10. Baseline conflict map + focus selection
11. Span opening for local context
12. Baseline residual blocker shaping

---

## Implementation Resolution Index (concrete mechanism per stage)
This is the "what actually executes" index, not conceptual intent.

1. Handoff state assembly
- Request fields are hydrated into controller state.
- Candidate draft texts are attached as raw strings.
- A mutable loop-state object is created for counters, refs, and ledger.

2. Countdown ticker
- A decrementing loop emits `preflight_countdown` once per second.
- `time.sleep(1)` enforces wall-clock spacing.

3. `starting`
- A status payload is string-formatted from already-known metadata.

4. Candidate disagreement hints
- Regex extractors scan each candidate text.
- Matched values are normalized and bucket-counted.
- Sorted bucket lists become hint payload families.

5. `orient`
- Static/semi-static checklist payload emission.

6. Canonicalization
- Source transcript ref/text is materialized into canonical document sections.
- Deterministic source hash is computed.

7. Audit
- Deterministic validators execute locally over canonical transcript.

8. `audit_result`
- Validator outputs are summarized into counts + top findings payload.

9. Decision ledger update
- Findings/hints are reduced into per-key state transitions.

10. Baseline + focus
- Conflict map is built from multi-value hint families.
- Focus key is selected with deterministic ranking rules.

11. Open spans
- Bounded text windows are extracted by anchors/offsets/fallback.

12. Residual blocker shaping
- Unresolved ledger items are reduced into blocker summaries and next action.

---

## 1) Handoff State Assembly
Conceptual:
- Build a run-local state object using outputs already produced by T0.

How it is accomplished:
- Resolve source transcript (artifact ref or inline text).
- Attach candidate draft texts when available from redundancy metadata.
- Attach source image refs for later stages (not consumed yet by model calls).
- Initialize mutable loop state:
  - current transcript ref/hash placeholders
  - iteration counters
  - no-progress streak and signature slots
  - sticky feedback slots
  - decision ledger root object

Why this matters:
- It defines the exact deterministic input universe the rest of pre-LLM stages operate on.

---

## 2) Countdown Ticker
Conceptual:
- Pure temporal boundary between T0 and transcript-edit processing.

How it is accomplished:
- Emit `preflight_countdown` event every second from N to 0.
- Sleep 1 second between emissions.
- No transcript parsing, no hints, no findings.

Why this matters:
- Provides explicit operator-visible separation.
- Does not affect logic outputs except delaying when downstream stages start.

---

## 3) `starting` Event
Conceptual:
- Run banner that summarizes what this run is about to do.

How it is accomplished:
- Build status text from known deterministic facts:
  - selected mode
  - candidate draft count
  - whether disagreement hints exist
- Emit one structured status payload.

Important:
- `starting` does not perform analysis.
- It reports state already known from handoff + hint derivation.

---

## 4) Candidate Disagreement Hints (Full Mechanism)
This is the piece you asked for most directly.

### What a hint is
A hint is:
- a machine-generated disagreement signal derived from T0 candidate drafts
- not a model judgment
- not user feedback

Example hint meaning:
- "Range tokens conflict across drafts: one bucket suggests 74, another 75."

### Input to hint generation
- candidate draft text list from T0 redundancy output
- each candidate is treated as a plain text source for deterministic extraction

### Extraction pass
For each candidate draft:
- apply deterministic token/value extractors for key families:
  - range-like values
  - distance-like values
  - bearing-like values
  - acreage-like values

The extractor behavior is rule-driven:
- regex-style patterns
- no model calls

Exact current regex extractors used for hinting:
- Range pattern A: `\brange[^()]{0,60}\((\d{1,3})\)\s*(west|east)\b`
- Range pattern B: `\br\s*\.?\s*(\d{1,3})\s*([we])\b`
- Acreage pattern: `\b(\d+(?:\.\d+)?)\s*acres?\b`
- Distance pattern: `\b(\d{2,5}(?:\.\d+)?)\s*(?:ft|feet)\b`
- Bearing pattern: `\b[NS]\.?\s*\d{1,3}(?:\s*°\s*\d{1,2})?\s*(?:[EW]\.?|east|west)\b`

Critical precision:
- This hint stage currently does **not** extract township/section directly.
- It currently emits hint families for range/acreage/distance/bearing.

### Normalization pass
Raw extracted values are canonicalized so equivalent strings compare cleanly.

Examples of normalization intent:
- strip punctuation/noise differences
- normalize directional suffix formatting
- normalize spacing/case variants
- normalize numeric text forms when safely equivalent

Goal:
- "same value written differently" should collapse to one normalized value.

Exact current normalization behavior:
- Range: converted to canonical short token `r{number}{w|e}` (example `r75w`).
- Bearing: lowercased and internal whitespace collapsed.
- Acreage/Distance: numeric string captured by regex is used as bucket key.

### Bucketing/count pass
For each value family:
- create buckets keyed by normalized value
- count frequency and track candidate provenance

Result shape (conceptual):
- family: `range_values`
- buckets:
  - value `74` seen in candidate 2
  - value `75` seen in candidates 1 and 3

Exact bucket algorithm:
- For each extracted value: increment integer counter in dict bucket.
- After scan: convert to list of `{value, count}`.
- Sort by `count desc`, then `value asc`.
- Keep top 8 per family.
- Scan cap is first 10 candidate drafts.

### Conflict detection pass
A disagreement hint exists when:
- there are competing buckets in a mapping-sensitive family
- and conflict survives normalization

Exact trigger used downstream:
- Family disagreement is treated as present when `len(family_values) > 1`.

No conflict hint when:
- all candidates converge to one normalized bucket
- or only one reliable extraction exists

### Output shape
Hints are stored as structured fields, conceptually:
- `range_values[]`
- `distance_values[]`
- `bearing_values[]`
- `acreage_values[]`
- each item can include normalized value + support count/provenance

### Where hints are used pre-LLM
Hints feed:
- `starting` copy ("disagreements detected")
- baseline conflict map generation
- decision ledger updates
- focus prioritization

Concrete downstream effects:
- Synthetic disagreement findings can be created from these hints.
- These can influence blocking warning behavior and HITL gating later.

### Why hints feel "too instant"
Because the entire hint pipeline is local:
- parse
- normalize
- bucket
- compare

No network roundtrip occurs.

---

## 5) `orient` Event (Current Role and Concern)
Conceptual:
- Checklist-style narration event.

How it is accomplished:
- Construct fixed/semi-fixed "what will be checked" text.
- Emit event.

What it is not:
- Not an evidence retrieval stage
- Not a validator stage
- Not a model stage

Operational concern:
- It can create a perception of synthetic "work theater."
- It is a valid removal candidate if goal is strict signal-to-noise event stream.

Exact implementation resolution:
- `orient` is emitted as a report payload after `starting`.
- It does not fetch artifacts, run validators, or mutate transcript content.

---

## 6) Canonicalization of Transcript Input
Conceptual:
- Convert source transcript into a stable, normalized internal document.

How it is accomplished:
- Materialize section-based structure
- ensure deterministic ordering/shape
- compute stable transcript hash/fingerprint

Exact implementation resolution:
- Canonical materialization resolves source ref/text into a normalized transcript document.
- Hash is computed over canonical transcript text.
- This canonical ref/hash is what audit/apply safety checks consume.

Why this matters:
- validators run against canonical structure
- hash enables downstream consistency checks and safe apply behavior

---

## 7) Deterministic Audit Validators
Conceptual:
- A local linter/rule-engine pass over canonical transcript.

How it is accomplished:
- apply deterministic validators such as:
  - PLSS consistency checks
  - bearing parse and structure checks
  - numeric/unit sanity checks
  - call-chain structure checks
- produce finding records with:
  - finding id/type/severity
  - message
  - section/span references where available

Important:
- This stage can look semantic but is still deterministic rule logic.
- No fresh model call here.

Exact implementation resolution:
- Local validator runner produces a structured validator report artifact.
- Report summary and clipped top findings are emitted into progress payloads.

---

## 8) `audit_result` Synthesis
Conceptual:
- Convert raw validator outputs into concise run payload.

How it is accomplished:
- count findings by severity/type
- select top findings for display
- build summary text
- attach latest refs/metadata for subsequent stages

Why it repeats identically:
- same canonical transcript + same validators -> same report.

---

## 9) Decision Ledger Update
Conceptual:
- Translate findings + hints into a per-decision closure state model.

How it is accomplished:
- update item states (unknown/disputed/verified/etc.)
- mark mapping-blocking vs optional impact
- attach alternatives and evidence pointers
- compute unresolved closure requirement candidates

Exact implementation resolution:
- Ledger reducer consumes findings + disagreement hint snapshot.
- Outputs per-decision states used by baseline/result policy.

Why this matters:
- downstream stages operate on ledger state, not raw finding text alone.

---

## 10) Baseline Conflict Map + Focus Selection
Conceptual:
- Decide what to inspect next and report why.

How it is accomplished:
- derive conflict map from hint buckets
- rank unresolved decision items via deterministic policy
- choose next focus key and reason code

Exact implementation resolution:
- Conflict map includes only families with multi-value hints.
- Focus selection chooses next key from ledger status/ranking rules.

Outputs:
- `investigation_baseline` event
- optional investigate ticker narrative

---

## 11) Local Span Opening
Conceptual:
- Collect local transcript slices around focused findings.

How it is accomplished:
- use offsets/anchors/fallback extraction paths
- enforce max chars per span and total-budget caps
- emit span previews and persist span artifact refs

Exact implementation resolution:
- Span opener accepts source transcript + focused findings.
- Returns bounded context snippets; may fallback when targeted spans are sparse.

Important:
- This is still local transcript manipulation.
- No model verification yet.

---

## 12) Baseline Residual Blocker Shaping
Conceptual:
- Produce explicit unresolved-blocker snapshot before model verification.

How it is accomplished:
- compute unresolved closure requirements from ledger
- compute mapping-blocking and optional counts
- generate deterministic "next recommended action" text

Exact implementation resolution:
- Unresolved ledger entries are transformed to residual blocker objects.
- Count aggregation and next-action synthesis are deterministic string/data transforms.

Outputs:
- `investigation_baseline_result` payload content (when emitted in sequence)

---

## Why the Pre-LLM Burst Feels Non-Physical
Perception issue:
- multiple stages emit in rapid succession
- several stages are messaging/aggregation, not expensive computation

Reality:
- this is expected for deterministic local stages
- the first true network/model latency appears only when `image_verify` starts

---

## Proposed Event Discipline Improvements
1. Remove `orient` event if it adds no decision value.
2. Tag events with `execution_origin`:
   - `deterministic_local`
   - `model_dependent`
3. In UI, visually separate pre-LLM events from model-bound phases.
4. Keep countdown short but explicit to preserve boundary signal.

---

## Fast FAQ
Q: Can hint generation require semantic understanding?
- It uses structured extraction heuristics and consistency logic, not fresh model reasoning.

Q: Why are early findings identical run-to-run?
- Same canonical input and deterministic validators.

Q: Does "instant" imply caching bug by itself?
- Not necessarily. Deterministic local stages can legitimately be near-instant.

Q: Where does fresh model work start?
- At `image_verify` (and later planner model steps when applicable).
