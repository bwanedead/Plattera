# agents.md Ethos — Compounding Knowledge in the Codebase

## Purpose
`agents.md` files are **local, persistent memory** for both humans and coding agents. They exist to capture the **non-obvious truth** about a part of the repo: the things that are easy to forget, hard to infer, and expensive to relearn.

The goal is simple: **reduce repeated mistakes and repeated discovery cost**.

When an agent (or a human) touches a folder weeks later, they should not have to rediscover:
- why the folder exists
- what invariants it must preserve
- how to run/test it correctly
- which files are generated vs hand-edited
- what footguns exist

Instead, the folder itself contains the local “sticky note” that prevents the next agent from stepping on the same rake.

---

## What compounding means (the core idea)
Every iteration of work produces learning:
- “This test fails unless you run generator X first.”
- “This API contract is relied on by 4 modules.”
- “This folder uses a weird naming convention for a reason.”
- “This file looks editable but is actually generated.”

Without a mechanism to store that learning, agents re-learn it repeatedly and make the same mistakes repeatedly.

`agents.md` is the mechanism that turns learning into **compounding leverage**:
- Each mistake becomes a note.
- Each note prevents future mistakes.
- Over time, the repo becomes easier to work in, even for fresh agents with fresh context windows.

This is especially important for “Ralph-style” loops where each iteration is a new context: the *only* durable memory is the repo itself.

---

## Why local folder-level notes (instead of one big doc)
A single monolithic “how this repo works” document becomes:
- stale
- too long to read
- too general to be useful in the moment

Local `agents.md` files keep knowledge **close to the code it governs**.

When you open a folder, you see the rules of that folder. This has three benefits:
1) **High relevance:** only the instructions you need for that area
2) **Low cognitive load:** short notes beat long manuals
3) **Natural maintenance:** when code changes, you update the note in the same commit

---

## What belongs in `agents.md` (high-value knowledge)
`agents.md` should store **high-signal operational truth**, such as:

### Contracts & invariants
- “This parser must remain deterministic.”
- “Offsets are in raw text space only.”
- “Do not change field X without updating Y.”

### Commands / workflows
- “Run this generator before tests.”
- “Use these commands for lint/test/build.”

### Gotchas / footguns
- “These files are generated—do not hand-edit.”
- “This module assumes timezone-naive timestamps.”
- “This endpoint must remain backward compatible.”

### Allowed changes
- “Safe to refactor internals, but do not change exported API.”
- “Do not move these files; import paths are relied on.”

### Links to truth
- Pointers to deeper docs or specs relevant to this folder.

---

## What does NOT belong (avoid noise)
To keep `agents.md` powerful, it must stay compact. Avoid:
- generic philosophy
- re-stating obvious code
- long design essays
- speculative notes (“might be useful later”)
- duplicating repo-wide rules already covered by `CLAUDE.md`

`agents.md` is for **sharp edges and crisp constraints**, not narrative.

---

## When to create/update an `agents.md`
Create or update an `agents.md` only when you learn something that will likely matter again:

- You hit a confusing failure and figure out the fix
- You discover a hidden dependency or ordering constraint
- You learn an invariant that must remain stable
- You discover a generated-file boundary
- You find a “do not touch this casually” zone

If the knowledge would prevent the *next* agent from repeating a mistake, it belongs.

---

## Style rules (how it should read)
- Short, bullet-heavy, factual
- Written as instructions to a capable dev who is new to this folder
- Prefer “Do X / Don’t do Y” over vague advice
- Use repo-relative paths, not absolute paths
- Keep under ~30–50 lines when possible

---

## Success criteria (how we know it’s working)
A good `agents.md` produces these outcomes:
- New agents ramp faster
- Fewer repeated mistakes across iterations
- Refactors are safer because constraints are explicit
- The codebase becomes more “self-describing” over time

If the repo feels like it is “teaching the agent how to work in it,” the system is working.

---

## Standard template (recommended)
Use a consistent structure so agents can scan quickly:

# agents.md

## Scope
- Folder: `<relative/path/>`
- Purpose: `<1–2 bullets>`

## Contracts & invariants
- `<bullets>`

## Allowed changes
- `<safe changes>`
- `<don’t-change-casually>`

## Commands
- Test: `<command>`
- Lint: `<command>`
- Build/Run: `<command>`

## Gotchas
- `<bullets>`

## Links
- Docs: `<relative/path/to/doc.md>`
- Related code: `<relative/path/>`

Keep it lean. Make it real. Make it prevent mistakes.
