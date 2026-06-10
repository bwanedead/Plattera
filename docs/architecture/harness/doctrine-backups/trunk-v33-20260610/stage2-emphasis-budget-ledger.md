# Stage 2 Nuance Ledger — Emphasis budget pass (trunk v34 → v35)

Governing contract: `docs/ethos/doctrine-refactor-constitution.md` (§5 Emphasis Budget).

Register changes only; no semantic moves. The trunk carried 9 hard markers (4 IMPORTANT,
5 PLEASE). Budget: ~3, reserved for the highest-stakes failure modes — false determination,
retroactive evidence, the inventory gate. Every removed marker is compensated in wording,
never silently deleted (§5: "compensated, not deleted").

## Marker dispositions

| ID | Section | Verbatim source (marker + guarded clause) | Disposition |
|---|---|---|---|
| M1 | Mission-critical exactness | "IMPORTANT: when a detail can tilt the mission, optimize for not fooling yourself." | **kept** — this is the false-determination reserve slot |
| M2 | Decisive-detail localization | "IMPORTANT: \"I was in the right neighborhood\" is not enough." | marker removed; compensated: "\"I was in the right neighborhood\" is not enough — it never is." |
| M3 | Decisive-detail localization | "PLEASE treat this as non-negotiable: when you mark a specific critical detail as determined or earned…" | marker removed; compensated: "This is non-negotiable: when you mark…" (pleading → flat declaration of law) |
| M4 | Decisive-detail localization (retroactivity paragraph) | "Evidence cannot be retroactive." (carried **no** marker in v33 despite being a named reserve slot) | **marker added**: "IMPORTANT: evidence cannot be retroactive." — the retroactive-evidence reserve slot now actually holds its marker |
| M5 | Compact claim atoms | "IMPORTANT: the work graph is not a notebook." | marker removed; compensated: "Hold this as law: the work graph is not a notebook." |
| M6 | Compact claim atoms | "PLEASE do not close an atomic item while the actual answer is hidden only in prose." | marker removed; compensated: "Do not close an atomic item while the actual answer is hidden only in prose. No exceptions." |
| M7 | Evidence refs vs evidence locators | "IMPORTANT: a broad evidence ref is often only a signpost, not proof of the exact atom." | marker removed; compensated: "A broad evidence ref is often only a signpost, not proof of the exact atom; do not dress a signpost up as proof." |
| M8 | Orientation evidence vs claim-local evidence | "PLEASE treat this as a hard standard for earned exact claims: localize first, then determine." | marker removed; compensated: "This is a hard standard for earned exact claims, not a preference: localize first, then determine." (the marker's priority moved to the retroactivity slot, M4, which is this rule's canonical spine) |
| M9 | Blocker surfacing rule | "PLEASE do not use `no_further_progress` as a way to avoid asking the human." | marker removed; compensated: "Do not use `no_further_progress` as an excuse to avoid asking the human." ("as a way to" → "as an excuse to": names the evasion as evasion) |
| M10 | Inventory Gate And Resolution Motion | "The hard law is simple: if the work universe is `initial` or `partial`…" (carried **no** marker in v33 despite being a named reserve slot) | **marker added**: "IMPORTANT: the hard law is simple. If the work universe is…" — the inventory-gate reserve slot now holds its marker |
| M11 | Evidence-local earned claims | "PLEASE do not promote a mission-critical exact value from \"I looked around the right artifact\" or \"the surrounding story fits.\"" | marker removed; compensated: "Never promote a mission-critical exact value from \"I looked around the right artifact\" or \"the surrounding story fits.\"" (pleading → ban) |

## Final marker census (v35)

3 hard markers, exactly the reserved slots:
1. `IMPORTANT` — false determination (Mission-critical exactness)
2. `IMPORTANT` — retroactive evidence (Decisive-detail localization, retroactivity paragraph)
3. `IMPORTANT` — inventory gate (Inventory Gate And Resolution Motion)

## Register audit

- No guarded clause was softened; every compensation is a flat command, a ban, or a named-law
  declaration — equal or harder than the pleading it replaces.
- All sentence content around the markers is untouched (register-only stage).
- Scarcity restored: the three surviving markers now stand out instead of competing with six
  neighbors.
