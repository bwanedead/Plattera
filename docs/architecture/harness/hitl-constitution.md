# HITL Constitution

This document defines the architectural law for human-in-the-loop (`HITL`)
transport in the Plattera harness.

Its purpose is to prevent a recurring knot:

- treating human feedback as a CLI-only testing feature
- treating blocking human waits as mission completion
- treating manual operator restart rituals as if they were intrinsic harness law
- letting deterministic runtime code semantically "use" human feedback on the
  agent's behalf

The core idea is simple:

- human feedback exists to let the agent ask for minimal-effort human input when
  that input is genuinely needed
- the harness owns transport and lifecycle mechanics around that input
- the agent owns whether the input is needed, how blocking it is, and what it
  means once it arrives

---

## 1. Core Rule

Human feedback is a **generic harness transport and lifecycle rail**.

It is not:

- a CLI-only trick
- a transcript-edit-only feature
- a semantic decision engine
- a substitute for agent investigation

The harness may:

- carry prompt requests
- carry human answers
- persist waiting state
- resume a paused run mechanically

The harness must not:

- decide whether the answer semantically resolves the case
- decide what the answer means for domain closure
- decide that the answer has been substantively incorporated merely because the
  answer arrived

That semantic incorporation remains agent-authored.

---

## 2. Purpose Of HITL

The purpose of `HITL` is to let the human do the smallest justified amount of
work needed to unblock or improve the run.

Preferred bias:

- short question
- bounded choices
- lowest practical human effort

Examples:

- two-button choice when the human just needs to pick one of two realities
- three-button choice when "unsure" or "other nuance" matters
- optional note/freeform only when bounded choices are not enough

The existence of `HITL` does not mean the run should overuse human labor.
It exists for cases where the agent cannot honestly or efficiently proceed
without human-provided knowledge or judgment.

---

## 3. Two HITL Species

The harness supports exactly two generic `HITL` postures.

### 3.1 Async request

This means:

- the agent wants human input
- that input is useful
- but the run can still do other meaningful work meanwhile

Generic shape:

- `hitl_request != null`
- `wait_for_human = false`

Required behavior:

- emit the request
- keep the logical run moving
- expose the eventual answer on later turns when it arrives

There is no pause/resume concept here because the run never stopped.

### 3.2 Blocking wait

This means:

- the agent has determined the current run is genuinely paused on human input
- there is not enough justified work left to keep moving honestly without that
  answer

Generic shape:

- `hitl_request != null`
- `wait_for_human = true`

Required behavior:

- emit the request
- pause the logical run
- when the active blocking prompt is answered, resume the run automatically

Blocking `HITL` is a pause condition.
It is not mission completion.

---

## 4. Pause And Resume Law

If the agent chooses a blocking human wait:

1. the logical run enters a waiting state
2. the run is not complete merely because the current execution slice stopped
3. the active blocking prompt id becomes part of harness-owned waiting state
4. when feedback arrives for that active blocking prompt, the run resumes
   automatically
5. the next model turn sees the answered feedback and decides what to do with it

The default rule is:

- **answering the active blocking prompt resumes the run**

No additional deterministic semantic test is needed before the next model turn.
If the answer does not truly unblock the case, the model can decide that on the
resumed turn.

Manual restart rituals are not the intended architecture.
If a current implementation requires them, that is an implementation gap, not
the constitutional meaning of `HITL`.

---

## 5. Ownership Map

### 5.1 Agent-owned

The agent must own:

- whether human input is needed
- what question to ask
- whether the request is async or blocking
- how the answer changes the work
- whether the answer resolved, narrowed, or failed to resolve the blocker
- when answered feedback has actually been semantically incorporated

### 5.2 Harness-owned

The harness may own:

- request normalization and validation
- pending/answered transport state
- active blocking prompt tracking
- waiting-state persistence
- mechanical pause/resume lifecycle
- delivery of answered feedback into later prompts

### 5.3 Control-plane-owned

Control planes such as CLI, app UI, viewer, or future MCP surfaces may own:

- how prompts are displayed
- how answers are captured
- how status is shown to the operator

They must not own:

- the meaning of `wait_for_human`
- the semantic decision to resume or not resume after answer
- the interpretation of the answer

Control planes are views and ingress points over harness law.
They are not alternate species of harness semantics.

---

## 6. Anti-Patterns

The following are architectural failures:

- treating blocking `HITL` as equivalent to mission completion
- requiring a human or CLI operator to manually "know" that a resume should
  happen after an answer
- making CLI behavior define the meaning of `HITL`
- deterministically interpreting the human answer inside the harness
- deciding that answered feedback has been integrated merely because transport
  state advanced
- using `HITL` as a substitute for available in-run investigation

If human feedback arrives and the next model turn never happens, the harness is
missing lifecycle behavior.
If the next turn happens but the harness has already semantically decided what
the answer means, the harness has violated authorship.

---

## 7. Current-Reality Rule

When implementation and constitution differ:

- the constitution defines the intended architecture
- current gaps should be documented explicitly as temporary implementation
  reality
- those gaps must not be mistaken for desired harness law

The correct long-term reading is:

- async `HITL` keeps working
- blocking `HITL` pauses and auto-resumes when answered
- semantic incorporation of the answer remains agent-authored
