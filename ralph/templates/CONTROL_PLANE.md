# Control Plane & Permissions

## What this is

`loop_state.json` is a machine-readable control plane intended for a future runner. It exists at:
`ralph/runs/<run_id>/loop_state.json`

It records the loop's current mode and review/steering signals. Human-readable evidence lives in:
- `review.md` (review pass output)
- `steering.md` (steering decisions and changes)

## Deterministic review → steering rule

1. Review may set `steering_requested: true` when drift is detected.
2. Once true, the next iteration is steering mode.
3. Steering runs once and clears the flag (runner may validate/clear).

## Cadence source of truth

Cadence configuration lives in `prd.json` under `loop_settings`.
`loop_state.json` stores dynamic state (counters, last-review iteration, flags).
If cadence fields exist in both places, the runner should treat `prd.json` as authoritative.

## Review ↔ loop_state consistency (invariant)

If `STEERING_NEEDED: yes`, set `steering_requested: true` and keep reasons aligned.
If `STEERING_NEEDED: no`, ensure `steering_requested: false`.
After steering completes, clear `steering_requested` and record changes in `steering.md`.

## Permissions matrix (by mode)

### Worker mode

Allowed:
- Implement code changes
- Update `progress.md`
- Update `SUMMARY.md`
- Write iteration transcript
- Flip story `passes` fields
- Add per-story notes

Disallowed:
- Editing `loop_state.json`
- Restructuring PRD (split/merge/reorder story list)
- Editing VISION/North Star docs (except tiny typo fixes)
- Changing `loop_settings`

### Review mode

Allowed:
- Write `review.md`
- Set `steering_requested` in `loop_state.json`
- Update global verification notes
- Flag drift or risk

Disallowed:
- Implementing features (except tiny documentation fixes)

### Steering mode

Allowed:
- Write `steering.md`
- Restructure PRD (split/merge/reorder)
- Adjust acceptance criteria for clarity
- Update VISION docs if needed
- Clear `steering_requested`

Disallowed:
- Large feature implementation (keep changes small and structural)
