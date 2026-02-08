# Reviewer Task — Iteration 14

Run ID: 2026-02-04__feature-graph-ir
Iteration: iter-0014
Review Mode: final

---

## Your Mission

Review the worker's output and determine if the run should continue or stop.

## Files to Review

1. **Worker Summary**: `C:\projects\Plattera\ralph\runs\2026-02-04__feature-graph-ir\phases\worker\iter-0014\output/worker_summary.md`
2. **PRD Progress**: `C:\projects\Plattera\ralph\runs\2026-02-04__feature-graph-ir/prd.json` (check `passes` fields)
3. **Progress Log**: `C:\projects\Plattera\ralph\runs\2026-02-04__feature-graph-ir/progress.md`

## PRD Status

- Total stories: 12
- Completed: 12
- Pending: 0

**All complete?** YES - recommend STOP

---

## Review Checklist

- [ ] Did the worker complete the intended story?
- [ ] Are acceptance criteria met (check prd.json)?
- [ ] Were files changed appropriately?
- [ ] Are there any blockers or concerns?
- [ ] Should the loop continue or stop?

---

## Decision Rules

**STOP** (decision: "stop") when:
- All stories in prd.json have `passes: true`
- Worker output includes `<promise>TASK COMPLETE</promise>`
- Critical blocker requires human intervention

**CONTINUE** (decision: "continue") when:
- Stories remain with `passes: false`
- Worker made progress but more work needed
- Minor issues that can be addressed next iteration

---

## Required Output

You MUST write your decision to:
  `C:\projects\Plattera\ralph\runs\2026-02-04__feature-graph-ir\phases\reviewer\iter-0014\output/review_result.json`

Schema:
```json
{
  "decision": "continue",
  "confidence": 0.85,
  "message": "Explanation of your decision",
  "stories_complete": 3,
  "stories_remaining": 2
}
```

- `decision`: REQUIRED - must be "continue" or "stop"
- `confidence`: Optional - 0.0 to 1.0
- `message`: Optional - explanation
- Other fields: Optional - any additional data


---
## IMPORTANT: Output Requirements

You MUST write your review decision to:
  `output/review_result.json`

Schema (JSON):
```json
{
  "decision": "continue",  // REQUIRED: "continue" or "stop"
  "confidence": 0.85,      // Optional: 0.0-1.0
  "message": "Explanation of decision",  // Optional
  "artifacts": ["changed/file.py"],      // Optional: list of files
  "data": {}               // Optional: any additional data
}
```

- Set `decision` to `"stop"` when the work is complete and no more iterations needed.
- Set `decision` to `"continue"` when more work is needed.
- Do NOT print the decision to stdout only - you MUST write the JSON file.
