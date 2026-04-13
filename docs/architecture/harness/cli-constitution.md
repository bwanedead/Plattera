# CLI Constitution

This document defines the architectural role of the harness CLI.

Its purpose is to prevent another recurring confusion:

- treating the CLI as if it were part of harness semantic law
- letting CLI conveniences become the practical source of run behavior
- confusing testing-workflow mechanics with the meaning of the underlying
  harness

The CLI is a control plane over the harness.
It is not the harness itself.

---

## 1. Core Rule

The CLI may expose, observe, and trigger harness behavior.
It must not define the semantic meaning of that behavior.

That means:

- the CLI may launch runs
- the CLI may watch run status
- the CLI may surface logs, prompts, and artifacts
- the CLI may submit human answers

That does not mean:

- the CLI defines what `HITL` means
- the CLI defines whether a run is paused vs complete
- the CLI defines domain workflow law
- the CLI defines closure semantics
- the CLI becomes the canonical source of mission lifecycle truth

If a behavior only exists in the CLI and not in the generic harness/runtime, it
is a control-plane feature, not harness law.

---

## 2. Intended Role

Today the CLI is primarily a testing and operator surface.

It exists so:

- coding agents can start and observe live runs without getting stuck inside one
  foreground process
- operators can inspect logs and artifacts
- human feedback can be submitted during testing

Future expansion is allowed.
The CLI may grow into a broader utility or communication surface, including an
operator seam for external tools or agent systems.

That broader future still follows the same rule:

- the CLI exposes harness capabilities
- it does not redefine harness semantics

---

## 3. What The CLI May Own

The CLI may own:

- command-line argument parsing
- background process spawning conveniences
- operator-friendly watch/status commands
- run-state mirrors for CLI operations
- log and artifact discovery helpers
- human-answer submission commands
- convenience formatting for testing and inspection

These are control-plane mechanics.

---

## 4. What The CLI Must Not Own

The CLI must not own:

- the meaning of `wait_for_human`
- whether answered blocking `HITL` should resume the run
- domain-specific tool or prompt semantics
- semantic interpretation of human answers
- domain closure law
- mission completion law

If a run resumes after human feedback, that resume should be because the
**harness runtime** says the paused run resumes when its active blocking prompt
is answered.

It should not be because the CLI is secretly implementing a separate workflow
species.

---

## 5. Relationship To The App And Other Control Planes

The live app, the CLI, and any future MCP/operator layer should sit on top of
the same harness semantics.

That means:

- the same logical run lifecycle should hold whether a run is driven from the
  app or the CLI
- a CLI workaround must never be mistaken for the intended product behavior
- if current implementation gaps force a temporary operator ritual in the CLI,
  that ritual should be documented as temporary implementation reality, not as
  harness law

The control plane may differ.
The harness semantics should not.

---

## 6. Background Worker Rule

The CLI may use background workers, watchers, or other process-management
helpers so testing agents are not blocked by a foreground process.

Those helpers exist to make testing possible.
They do not change the meaning of the run.

So:

- a background worker is a CLI implementation detail
- a watch command is a CLI implementation detail
- a status command is a CLI implementation detail

But:

- whether a run is logically running, waiting, resumed, completed, failed, or
  exhausted is harness/runtime truth

---

## 7. Current-Reality Rule

When current CLI workflow differs from the intended harness lifecycle:

- document the gap explicitly
- keep the gap out of constitutional meaning
- treat the gap as a refactor target, not as desired architecture

The CLI may temporarily expose awkward mechanics while the harness catches up.
Those mechanics are not the final truth of the system.
