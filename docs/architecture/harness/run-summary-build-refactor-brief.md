# Run Summary Build Refactor Brief

This brief defines the next cleanup leg for:

- `backend/harness/run_summary/build.py`

Its purpose is simple:

- stop `build.py` from becoming the next harness junk drawer
- preserve the current read-model behavior
- split the file along honest responsibility boundaries
- keep the run-summary package generic and inspection-only

This is a **shape and maintainability** brief, not a feature brief.

---

## 1. Why this file matters

`run_summary/` is the shared harness inspection/read-model layer.

That layer is important because it is the place where native harness payloads become:

- `SharedRunSummaryEnvelope`
- derived mission state for inspection
- prompt observability summaries
- blocker / waiting / verification summaries

This is downstream from runtime.
It is not runtime law.
It is not review law.
It is not domain logic.

If `build.py` becomes a monolith, the harness gets a new corruption path:

- mixed payload parsing
- mixed family adaptation
- mixed summary inference
- mixed registration glue

all inside one file that feels “convenient” until it quietly turns into a second control center.

---

## 2. Repo reality today

Current package:

```text
backend/harness/run_summary/
  __init__.py
  models.py
  build.py
```

Current `build.py` responsibilities include:

- top-level public builders
  - `build_registered_run_summary`
  - `build_orchestration_kernel_run_summary`
  - `build_mission_flow_run_summary`
- orchestration-kernel payload extraction
- mission-flow payload extraction
- prompt observability derivation
- mission-state construction
- resolution-state parsing
- generic coercion helpers
- builder registration

That is all coherent at a high level, but it is too much to keep in one file forever.

---

## 3. The real problem

The problem is **not** that `build.py` is impure in the old sense.
It is not currently smuggling domain/family semantics back into the harness.

The problem is that it mixes too many levels of responsibility:

1. public entrypoints
2. family-specific payload adaptation
3. shared summary derivation helpers
4. state construction helpers
5. registration glue

That creates three risks:

- future changes will add “just one more helper” until the file becomes load-bearing spaghetti
- orchestration and mission-flow logic will accidentally couple more tightly than they should
- inspection logic will become harder to test in focused slices

So this is a **modularity / drift prevention** refactor, not an anti-corruption rescue.

---

## 4. Non-negotiable rules

### 4.1 Stay inspection-only

`run_summary/` must remain a derived read-model surface.

It must not start owning:

- runtime decisions
- review policy
- domain logic
- semantic closure judgments
- cross-family policy law

### 4.2 No new genericness violations

Do not reintroduce:

- product IDs
- mapping-specific fields
- family-specific fields
- alternate legacy wire-key parsing

### 4.3 Split by responsibility, not by aesthetics

Do not create wrapper museums.

Every new module must have an obvious job.
If a file exists just to bounce one function to another file, that is not a win.

### 4.4 Keep orchestration and mission-flow adaptation separate

Those are the natural seams.
They should not share one giant adaptation body forever.

### 4.5 Keep shared helpers genuinely shared

If a helper is only used by orchestration-kernel logic, it belongs with orchestration-kernel logic.
Do not over-promote helpers into “shared” modules just because that looks tidy.

---

## 5. Target shape

Recommended package shape:

```text
backend/harness/run_summary/
  __init__.py
  models.py
  build.py                # tiny public entrypoints only
  orchestration.py        # orchestration-kernel payload -> SharedRunSummaryEnvelope
  mission_flow.py         # mission-flow payload -> SharedRunSummaryEnvelope
  mission_state.py        # mission-state / resolution-state construction helpers
  prompt_observability.py # prompt summary derivation helpers
  common.py               # truly shared coercion helpers only
```

This is the preferred direction, not a commandment that every file must appear immediately.

Minimum acceptable split:

- `build.py`
- `orchestration.py`
- `mission_flow.py`
- `common.py`

If mission-state and prompt-observability helpers still make those files too heavy, then split further.

---

## 6. Responsibilities by module

### 6.1 `build.py`

Should become a thin public surface only:

- `build_registered_run_summary`
- `build_orchestration_kernel_run_summary`
- `build_mission_flow_run_summary`
- registration calls

This file should not contain long payload-derivation bodies.

### 6.2 `orchestration.py`

Own only orchestration-kernel adaptation:

- payload unwrapping for `orchestration_kernel`
- trace-event-derived summaries
- orchestration run artifact extraction
- orchestration resolution-state handling

This is where orchestration-specific inference belongs.

### 6.3 `mission_flow.py`

Own only mission-flow adaptation:

- parse `mission_flow`
- derive summaries from `MissionObservation`
- translate mission cycles / transitions / posture into the read model

This is where mission-flow-specific mapping belongs.

### 6.4 `mission_state.py`

Own shared mission-state construction helpers:

- `_mission_state_from_components`
- resolution-state construction from payload dictionaries

This should stay generic and reusable by both family builders.

### 6.5 `prompt_observability.py`

Own prompt-event summarization only:

- summary from native payload
- summary from trace events

This keeps prompt-observability shaping from staying buried in a giant mixed file.

### 6.6 `common.py`

Own only truly shared small coercion helpers:

- `_as_dict`
- `_as_dict_list`
- `_as_str`
- `_as_int`
- `_as_bool`
- `_as_str_list`
- `_first_non_empty`
- `_event_kind`
- maybe `_as_terminal_class`

Do not move logic here unless it is actually shared.

---

## 7. What should stay out of this refactor

This refactor should **not** also try to:

- rename `mission_flow`
- rename `orchestration_kernel`
- redesign `MissionState`
- redesign tracing
- redesign review bundles
- add legacy compat readers
- add product- or domain-specific fields

Keep it bounded.
This is a file/package-shaping leg.

---

## 8. Recommended sequence

1. Move shared coercion helpers into `common.py`
2. Move prompt observability helpers into `prompt_observability.py`
3. Move mission-state / resolution-state helpers into `mission_state.py`
4. Move orchestration-kernel build path into `orchestration.py`
5. Move mission-flow build path into `mission_flow.py`
6. Reduce `build.py` to public entrypoints + registration only
7. Run the harness suite

This order keeps the public API stable while shrinking the hotspot gradually.

---

## 9. Required tests during the refactor

This refactor should not land on “looks cleaner.”
It should land on preserved behavior.

At minimum, keep or add direct tests for:

- orchestration-kernel run-summary build
- mission-flow run-summary build
- prompt observability from trace events
- prompt observability from payload-native summary
- mission-state / resolution-state derivation

Relevant test targets:

- `backend/harness/run_summary/test_build_orchestration.py`
- `backend/harness/run_summary/test_build_mission_flow.py`

And re-run:

- `pytest backend/harness -q`

---

## 10. Definition of done

This refactor is done when:

1. `build.py` is a thin public surface, not the main logic host
2. orchestration-kernel adaptation and mission-flow adaptation live in separate modules
3. shared helpers live in obvious homes
4. no genericness or wire regressions are introduced
5. the harness suite stays green
6. the resulting package is easier to extend without immediately regrowing a monolith

---

## 11. One-line operating rule

Split `run_summary/build.py` into honest inspection-layer modules so orchestration adaptation, mission-flow adaptation, shared state construction, and prompt observability stop cohabiting one expanding file.
