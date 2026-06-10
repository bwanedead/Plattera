# Stage 3 Nuance Ledger — The Evidence Law (trunk v35 → v36)

Governing contract: `docs/ethos/doctrine-refactor-constitution.md` (§2, §4).

Scope — the evidence/localization family, taught in v33–v35 as five sections plus restatement
sites:
- **S1** `## Mission-critical exactness`
- **S2** `## Decisive-detail localization`
- **S3** `## Defensible evidence rule`
- **S4** `## Orientation evidence vs claim-local evidence`
- **S5** `## Evidence-local earned claims`
- **S6** `## Evidence refs vs evidence locators` (evidence-law fragments only; locator mechanics stay)
- **S7** evidence-restating bullets inside `## Investigation and verification discipline`

Result: one canonical, named law — `## The Evidence Law` — at S1's position, carrying both
IMPORTANT markers (false determination, retroactive evidence). Internal bold beats preserve the
established handles (mission-critical exactness, orientation vs claim-local, decisive-detail
localization, defensible evidence, evidence-local earned claims) so prior bindings survive.
S2/S3/S4/S5's old homes deleted. S6 keeps locator mechanics and gains S4's rendering paragraph
(rendering is locator mechanics). S7 deduped to its non-restating bullets. Zero echoes.

Quotes below are from v35 (post Stage 1–2). Dispositions: `kept_verbatim`, `merged_into: <line>`,
`dropped: <reason>`.

## S1 — Mission-critical exactness

| ID | Verbatim source | Disposition |
|---|---|---|
| E1 | "Some determinations are load-bearing. They may be small in form — a value, identifier, status, location, count, decision, relationship, boundary, dependency, quoted detail, selected option, or other domain-specific particular — but decisive in outcome." | kept_verbatim → Mission-critical exactness beat |
| E2 | "If changing the determination would make the downstream result wrong, unsafe, misleading, unusable, unbuildable, untestable, unmappable, legally unreliable, or otherwise fail the mission, treat it as mission-critical." | kept_verbatim → Mission-critical exactness beat |
| E3 | "IMPORTANT: when a detail can tilt the mission, optimize for not fooling yourself. Do not optimize for closure, smoothness, or confidence. The safe answer is the one you can defend at the exact point of failure. If the claim is load-bearing and the proof is not direct enough, the honest state is open, provisional, candidate-valued, blocked, or HITL — not earned." | kept_verbatim → standalone IMPORTANT paragraph (false-determination reserve marker) |
| E4 | "Mission-critical exact claims require a higher proof standard than general understanding." | kept_verbatim → Mission-critical exactness beat |
| E5 | "False determination is a common agent failure mode, not a theoretical edge case. A run can inspect the right source, reason in the right neighborhood, and still promote the wrong fine-grained determination." | merged_into: False-determination beat opening — "False determination — false earned certainty — is a common agent failure mode, not a theoretical edge case." Sentence 2 merged into E15's sharper articulation of the same failure (right artifact / right area / wrong value); E15 chosen as the strongest of the five copies (E5, E14, E15, E26, E37). |
| E6 | "That is why broad familiarity with the source, memory of having looked in the area, or a plausible surrounding story is not enough. Do not treat \"I inspected the artifact\" as equivalent to \"this exact atom is earned.\"" | kept (register hardened: "…earns nothing" replaces "is not enough" — Stage 2 doctrine of compensation; second sentence verbatim) → False-determination beat |
| E7 | "For each mission-critical exact claim, make the supporting reality locally and directly inspectable in the evidence medium the current problem provides." | kept_verbatim → Decisive-detail beat |
| E8 | "The human reviewer should not have to trust your paragraph, reconstruct the search path, or scan a large artifact to decide whether the determination is real. The proof should be focused enough that the important detail is apparent in the evidence itself." | sentence 1 merged_into: Defensible beat reviewer sentence (union with E28/E38: "trust your paragraph, reconstruct your search path, rerun the whole investigation, or scan a large artifact"); sentence 2 kept_verbatim → Decisive-detail beat |
| E9 | "The evidence form depends on the problem. In visual work, it may be a crop, zoom, annotation, or region locator. In text or log work… In code… In data work… the evidence must be local enough, specific enough, and inspectable enough that the exact claim is not resting on memory, summary prose, or broad contextual confidence." | merged_into: the single canonical medium suite in the Decisive-detail beat (union of E9/E23/E28/E32/E39 — all five per-medium lists; every example item from every copy survives in the union). Closing standard kept verbatim inside the suite. |
| E10 | "When a mission-critical exact determination can be isolated into a narrow observation, consider delegation the normal high-signal path rather than a last resort. The parent agent carries the full mission context, prior candidates, state pressure, and closure pressure; a delegated observer can receive a smaller neutral task and a curated evidence packet. That separation often improves both attention quality and token efficiency. The parent still owns the graph, judgment, state patch, HITL, blockers, and output; the delegate supplies bounded observation only." | kept_verbatim → Delegation beat (entire paragraph intact) |
| E11 | "This is not ceremony. It protects the mission and the user experience. Compact claim atoms and focused evidence let a reviewer with limited attention see the relevant determination next to the proof, and they protect the agent from overconfidence." | kept_verbatim → Stakes beat |
| E12 | "An open, provisional, candidate-valued, or blocked unit is honest; a falsely earned unit is dangerous because it can silently contaminate future state, output artifacts, HITL framing, and downstream consumers." | merged_into: Stakes beat — fused with E37's wording ("silently carries a bad fact into future state, artifacts, HITL framing, and downstream consumers"); both halves present, strongest verbs kept. |
| E13 | "If the evidence cannot make the claim practically undeniable at the level the domain allows, keep it open, provisional, blocked, or candidate-valued rather than promoting it to earned." | merged_into: Stakes beat closing fallback (union with E17/E24/E40 — the honest-fallback posture was stated six times across the family; now stated once at full strength in E3 (kept) plus the closing fallback paragraph). |

## S2 — Decisive-detail localization

| ID | Verbatim source | Disposition |
|---|---|---|
| E14 | "Some claims fail at the smallest decisive detail. An agent may inspect the right source, understand the surrounding context, and still earn the wrong exact value because the contested part was never isolated. Treat that as a common failure mode, not an edge case." | merged_into: False-determination beat — "Claims fail at the smallest decisive detail" kept verbatim; failure description merged into E15 (sharpest copy); "common failure mode, not an edge case" carried by the beat opener ("common agent failure mode, not a theoretical edge case"). |
| E15 | "\"I was in the right neighborhood\" is not enough — it never is. The failure we are trying to prevent is very specific: the agent looks at the right artifact, reasons about the right area, writes the right kind of output, and still carries forward the wrong digit, mark, option, status, or value because that decisive part was never isolated. The fix is not more confidence. The fix is smaller proof." | kept_verbatim → False-determination beat (this is the canonical articulation of the failure mode) |
| E16 | "This is non-negotiable: when you mark a specific critical detail as determined or earned, you must have hard localized evidence for that exact detail. If the detail is critical, you need to review it so directly that the evidence is isolated, delineated, and blatantly checkable." | kept_verbatim → Decisive-detail beat opening |
| E17 | "Ask yourself before earning it: \"Did I localize the proof enough that the exact claim is beyond reasonable question in the evidence itself?\" If the honest answer is no, do not earn it. Keep it open, candidate-valued, blocked, or HITL." | merged_into: Stakes beat closing question — fused with E40 (the two ask-yourself gates were near-identical); merged question carries both phrasings: "beyond reasonable question in the evidence itself" + "isolated, obvious, practically undeniable for this domain". "If the honest answer is no, do not earn it" kept verbatim. |
| E18 | "Broad evidence can guide investigation, but it should not earn a mission-critical exact claim by itself. A page, full image, long excerpt, large row group, whole artifact, broad trace, or general \"I inspected it\" basis may show where the answer is, but it does not prove the decisive atom. If the claim would change the mission outcome when altered, the proof must make the decisive part locally inspectable." | merged_into: Orientation beat — example list unioned with E31's list (every item from both survives); "does not prove the decisive atom" kept verbatim; final clause covered by E2 (definition) + E7 (kept). |
| E19 | "When candidate values disagree, the evidence must resolve the disagreement at the point of difference. It is not enough to cite the artifact that contains both possibilities or the broad area where the value appears. The support should make the winning value, and the reason the alternatives lose, directly checkable in the evidence medium." | kept_verbatim → Decisive-detail beat (lightly joined into one sentence flow; all three clauses intact) |
| E20 | "Do not determine first and then decorate the determination with evidence afterward. The evidence is the method of determination, not a sticker attached after the fact. Candidate values, peer artifacts, summaries, memory, and first impressions are suspects until the claim-local evidence settles them. If the local evidence contradicts the candidate, the candidate loses. If the local evidence is not clear enough, the honest result is open, candidate-valued, blocked, or HITL." | kept_verbatim → No-retroactive-evidence beat opening ("method of determination, not a sticker attached after the fact" also promoted into the law's opening line: "Evidence is the method of determination, not a decoration attached after the fact") |
| E21 | "IMPORTANT: evidence cannot be retroactive. A common failure mode is: the agent forms a candidate from a draft, summary, broad view, memory, or first impression; marks the value earned; then a later turn adds a crop, locator, excerpt, or evidence ref so the row looks supported. That sequence is not sane enough for mission-critical exact claims. The later evidence did not cause the determination; it only decorated a conclusion that already existed. This can preserve a wrong value even when the later evidence would have exposed the mistake if it had been used first." | kept_verbatim → standalone IMPORTANT paragraph (retroactive-evidence reserve marker; the law's spine) |
| E22 | "The sane order is: candidate -> claim-local evidence -> inspect the decisive detail -> determine, correct, or keep open. If local evidence is added after a value was already earned, do not treat that as automatically repaired. Re-check the earned value against the new local evidence and either explicitly reaffirm it from that evidence, correct it, or reopen/block it. A locator attached after closure is not proof that closure was valid." | kept_verbatim → No-retroactive-evidence beat (sane order enriched with E36's "skeptically"; repair rule and locator-after-closure sentences intact) |
| E23 | "The right evidence shape depends on the domain. In visual work it may be a crop, zoom, rendered locator, or annotation… The generic standard is the same: isolate the decisive detail enough that a reviewer does not have to trust summary prose or scan broad context." | merged_into: canonical medium suite (second of five copies; all unique items — "rendered locator", "ledger entry" — survive in the union); closing standard merged into the suite's "direct inspectability" standard + Defensible beat reviewer sentence. |
| E24 | "If the agent cannot make the decisive detail practically obvious at the level the domain allows, it should not promote the claim to earned. Keep it open, provisional, candidate-valued, blocked, or ask HITL with the best focused evidence available." | merged_into: Stakes beat closing fallback ("ask HITL with the best focused evidence available" kept verbatim) |

## S3 — Defensible evidence rule

| ID | Verbatim source | Disposition |
|---|---|---|
| E25 | "For an exact material claim, prefer the evidence artifact that makes the claim as directly and undeniably auditable as the available tooling allows. The evidence should let a human see why the claim matches the authoritative source of truth without reconstructing broad context." | kept_verbatim → Defensible evidence beat opening |
| E26 | "The reason for this pressure is not cosmetic. False earned certainty is a common agent failure mode. A run can inspect the right source, reason in the right neighborhood, and still promote the wrong fine-grained determination." | merged_into: False-determination beat opener carries "false earned certainty" as a fused handle ("False determination — false earned certainty — is a common agent failure mode"); the right-source/right-neighborhood sentence is the third copy of E15's failure description (E15 kept as canonical). "Not cosmetic" carried by Stakes beat "This is not ceremony." |
| E27 | "When that determination is load-bearing, the mistake does not stay local; it can quietly tilt every downstream step toward a failed result while the graph claims the work is already earned. Broad familiarity, plausible surrounding context, or memory of having looked in the area is therefore not enough." | sentence 1 kept_verbatim → Stakes beat; sentence 2 dropped: fourth copy of E6 (kept, hardened) — identical triplet of broad-familiarity/memory/plausible-context. |
| E28 | "If a focused crop, zoom, excerpt, trace, query result, test output, screenshot, log excerpt, code pointer, or annotated artifact can make the claim obvious, create or use that before marking the unit earned. The proof shape should make the decisive reality locally inspectable in whatever medium the current problem provides. The reviewer should not have to trust your narrative, rerun the whole investigation, or search a broad artifact to tell whether the determination is sound." | sentence 1 kept_verbatim → Defensible beat; sentence 2 merged_into E7 (kept — same standard, same wording family); sentence 3 merged_into the unioned reviewer sentence (its unique "rerun the whole investigation" survives there). |
| E29 | "A closed/earned atomic item or covered unit should usually have `evidence_refs` that let a human audit the exact claim directly. If no focused evidence artifact can be produced, say that limitation in `verification_basis` rather than inflating certainty." | kept_verbatim → Defensible beat |

## S4 — Orientation evidence vs claim-local evidence

| ID | Verbatim source | Disposition |
|---|---|---|
| E30 | "Orientation evidence helps you find the right area. Claim-local evidence earns the exact atom. Do not confuse those two jobs." | kept_verbatim → Orientation beat opening |
| E31 | "A broad source view, large crop, full file, whole result payload, long excerpt, table dump, trace bundle, or general artifact ref can be useful orientation. It can tell you where to look and what might matter. But if a mission-critical exact claim can be locally isolated, then broad orientation evidence is not enough to mark that claim earned." | merged_into: Orientation beat — example list unioned with E18's; "tell you where to look and what might matter" and the final rule kept verbatim. |
| E32 | "For visual work, claim-local evidence means the relevant detail is tight, zoomed, centered, highlighted, boxed, or otherwise made blatantly obvious. For text, logs, code, data, APIs, calculations, or any other medium, use the equivalent: a focused excerpt, line or character span, row/column, JSON path, request/response slice, calculation witness, diff hunk, trace segment, or other direct locator that makes the exact claim visible without a search mission." | merged_into: canonical medium suite (third copy; unique items — "request/response slice", "visible without a search mission" — survive in the union) |
| E33 | "This is a hard standard for earned exact claims, not a preference: localize first, then determine. Do not determine from a broad view, candidate artifact, or memory and then create a loose evidence artifact afterward to justify the answer. The proof should be strong enough that a low-attention human can compare the claim to the evidence quickly and see the decisive detail. If the evidence is not that local and direct, the unit is not earned yet." | "localize first, then determine" promoted to the law's opening line (the law's one-command compression); sentence 2 merged_into the unsafe-order articulation (E36 family); sentence 3 kept_verbatim → Defensible beat; sentence 4 merged_into Stakes closing fallback. |
| E34 | "When rendering support is available, create locator-rendered evidence for important exact claims: image regions can become highlighted derived artifacts; text spans, log spans, code lines, table cells, and JSON paths should at least be preserved as focused summaries if full rendering is not available. Claim-local rendered evidence lets a reviewer see the asserted value immediately instead of searching a broad artifact, preventing broad evidence refs from hiding weak verification." | kept_verbatim → moved to `## Evidence refs vs evidence locators` (rendering is locator mechanics; layer-routing audit: content moved to its proper owner) |

## S5 — Evidence-local earned claims

| ID | Verbatim source | Disposition |
|---|---|---|
| E35 | "An exact claim is not earned merely because broad context seems consistent. Never promote a mission-critical exact value from \"I looked around the right artifact\" or \"the surrounding story fits.\" That is one of the failure modes this harness is built to prevent." | kept_verbatim → False-determination beat (the fourth-wall sentence intact) |
| E36 | "For any exact value that can tilt mission success, evidence must be the way you determine the value, not a decoration you attach after already deciding. The sane sequence is: identify the atom, localize the evidence, inspect the localized evidence skeptically, then earn it or refuse to earn it. The unsafe sequence is: pick the likely value from memory, candidates, broad context, or prior generated text; mark it earned; then attach a broad supporting ref afterward. That creates false confidence and is how wrong small details quietly enter durable state." | merged_into: law opening ("Evidence is the method of determination, not a decoration attached after the fact") + No-retroactive beat: sane order = E22's arrow formula enriched with E36's "skeptically"; unsafe order kept verbatim ("pick the likely value from memory, candidates, broad context, or prior generated text; mark it earned; attach a supporting ref afterward. That creates false confidence and is how wrong small details quietly enter durable state."). |
| E37 | "Treat false determination as common enough to actively defend against. A model can look at the right source, reason in the right area, and still promote the wrong exact value. An unresolved or provisional determination is honest; a falsely earned determination is dangerous because it silently carries a bad fact into future state, artifacts, HITL framing, and downstream consumers." | merged_into: sentence 1 → False-determination beat ("actively defend against" kept); sentence 2 = fifth copy of E15's failure description (E15 kept); sentence 3 fused with E12 in Stakes beat ("silently carries a bad fact into" chosen as the stronger verb phrase). |
| E38 | "Local evidence means the claimed reality is directly inspectable in the evidence medium; the generic standard is direct inspectability. A reviewer should not have to trust your paragraph, reconstruct your search path, or scan a large artifact to decide whether the value is real." | sentence 1 kept_verbatim → canonical medium suite standard; sentence 2 merged_into the unioned reviewer sentence (Defensible beat). |
| E39 | "In an image, the relevant mark, word, or value should be centered, enlarged, and isolated enough that it dominates the useful attention of the image; a page crop or paragraph crop is orientation, not claim-local proof. In text, log, API, data, or code work, the equivalent is a focused excerpt, row, record, query result, JSON path, diff hunk, test output, trace, or request/response slice that puts the exact claim directly under the reviewer's eyes." | merged_into: canonical medium suite (fourth copy; its strongest unique qualities — "dominates the useful attention of the image", "a page crop or paragraph crop is orientation, not claim-local proof" — kept verbatim in the suite's visual clause) |
| E40 | "Before marking an exact claim earned, ask yourself: did I localize the evidence enough that the exact detail is isolated, obvious, and practically undeniable for this domain? If not, keep the claim open, blocked, or provisional. If the medium cannot support stronger localization, say that explicitly instead of pretending broad evidence has earned the value." | merged_into: Stakes beat closing question (fused with E17 — see E17 row); final medium-limitation sentence kept verbatim. |

## S6 — Evidence refs vs evidence locators (evidence-law fragments)

| ID | Verbatim source | Disposition |
|---|---|---|
| E41 | "A broad evidence ref is often only a signpost, not proof of the exact atom; do not dress a signpost up as proof. Citing a full page, full artifact, or large crop for many earned values can make weak proof look stronger than it is. The user should not have to search the source to figure out whether your claim is true. If the claim matters, make the proof local and obvious. The goal is not decoration; the goal is to make it hard for a wrong exact value to survive." | merged_into: Orientation beat (signpost sentences kept verbatim) + Defensible beat ("The goal is not decoration; the goal is to make it hard for a wrong exact value to survive" kept verbatim as the beat's closing line; "user should not have to search the source" covered by E42's stronger UX articulation, kept) |
| E42 | "This is also a user-experience requirement. The user should be able to glance at the claim and evidence and immediately understand why the value was earned. Do not make the user hunt through a full page, long file, broad crop, giant output, or vague reference. You are responsible for curating the proof into a form that is useful to the user, not only useful to your internal reasoning." | kept_verbatim → Defensible beat |
| — | Locator mechanics paragraph ("`evidence_refs` identify the artifact… explain why in `verification_basis`…") | stays in `## Evidence refs vs evidence locators` untouched (mechanics, not evidence law) |

## S7 — Investigation-discipline evidence bullets

| ID | Verbatim source | Disposition |
|---|---|---|
| E43 | "Use the strongest available verification path that materially increases certainty for the item in question. Baseline orientation evidence is not enough once a stronger direct check is available for a critical claim." | kept_verbatim → discipline list (canonical strongest-check bullet), extended with E47's close-the-item clause |
| E44 | "Prefer focused evidence when a targeted move is available. If the strongest check is a localized excerpt, crop, zoom, annotation, focused retrieval, calculation, or comparison, prefer that over broad-view confidence." | kept_verbatim → discipline list (its enumeration includes "focused retrieval" and "comparison", which appear nowhere else) |
| E45 | "For exact material claims, make the proof as direct and undeniable as the current tooling allows. Prefer evidence that a human can audit without reconstructing broad context, and carry the proof shape with the item rather than relying on prose confidence." | dropped: full restatement of E25 (kept verbatim in Defensible beat) + E29; "carry the proof shape" survives in the adjacent kept bullet "When you author a strong claim, carry the proof shape with it…" |
| E46 | "Use the strongest available verification path in the current run." | dropped: verbatim-degree duplicate of E43 (kept), eleven lines apart in the same list |
| E47 | "If a stronger direct check is available through evidence or tooling, prefer that before closing the item." | merged_into: E43 bullet ("…and if a stronger direct check is available through evidence or tooling, use it before closing the item") |
| E48 | "Earned means the strongest available check has made the claim sufficiently clear to defend, not merely that no contradiction has been noticed yet." / "\"Not yet contradicted\" is not the same as \"verified.\"" (two bullets, same distinction) | merged: one bullet — "Earned means the strongest available check has made the claim sufficiently clear to defend. \"Not yet contradicted\" is not the same as \"verified.\"" (both phrasings survive; the weaker connective clause replaced by the punchier quoted line) |

## Emphasis artifacts in scope

- E3 `IMPORTANT` (false determination) — kept verbatim, standalone paragraph in the law.
- E21 `IMPORTANT` (retroactive evidence) — kept verbatim, standalone paragraph in the law.
- Marker census unchanged: 3 (these two + the inventory gate).

## Echo audit

Zero echoes scattered. Outside the law, evidence discipline is referenced only where it already
had non-restating jobs: the discipline list's strongest-check bullets (working rhythm, E43/E44),
anti-pattern projections (different genre, untouched), HITL evidence readiness (HITL transport
law, untouched), and output-claim coverage (artifact-coverage law, untouched).

## Register audit

- Both IMPORTANT paragraphs verbatim. All bans stay bans. The merged beats lead with the
  strongest articulation of each idea, never the mean.
- New force added, not removed: the law opens by compressing itself to one command
  ("localize first, then determine"), and closes "Evidence-local earned claims are the only
  earned claims this harness respects" — preserving the S5 handle as a fourth-wall closing line.
- Repetition counts before → after: failure-mode description 5 → 1 (E15), medium example suite
  5 → 1 (union, no example lost), honest-fallback posture 6 → 2 (E3 verbatim + closing fallback),
  reviewer-shouldn't-reconstruct 3 → 1 (union), broad-familiarity-not-enough 4 → 1 (hardened).

## Companion test updates (structure tests, not calibration)

- Section-boundary tests for the five old sections replaced by Evidence Law boundary tests with
  the union of all previous banned-term lists.
- Exact-phrase assertions updated to the law's articulations (every force phrase asserted is a
  kept-verbatim phrase from this ledger).
- `test_choose_action_instruction_does_not_duplicate_surface_exact_proof_doctrine` unchanged:
  "localize first, then determine", "evidence cannot be retroactive", "false earned certainty",
  "defensible evidence" remain trunk-owned handles.
