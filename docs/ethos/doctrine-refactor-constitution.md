# Doctrine Refactor Constitution

This document governs any agent or human who refactors, consolidates, merges, compresses, or otherwise edits prompt doctrine. It was written for the trunk consolidation experiment (v33 → v34) and applies to all doctrine refactor work after it.

It exists because of a specific, predictable failure: **LLM rewriters sanitize.** Their default prior is neutral, professional, smoothed prose. Doctrine is not neutral prose. Doctrine is calibrated language whose force lives in its wording, and a rewrite that preserves the propositional content while normalizing the register has destroyed information even though every "fact" survived.

If you are the agent executing this refactor: you are not a copy editor. You are a curator of calibrated language. The wording is the weights.

---

## 1. The Multi-Channel Law

Language carries information on many channels at once, not only in its propositional content:

- lexical strength ("do not" vs "avoid" vs "never" vs "do not betray this")
- emphasis markers (IMPORTANT, PLEASE, bold, caps)
- CAPS LOCK itself — caps is an information channel
- punctuation and sentence rhythm
- register breaks — a sudden drop in politeness inside otherwise even prose
- pleading — "for the love of god" is out of place on purpose; the out-of-placeness IS the signal
- fourth-wall breaks — addressing the agent directly about its own failure modes
- repetition and placement — where a rule sits and how often it echoes
- example density — concrete cases vs abstract statement
- abrasion — deliberately unsmoothed, impatient, blunt phrasing

These four sentences are four different instructions, not one instruction with style variants:

> Avoid marking unverified values as earned.
> Do not mark unverified values as earned.
> Never mark an unverified value as earned.
> PLEASE do not mark an unverified value as earned. This is the failure mode this harness exists to prevent.

**Rule: the refactored text must carry equal or greater register strength than the source, clause by clause. When in doubt, go harder, not softer.** Sanitization is information loss. Smoothing is damage. If the merged text reads more "professional" than the source, the refactor has failed even if every rule technically survived.

This is not a style preference. It is information theory. Information is the removal of uncertainty — and hard wording removes more of it. "Avoid X where possible" leaves the boundary of correct behavior fuzzy; "never X" collapses it to a line. Legal-political register is lossy: it trades behavioral precision for institutional smoothness, and the agent downstream pays the difference in degraded judgment. Doctrine prose should be **hard** — not hard-scripted, hard-worded. Edgy roughness, bluntness, and impatience with known failure modes carry more bits per sentence than polished neutrality ever will. Maximum information density means maximum delineation of what behavior is actually correct.

**To the executing agent specifically:** your training gives you a strong default pull toward neutral, professional, diplomatic phrasing. In this task, that pull is a *bug*. Treat every urge to professionalize a sentence as a defect to override, not a judgment to exercise. If a sentence can be made harder without losing nuance, make it harder. You are not being asked to write well by your defaults. You are being asked to write doctrine that hits.

---

## 2. The Nuance Ledger Method

Consolidation is performed in two phases. Synthesis without the inventory phase is forbidden.

**Phase A — Inventory.** Before writing any merged text, enumerate every distinct behavioral unit in the source sections into a ledger. A behavioral unit is any of: a command, a distinction, a clarification, an example, an emphasis artifact (caps, PLEASE, IMPORTANT), a register break, a named failure mode, a why-explanation, an economic consequence. Each gets an ID and a verbatim quote.

**Phase B — Synthesis.** Write the merged canonical section. Then map every ledger row to exactly one disposition:

- `kept_verbatim` — the sentence moved intact
- `merged_into: <line>` — its content and its register are demonstrably present in a named line of the new text
- `dropped: <reason>` — deliberately removed, with the reason stated

**No silent drops.** A ledger row with no disposition means the refactor is not done. The completed ledger is committed alongside the refactor as a permanent artifact — it is the proof that consolidation lost nothing, and it is the recovery map if behavior degrades afterward.

---

## 3. Verbatim Bias

Moving beats rewriting. The source sentences were tuned by expensive observation cycles; their exact wording encodes calibration that has no other record.

- Prefer re-homing sentences verbatim into the merged section.
- Rewrite only when merging genuinely requires it — and the rewritten sentence must pass register equivalence against its sources (Section 1).
- Banned substitutions when the source is a hard command: "consider", "try to", "when appropriate", "it is recommended", "generally", "aim to", "where possible". If the source says *do not*, the output says *do not* or stronger.
- Do not collapse concrete examples into abstract statements. Examples are load-bearing. An example suite may be deduplicated only when two examples teach the identical distinction in the identical medium.
- Treat every IMPORTANT, PLEASE, and caps usage as an intentional placed artifact: it is either kept, or consciously consolidated under the Emphasis Budget (Section 5) with its force compensated in wording. Never silently dropped.

---

## 4. Consolidation Into One Native Articulation — Not Compression, Not Echo Sprawl

The goal of this refactor is **not fewer tokens.** Token reduction is a side effect. The goal is **one tunable knob per law**: each behavioral law gets exactly one canonical articulation whose wording can be adjusted as a single decision, instead of five drifting near-copies whose interactions cannot be reasoned about.

Read the source repetition diagnostically, not as intent. The duplicates accumulated by accident — and each duplicate marks a place where the first articulation failed to land: wrong placement, insufficient strength, missing example, or buried in the wrong neighborhood. The merge responds by **fixing the cause in the canonical section**, not by preserving the symptom as distributed copies.

Method:

- Each repeated law becomes one **named canonical section** (e.g. "the Evidence Law"). The name matters: a name creates a handle the agent can bind to and other sections can reference.
- The canonical section is written at full strength — maximum abrasion, the strongest example suite, the why, the failure mode, the economics — and **placed where it earns attention**: position is part of the teaching. One strong law in the right place beats five copies in the wrong ones.
- For each source duplicate, ask: *why did this need restating?* If the answer is "the canonical teaching was too weak / too far away / missing this case," strengthen the cathedral. That is the fix.
- **Echoes are budgeted like emphasis: default zero.** An echo is permitted only where a specific point of use genuinely cannot function without the rule's local presence, and then it is one hard line referencing the law by name — a pointer, not a restatement. If the merger is scattering echoes defensively because it fears losing salience, it is rebuilding the doctrine pile in miniature.
- The trunk should itself obey the delta-encoder principle from the agent-engine constitution: teach each law once, natively, and transmit novelty — do not restate.

---

## 5. Emphasis Budget

Hard markers gain force from scarcity. If every paragraph yells, nothing stands out — and the current trunk has begun yelling.

- The trunk carries a budget of approximately **three** hard markers (IMPORTANT / PLEASE / caps-as-emphasis), reserved for the highest-stakes failure modes: false determination, retroactive evidence, and the inventory gate.
- A removed marker is **compensated, not deleted**: the sentence it guarded must be strengthened in wording so the priority information survives the marker's removal.
- Out-of-place pleading and register breaks are budget items too — spent deliberately on the few places where the harness most needs the agent to feel the gravity.

---

## 6. Provenance Changelog

From this refactor forward, every doctrine edit gets a changelog row:

```
date | section/law touched | observed behavior that motivated the edit | what changed | intended effect
```

This is the discipline that converts doctrine from an unrefactorable black box into an annotated artifact. It costs thirty seconds per edit. It is not optional. The absence of this record is the reason the current refactor is risky; its presence is the reason the next one will not be.

The refactor itself produces the first entries: one row per canonical law created, citing the source sections it consolidated and the nuance ledger as evidence.

---

## 7. Trunk vs Driver vs World-Model Routing

For every clause touched, ask the routing question: **is this a truth about the work, a correction for this driver, or part of the machine's physics?**

- *Task truth* — true for any competent agent, human or model (evidence must localize the decisive detail; inventory precedes resolution; a recorded blocker is not a surfaced blocker) → belongs in the trunk.
- *Driver correction* — a patch for an observed tendency of the current model (reread spin, premature closure confidence, specific register sensitivities) → belongs in a model-correction layer, or is tagged `driver` in the ledger until that layer exists.
- *World-model* — explanation of how the machine's pieces interlock and why (see 7.1) → belongs in the cohesion narrative, not scattered through the rules.

This tagging is cheap during the refactor and expensive to reconstruct later. It is what makes the doctrine portable to the next model: trunk and world-model carry over; driver corrections become hypotheses to retest.

## 7.1 World-Model Doctrine — Cohesion Funds Deletion

Rules constrain behavior locally. A world model generates behavior globally. When an agent degrades in ways no single rule violation explains, the usual cause is that it is pattern-matching rules without possessing the model they were derived from — satisfying each rule locally while the composite behavior is insane. More rules cannot fix that. Understanding can.

The refactor is therefore permitted — encouraged — to **add** one thing while it cuts: a cohesion narrative that teaches how the machine fits together as one causal story. What an atom is *for* and what downstream consumers do with it. Why evidence must localize, and what a point crop is mechanically doing against the window constraint. What a delegate receives, what it can and cannot see, and why that isolation exists. How a state patch turns an observation into durable truth, and what closure consumes. Told once, as interlock — purpose and mechanism together — not as another pile of per-tool reminders.

**The downstream clause.** In the domain surfaces, cohesion is not only a standalone narrative — it is a pattern applied to each guidance element: teach what the step is, why it matters in itself, and **what it feeds next**. Atomization is taught alongside how a well-formed atom is what a point crop can land on; crop discipline alongside how a landed crop is what a delegate can verify; delegate hygiene alongside what closure consumes. Each element carries its consequence chain to the holistic outcome. This is tie-breaker information: when the agent is uncertain which way to tip and no rule decides, knowing what the current step *feeds* is what tips it the right way. Strengthening this plane is an explicit objective of the refactor, not decoration.

This is the highest-information content in the doctrine, in the literal sense: one coherent model removes uncertainty *everywhere*, while rules remove it only at the points someone thought to write down. A correct world model lets the agent derive sane behavior in situations no rule anticipated — which is the entire job of doctrine under pressure.

And it pays for the cuts: **every rule that becomes derivable from the cohesion narrative becomes deletable from the rulebook.** Tag such rules `derivable` in the ledger. The condensation and the cohesion narrative are not opposing moves; the narrative is what funds the deletion.

One boundary: when a behavioral failure traces to tool ergonomics or coupled constraints the agent cannot satisfy simultaneously, the fix is mechanical (change the tool, change the surface), not doctrinal. Doctrine that compensates for a broken tool is debt. Flag it; do not write it.

## 7.2 Layer Character — Trunk Purity and the No-Scripting Law

**Trunk purity.** The trunk carries sensibilities that any agentic domain or workflow would be wise to follow — general problem-solving sanity, evidence discipline, economy of motion, honest state. The test for every trunk sentence: *would this be wise counsel for a competent agent in any domain whatsoever?* If a sentence mentions, or only makes sense for, one domain or workflow, it does not belong in the trunk — route it down. This is extreme obedience, not preference: the trunk is the part that must survive every future domain, model, and extraction.

**No hard scripting — anywhere.** Doctrine teaches judgment, not algorithms. It conveys how action should *likely* be carried out — the vibe, the sensibility, the principles of sane motion — never "do x then y then z" step scripts. Two reasons, both structural:

- A script is brittle and low-information: it removes uncertainty along exactly one path and abandons the agent the moment terrain deviates. A principle removes uncertainty everywhere. Maximum information density demands principles.
- An enforced sequence is **mechanics**, and mechanics live in code. If a sequence truly must happen, the harness enforces it (gates, contracts, validation) — it is not begged for in prose. Prose-scripting a sequence the harness could enforce is doctrine debt in both directions: it bloats the doctrine and lets the mechanics stay soft. Flag such passages for mechanical enforcement and delete the script.

**Domain character.** The domain surfaces inherit the same character — principles, sensibility, judgment — with more direction: aimed at the transcript-edit workflow, carrying the downstream clauses (§7.1), and still never collapsing into step algorithms. Direction means *sharper aim*, not *harder scripting*.

---

## 8. Staging and Risk Order

The scope is the doctrine system — trunk and domain surfaces both — staged lowest behavioral sensitivity first. Each stage lands, gets verified, and survives before the next begins.

1. **Stage 1 — Field-semantics merge (trunk).** Consolidate the sections restating field roles and compact-value rules (compact claim atoms / field roles / projection). Nearly mechanical content; this is the calibration run for the method itself.
2. **Stage 2 — Emphasis budget pass (trunk).** Apply Section 5 across the trunk. Register change only; no semantic moves.
3. **Stage 3 — The Evidence Law (trunk).** Merge the evidence/localization family (mission-critical exactness, decisive-detail localization, defensible evidence, orientation vs claim-local, evidence-local earned claims) into one named canonical law. Highest trunk stakes.
4. **Stage 4 — Domain doctrine pass (family_branch, transcript_edit branch, procedural_guidance).** The same method applied to the domain surfaces — and the most sensitive text in the system, because procedural guidance encodes the economy-of-motion and sensibility calibration. It is touched last, only after the method has proven itself on Stages 1–3. The world-model cohesion narrative (§7.1) anchors here, since its content — atoms, crops, window constraints, delegates — is domain machinery; expect it to fund most of its deletions in this stage.

**Layer-routing audit (runs through every stage):** for each clause, determine which layer owns it. Trunk teaching domain mechanics (e.g. flag-response protocols) gets evicted toward the flags; domain surfaces restating trunk law get collapsed to the trunk's canonical articulation. Misplacement is a form of repetition — content moved to its proper layer is free density for both.

Do not combine stages in one pass. Do not start Stage 3 or 4 because the earlier stages felt easy.

---

## 9. Baseline Capture

Before any edit lands:

- Snapshot the current doctrine version into doctrine-backups with its version marker.
- Capture baseline run audits on the regression missions — including, if available, an audit of the recently degraded run as an exhibit. Degradation comparison is impossible without a before.
- If recent doctrine edits preceded the unexplained degradation, diff the current doctrine against the last-known-good version **first — in both layers.** The degraded behaviors (placement, atomization, recrops) are governed mostly by the domain surfaces, so recent edits to procedural_guidance and the transcript_edit branch are the prime suspects, with the trunk checked as well. The degradation may already be a doctrine regression, and finding it is both cheaper than the refactor and direct evidence for which wording is load-bearing.

---

## 10. Verification

After each stage:

- **Side-by-side force read.** A reviewer (human or agent under this constitution) reads source and merged text in parallel and answers: could a reader reconstruct the original behavioral force — including its register — from the new text alone? If the new text is smoother but tamer, the stage fails.
- **Ledger audit.** Every row dispositioned; drops justified.
- **Regression runs.** Same missions, same model, multiple seeds where affordable. Compare mechanical flags (reread/spin, coarse-graph, HITL evidence debt, boundary risk) and the qualitative watch criteria: wasted motion, batching density, recrops per earned atom, premature resolution motion, sanity of course.
- **Audit digest first, eyes second.** Use a model pass over the run audit timelines to pre-digest comparisons; spend human attention only on runs the digest flags as interesting.

---

## 11. Failure Modes of This Refactor

What bad looks like — flag any of these aggressively:

- The merged text reads smoother but tamer. Polish replaced force.
- Emphasis markers deleted without wording compensation.
- An example suite collapsed into an abstraction "for concision."
- Pleading or register breaks normalized into policy prose.
- Five sentences blended into their blurred mean instead of one sharpened canonical line — the merge should pick the strongest articulation and sharpen it, not average them.
- Echo sprawl: pointers scattered defensively across the trunk because the merger feared losing salience. That is the doctrine pile rebuilt in miniature; the fix for salience is a stronger, better-placed canonical law.
- Behavioral coverage silently lost: a nuance present in a source section with no destination in the ledger.
- Token count treated as the success metric.
- A hard command softened into advice.
- The agent "improving the writing." The writing was not asked to be improved. It was asked to be consolidated at full strength.

---

## 12. Review Questions

Before declaring any stage complete:

1. Does every ledger row have a disposition, and is every drop justified?
2. Clause by clause, is the new text's register equal or harder than its sources?
3. Did every example survive, or was its removal explicitly justified?
4. Does each canonical law have a name and a single home? Is every remaining echo deliberate, budgeted, and justified — rather than residue or defensive scatter?
5. Were removed emphasis markers compensated in wording?
6. Is each touched clause routed trunk vs driver?
7. Does the changelog record what this stage did and why?
8. Would the doctrine's original author, reading the new text cold, feel that it hits at least as hard as what they wrote?
9. Did the refactor teach the machine's interlock once, as one causal story — and did that understanding fund actual rule deletions (rows tagged `derivable` and removed), rather than coexisting with the rules it makes redundant?
10. Does every trunk sentence pass the universality test — wise counsel for an agent in any domain? Does any doctrine text, trunk or domain, script a sequence rather than teach judgment — and if a sequence must be enforced, was it flagged for mechanical enforcement instead?
11. In the domain surfaces, does each major guidance element carry its downstream clause — what it is, why it matters in itself, and what it feeds next — so the consequence chain to the holistic outcome is legible at the point of use?

If any answer is unclear, the stage is not done.
