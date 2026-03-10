# Agent-Engine Ergonomics Theory

This document captures a design principle that has become increasingly important as Plattera's agent loops become more capable:

**the seam between the agent and the engine should fit the agent's natural action grammar as closely as possible, so long as that grammar is sane, deterministic, and structurally supportable.**

This is not an argument for making the engine fuzzy, permissive, or vague. It is an argument for designing action contracts that match how the agent naturally and repeatedly tries to express correct intent.

---

## 1. Core Principle

When the agent repeatedly expresses the same action in a consistent, intelligible shape, that is strong design signal.

If the shape is:

- semantically clear,
- deterministic to parse,
- conflict-free,
- easy to validate,
- and compatible with runtime execution rails,

then the contract should usually evolve toward that shape rather than forcing the agent through an awkward, unnatural notation forever.

In short:

- The agent should not need to "speak with an accent" just to use the engine.
- The engine should accept action forms that are natural to the agent, provided they remain mechanically reliable.

This is the **agent ergonomics** principle.

---

## 2. The Sidewalk-on-the-Dirt-Path Rule

Sometimes a system is designed one way on paper, but the actual user repeatedly chooses a nearby, more natural path.

That is not always user error. Often it is design feedback.

For agent systems, the same thing happens:

- the engine defines one canonical request shape,
- the agent repeatedly emits a nearby but more natural structure,
- the runtime rejects it,
- and the loop pays avoidable friction costs.

When this happens consistently, the right question is not:

> "How do we force the model to obey the original contract?"

The right question is:

> "Is the model revealing a better contract surface?"

If the answer is yes, we should pave that path.

This does **not** mean:

- accepting arbitrary malformed payloads,
- guessing at meaning,
- or allowing ambiguous shorthand.

It means:

- identify recurring sane patterns,
- bless them deliberately,
- normalize them internally if useful,
- and reject only what remains ambiguous or unsafe.

---

## 3. Why This Matters

### 3.1 Reduces artificial loop friction

Many loop failures are not reasoning failures. They are seam failures:

- the agent knew what it wanted,
- but expressed it in a shape the engine did not accept.

That wastes:

- iterations,
- invalid-payload budgets,
- wall time,
- and operator attention.

### 3.2 Keeps the agent truly agentic

If the contract is overly awkward, the engine quietly regains authorship over the loop because the runtime has to script around the agent's repeated formatting failures.

That moves the system back toward:

- scripted investigation,
- hidden corrective shims,
- and brittle pre-authored flows.

A better-fitting contract preserves the intended architecture:

- agent chooses intent,
- runtime executes with rails.

### 3.3 Improves structural honesty

If the runtime constantly has to translate obvious near-miss agent intent into the "real" shape, that is often a sign the public contract and the true ergonomic contract have diverged.

That divergence should usually be corrected, not hidden forever.

---

## 4. Three Layers of Action Shape

Agent loops usually have three distinct layers:

### 4.1 Agent-natural form

How the agent instinctively tries to express an action.

Example:

- nested operation-specific payloads,
- shorthand use of current active artifact,
- action-specific target objects instead of generic mode wrappers.

### 4.2 Accepted contract form

The officially supported external interface the runtime accepts.

This should be:

- explicit,
- bounded,
- documented,
- and aligned with repeated sane agent behavior.

### 4.3 Internal execution form

The normalized shape runtime code actually uses to execute deterministically.

This may still be canonicalized for implementation simplicity even after the accepted contract becomes more ergonomic.

That is fine.

The important thing is:

- internal normalization as an implementation detail is healthy,
- but forcing an awkward external contract forever when the natural agent form is clearly better is not.

---

## 5. When To Adapt the Contract

We should adapt the engine's accepted action form when all of the following are true:

### 5.1 The agent behavior is recurring

Not a one-off malformed payload.

The same or very similar structure should appear across:

- retries,
- runs,
- or adjacent action types.

### 5.2 The intent is unambiguous

The engine should be able to tell what the agent meant without fuzzy inference.

Good:

- `target.mode = "select_region"`
- `target.select_region = {...}`

Bad:

- multiple competing operation keys,
- conflicting mode declarations,
- mixed shorthand that could map to more than one action.

### 5.3 The shape maps cleanly to safe execution

The runtime must still be able to:

- validate inputs,
- enforce rails,
- persist artifacts,
- and produce deterministic results.

### 5.4 The shape does not collapse important distinctions

If a shorthand removes required meaning in a way that creates ambiguity, it should not become the accepted contract.

Example:

- if two active artifacts exist, "use the current one" is too vague,
- but if exactly one active artifact exists for the focused decision key, implicit reuse may be acceptable.

---

## 6. When Not To Adapt the Contract

We should **not** adapt to every natural-seeming model behavior.

Reject or keep as invalid when:

- the behavior is inconsistent,
- the shape is ambiguous,
- the intent conflicts across fields,
- the shorthand would force runtime guesswork,
- the meaning depends on hidden state not safely recoverable,
- or the pattern weakens safety rails.

The goal is not "be forgiving."

The goal is:

**be glove-fitting where the agent is repeatedly sane, and strict where the meaning is uncertain.**

---

## 7. Preferred Design Pattern

When an agent-natural shape is good enough to support, prefer this pattern:

1. Observe the raw emitted payloads in live runs.
2. Confirm the pattern is recurring and coherent.
3. Decide whether that pattern should become:
   - the new accepted contract, or
   - a supported ergonomic alias.
4. Normalize internally into one execution shape if useful.
5. Keep validation strict after normalization.
6. Add regression tests using the real emitted payloads.

This keeps the system:

- evidence-based,
- structurally explicit,
- and responsive to the agent's actual behavior.

---

## 8. Where This Applies Especially Strongly

This theory matters most in surfaces where the agent is doing high-frequency action authoring.

### 8.1 Evidence requests

If the agent repeatedly expresses:

- image evidence,
- span evidence,
- dependency requests,

in a certain operation-first form, the contract should likely support that form.

### 8.2 Visual investigation

Visual workflows especially benefit from ergonomic action forms because the agent reasons iteratively:

- select region,
- refine region,
- verify region,
- reuse crop for HITL.

If the agent naturally expresses crop adjustments as "here is the better box," that may be more faithful than forcing every adjustment into a transform-language first.

### 8.3 Artifact reuse

If the agent clearly means:

- "use the current selected region,"
- "verify the crop I just chose,"

the runtime should consider whether an explicit artifact handle is still required, or whether a narrow unambiguous default can be supported.

### 8.4 HITL action expression

If the agent repeatedly frames the next useful action as:

- "ask the human to resolve this exact blocker using this exact crop,"

the contract and prompt surface should preserve that directness rather than routing it through awkward generic prompt wrappers.

---

## 9. Runtime Rails Still Matter

Agent ergonomics is **not** anti-rail.

The runtime must still own:

- deterministic validation,
- bounds checks,
- artifact persistence,
- transcript/version scoping,
- blocker/ticket state transitions,
- retry/repeat budgets,
- and terminal policy.

The runtime should adapt the **shape of accepted intent**, not surrender the responsibility of safe execution.

This distinction is critical:

- **agent owns intent**
- **runtime owns realization**

The engine should become easier for the agent to drive, not looser about what actually happens.

---

## 10. Practical Heuristic

When reviewing a repeated agent failure, ask:

### Question A

Did the agent choose the wrong action?

If yes:

- improve reasoning context,
- improve evidence visibility,
- or improve move guidance.

### Question B

Or did the agent choose the right action, but express it in a shape the engine made awkward?

If yes:

- this is likely an ergonomics problem,
- and the contract may need to move toward the agent.

This is the core diagnostic split.

---

## 11. Design Bias for Plattera

For Plattera's long-running agent loops, the bias should be:

- strict rails,
- explicit persistence,
- deterministic runtime realization,
- but contract surfaces that are increasingly aligned with how the agent naturally and repeatedly expresses sane intent.

This helps the system become:

- less brittle,
- less retry-heavy,
- more agentic,
- and more structurally honest.

The end goal is not merely valid JSON.

The end goal is a loop where:

- the agent can think naturally,
- the engine can execute reliably,
- and the seam between them is tight enough that very little intent is lost in translation.

---

## 12. Summary

**Agent ergonomics theory** means:

- treat recurring sane agent action shapes as design signal,
- adapt accepted contracts toward those shapes when safe,
- keep one deterministic execution model underneath,
- and preserve strict rails after normalization.

Put differently:

**Do not make the agent contort itself to fit a contract that the engine could easily learn to fit instead.**

Where the agent consistently walks a sensible path, pave it.
