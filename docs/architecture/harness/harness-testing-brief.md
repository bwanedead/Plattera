# Harness Testing Brief

This brief defines the testing suite the shared harness needs before we treat it as rock solid infrastructure for live domain workflows.

Its job is to answer four questions:

- what the harness already verifies well
- what is still untested or under-tested
- what test layers are required for confidence
- what the definition of done is before we consider the harness hardened

This is not a generic “add more tests” note.
It is a concrete testing map for the current harness tree.

---

## 1. Purpose

The harness is now structurally sane enough to build on.

That means the next risk is no longer obvious architecture corruption.
The next risk is **false confidence**:

- mechanics drift without being noticed
- read models silently misparse payloads
- traces lose fidelity
- review bundles misrepresent runs
- orchestration and mission coordination remain green in isolation but fail in composition

The testing suite must prove that the harness is:

- generic
- mechanically correct
- composition-safe
- observable
- stable under future refactors

---

## 2. Current Test Reality

Current harness tests cover:

- `backend/harness/test_mission_flow.py`
  - mission coordinator record shape
  - adapter lookup
  - transition validation/application
  - mission identity carriage
  - terminal handoff
  - immutability of coordinator-owned record views

- `backend/harness/test_mission_flow_capabilities.py`
  - transition capability rejection
  - typed mode-context execution adapter flow

- `backend/harness/runtime/run/test_progress.py`
  - mechanical progress evaluation

- `backend/harness/test_architecture_guardrails.py`
  - banned vocabulary does not return
  - removed harness paths do not reappear
  - key shared shapes stay generic
  - hotspot files do not silently bloat

This is useful, but it is still a **narrow** suite.

The current suite mostly proves:

- the mission coordinator works
- one small progress helper works
- architectural drift is being watched

It does **not** yet prove the end-to-end accuracy of:

- run loop behavior
- canonical trace building
- run summary derivation
- review bundle assembly
- live composition across run -> trace -> summary -> review

---

## 3. Testing Principles

### 3.1 Test mechanics, not semantic doctrine

Tests should verify:

- shape
- invariants
- transitions
- preservation of data
- bounded generic behavior

Tests should **not** encode:

- domain-specific meaning
- mapping-specific readiness logic
- hidden semantic staging
- deterministic authored mission truth

### 3.2 Prefer fixture-backed composition tests at boundaries

The highest-value tests are not just unit tests.
They are boundary tests proving:

- emitted payloads can be normalized
- normalized traces can be summarized
- summaries can be reviewed
- shared state remains generic throughout

### 3.3 Keep the suite layered

The harness should have explicit tests at four layers:

1. structure / architecture guardrails
2. unit tests for core mechanics
3. adapter / parser / builder integration tests
4. end-to-end harness composition tests

---

## 4. Required Test Surface

### 4.1 Runtime / run

Target files:

- `backend/harness/runtime/run/orchestrator.py`
- `backend/harness/runtime/run/trace_collector.py`
- `backend/harness/runtime/run/hitl_transport.py`
- `backend/harness/runtime/run/loop_memory.py`

What is missing:

- bounded loop behavior tests
- terminal-before-action tests
- action-plan execution tests
- wait-for-human behavior tests
- skip-execution behavior tests
- latest-ref / active-item continuity updates
- trace-event emission assertions
- opaque run-context carriage assertions

Recommended test module:

- `backend/harness/runtime/run/test_orchestrator.py`

Minimum cases:

1. initializes pack, syncs state, chooses action, executes one step, emits trace events
2. terminal evaluation exits without action execution
3. `wait_for_human=True` returns waiting terminal posture without execution
4. `skip_execution=True` iterates without session action execution
5. latest refs and active item propagate into continuity
6. `opaque_run_context` is carried but never interpreted

### 4.2 Runtime / mission observability

Target files:

- `backend/harness/runtime/mission/observability.py`
- `backend/harness/runtime/mission/registry.py`
- `backend/harness/runtime/mission/cli_support.py`

What is missing:

- mission observation payload round-trip tests
- required field presence tests
- cycle summary preservation tests
- opaque adapter payload carriage tests
- native wire shape validation tests

Recommended test module:

- `backend/harness/runtime/mission/test_observability.py`

Minimum cases:

1. `to_payload()` produces native `mission_flow` shape only
2. `parse_mission_observation_payload()` round-trips a native payload
3. cycle summaries, transition history, and posture summaries survive round-trip
4. `opaque_adapter_payload` is preserved exactly
5. malformed payloads fail clearly

### 4.3 Tracing

Target files:

- `backend/harness/tracing/service.py`
- `backend/harness/tracing/builder.py`
- `backend/harness/tracing/adapters/kernel_direct.py`
- `backend/harness/tracing/adapters/mission_flow.py`
- `backend/harness/tracing/rationale_continuity_strip.py`

What is missing:

- family detection tests
- ambiguity detection tests
- native payload validation tests
- kernel-direct canonicalization tests
- mission-flow canonicalization tests
- rationale strip derivation tests

Recommended test modules:

- `backend/harness/tracing/test_service.py`
- `backend/harness/tracing/test_kernel_direct.py`
- `backend/harness/tracing/test_mission_flow_adapter.py`
- `backend/harness/tracing/test_rationale_continuity_strip.py`

Minimum cases:

1. `build_canonical_trace_from_payload()` detects `mission_flow`
2. `build_canonical_trace_from_payload()` detects `orchestration_kernel`
3. ambiguous payload shape fails clearly
4. kernel-direct adapter preserves run/request/session IDs, terminal snapshot, and event count
5. mission-flow adapter preserves mission ID, cycle index, transitions, and high-signal refs
6. rationale strip only derives from current execution-phase events

### 4.4 Run summary

Target files:

- `backend/harness/run_summary/build.py`
- `backend/harness/run_summary/models.py`

What is missing:

- orchestration-kernel summary builder tests
- mission-flow summary builder tests
- prompt observability summary tests
- mission-state derivation tests
- malformed payload failure tests

Recommended test modules:

- `backend/harness/run_summary/test_build_orchestration.py`
- `backend/harness/run_summary/test_build_mission_flow.py`

Minimum cases:

1. orchestration payload builds a native `SharedRunSummaryEnvelope`
2. mission-flow payload builds a native `SharedRunSummaryEnvelope`
3. prompt observability derives from trace events when present
4. prompt observability falls back to payload-native summary when trace events do not contain prompt events
5. generated `MissionState` remains generic (`opaque_payload`, no product fields)
6. malformed payloads fail clearly

### 4.5 Review

Target files:

- `backend/harness/review/tool.py`
- `backend/harness/review/reporting.py`

What is missing:

- single-run review bundle tests
- multi-run review bundle tests
- mixed-family aggregate behavior tests
- prompt-event extraction tests
- file-output helper tests

Recommended test modules:

- `backend/harness/review/test_tool.py`
- `backend/harness/review/test_reporting.py`

Minimum cases:

1. single-run review bundle contains trace, run summary, review, and prompt events
2. multi-run review bundle aggregates run families and statuses correctly
3. prompt-event extraction preserves `pack_id`, prompt IDs, and surfaces
4. `maybe_write_review_output()` writes deterministic JSON
5. partial traces are reflected correctly in review output

### 4.6 End-to-end harness composition

This is the highest-value missing layer.

The harness needs one or two full composition tests that prove the layers work together, not just independently.

Recommended module:

- `backend/harness/test_harness_composition.py`

Minimum cases:

1. **orchestration-kernel composition**
   - start from a native orchestration payload or a tiny fake loop artifact
   - build canonical trace
   - build run summary
   - build review bundle
   - assert stable IDs, loop family, terminal class, and prompt-event visibility

2. **mission-flow composition**
   - start from a native mission-flow payload
   - build canonical trace
   - build run summary
   - build review bundle
   - assert mission identity, cycle count, terminal posture, and opaque payload carriage

These tests should be short and fixture-backed.
They are not meant to simulate the whole application.
They are meant to prove the harness trunk composes correctly.

---

## 5. Fixture Strategy

The harness should keep a small set of native canonical fixtures under:

- `backend/harness/test_fixtures/harness_regression_pack/`

Recommended fixture additions:

- native orchestration-kernel payload with prompt events
- native orchestration-kernel payload with wait-for-human posture
- native mission-flow payload with at least one transition
- native mission-flow payload with terminal handoff

Fixture rules:

- native wire only
- no superseded key shapes
- names should match current architecture vocabulary
- keep fixtures small and inspectable

---

## 6. Test Commands

With repo venv active:

- full harness suite
  - `pytest backend/harness -q`

- architecture gate only
  - `pytest backend/harness/test_architecture_guardrails.py -q`

- future focused slices
  - `pytest backend/harness/tracing -q`
  - `pytest backend/harness/run_summary -q`
  - `pytest backend/harness/review -q`

If directory-local test packages do not exist yet, create them as part of the suite build-out.

---

## 7. Suggested Build Order

Build the missing suite in this order:

1. tracing service + adapters
2. run summary builders
3. review/reporting
4. runtime/run orchestrator behavior
5. end-to-end composition tests

Why this order:

- tracing, run summary, and review are the least covered and most likely to silently drift
- orchestrator behavior should be tested after the downstream inspection surfaces exist
- composition tests should lock the whole trunk after the lower-level pieces are covered

---

## 8. Definition Of Done

The harness testing suite is “ready to build on” when:

1. architecture guardrails stay green
2. mission coordinator and progress tests stay green
3. tracing service and both native adapters have direct tests
4. run summary builders have direct tests
5. review tooling has direct tests
6. at least one orchestration-kernel composition path and one mission-flow composition path are covered end to end
7. fixtures are native-only and named in current harness vocabulary

At that point, the harness is not just architecturally clean.
It is also **verified enough** to serve as the substrate for live domain workflows.

---

## 9. One-Line Operating Rule

Before building more domain behavior on top of the harness, finish the missing tests that prove the generic trunk can emit, normalize, summarize, and review its own native payloads without semantic drift or silent loss of fidelity.
