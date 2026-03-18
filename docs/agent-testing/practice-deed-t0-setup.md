# Practice Deed — t0 Transcription Setup

## What t0 is

**t0 is the initial transcription event.** It is completely separate from the transcript-edit kernel
loop. t0 takes the raw deed image, sends it through the application's OCR/LLM transcription
pipeline (`gpt-o4-mini`, redundancy=3), and writes the resulting draft JSON files to disk.

This page is only the upstream fixture setup. For the broader loop purpose, closure model, and
test success criteria, see `docs/agent-testing/transcript-edit-loop-holistic-intent.md`.

The transcript-edit loop takes t0's output **as input** — it does not know about, or call, the
image pipeline. The dossier and its transcript artifacts are **created by t0**, not pre-existing.

```
practice_deeds/legal_text_image.jpg
          │
          │  t0 (gpt-o4-mini, redundancy=3)
          ▼
dossiers_data/views/transcriptions/live-validation-practice-legaltext/
    draft_legal_text_image/raw/
        draft_legal_text_image_v1.json
        draft_legal_text_image_v2.json   ← seed for the edit loop
        draft_legal_text_image_v3.json
          │
          │  transcript-edit kernel loop
          ▼
   audit → repair → promote (with HITL range-conflict prompt)
```

---

## When to run t0

Run t0 **once** to create the canonical practice fixture. Re-run it only if the fixture data is
deleted or corrupted. Once the `draft_legal_text_image_v2.json` seed file exists under the
canonical dossier directory, `--tx-scenario practice_legaltext` resolves it automatically and
you can run the edit loop as many times as you want without re-running t0.

---

## Prerequisites

1. **venv active**: `.\.venv\scripts\activate.ps1` (from `C:\projects\Plattera`)
2. **Backend running**: in one terminal, `cd backend && python main.py` (listens on `localhost:8000`)
3. **Practice deed image** at its canonical location: `C:\projects\Plattera\practice_deeds\legal_text_image.jpg`

---

## Run t0 — PowerShell

```powershell
# From repo root C:\projects\Plattera — backend must be running in another terminal

$imagePath = "practice_deeds\legal_text_image.jpg"
$dossierID = "live-validation-practice-legaltext"

curl.exe -s -X POST "http://localhost:8000/api/dossier/process" `
  -F "file=@$imagePath" `
  -F "dossier_id=$dossierID" `
  -F "model=gpt-o4-mini" `
  -F "redundancy=3" `
  -F "auto_llm_consensus=false" `
  | python -m json.tool
```

**This is the canonical t0 configuration. Do NOT change `model=gpt-o4-mini` or `redundancy=3`.**

Expected response (success):
```json
{
  "status": "success",
  "metadata": {
    "dossier_id": "live-validation-practice-legaltext",
    "transcription_id": "draft_legal_text_image",
    ...
  }
}
```

---

## Run t0 — Bash / Git Bash

```bash
cd /c/projects/Plattera

curl -s -X POST "http://localhost:8000/api/dossier/process" \
  -F "file=@practice_deeds/legal_text_image.jpg" \
  -F "dossier_id=live-validation-practice-legaltext" \
  -F "model=gpt-o4-mini" \
  -F "redundancy=3" \
  -F "auto_llm_consensus=false" \
  | python -m json.tool
```

---

## What t0 creates

After a successful t0 run:

```
backend/dossiers_data/views/transcriptions/
  live-validation-practice-legaltext/
    draft_legal_text_image/
      raw/
        draft_legal_text_image_v1.json
        draft_legal_text_image_v2.json   ← canonical seed file
        draft_legal_text_image_v3.json
```

> **Note:** `transcription_id` is auto-derived from the uploaded filename:
> `legal_text_image.jpg` → stem `legal_text_image` → `transcription_id = draft_legal_text_image`.
> The three `_v1 / _v2 / _v3` files are the three redundancy drafts from gpt-o4-mini.

---

## Verify the fixture

```powershell
# From backend/
Get-ChildItem dossiers_data\views\transcriptions\live-validation-practice-legaltext -Recurse -Filter "*.json" | Select-Object Name
```

You should see at minimum `draft_legal_text_image_v2.json`. If so, the scenario resolver will
find it automatically and `--tx-scenario practice_legaltext` is ready to use.

---

## After t0: run the edit loop

Once the fixture exists, run the transcript-edit kernel loop:

```powershell
cd C:\projects\Plattera\backend

python -m api.mission_runtime_cli `
  --initial-mode transcript_edit `
  --objective "audit and repair legal text transcript" `
  --mission-id row1 `
  --tx-scenario practice_legaltext `
  --tx-validation-mode live_hitl `
  --tx-max-iterations 12 `
  --done-file tmp\done_row1.json `
  > tmp\result_row1.json 2> tmp\err_row1.txt
```

See `docs/agent-testing/transcript-edit-loop-cli-testing.md` for the full watch/inject cycle.

---

## Model and redundancy are sacred

| Parameter | Value | Why |
|-----------|-------|-----|
| `model` | `gpt-o4-mini` | Canonical t0 model — do not change |
| `redundancy` | `3` | Three drafts required for the range-conflict scenario to surface |

The `draft_legal_text_image_v2.json` seed used by the edit loop comes from the second of three
redundancy drafts. Changing the model or redundancy count changes the output content and may
eliminate the 74 vs 75 range conflict that the live-hitl validation scenario requires.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Connection refused` on curl | Backend not running | Start `python main.py` in another terminal |
| `{"detail": "Invalid file type..."}` | Wrong file path | Confirm `practice_deeds/legal_text_image.jpg` exists |
| `status: "error"` in response | Pipeline error | Check backend terminal for stack trace |
| `--tx-scenario practice_legaltext` still fails after t0 | Wrong dossier_id used | The `dossier_id` in the curl must be exactly `live-validation-practice-legaltext` |
| `draft_legal_text_image_v2.json` missing, only v1 and v3 | Partial processing failure | Re-run t0; inspect backend logs |

---

## Links

- Holistic test intent and success criteria: `docs/agent-testing/transcript-edit-loop-holistic-intent.md`
- Edit loop test guide: `docs/agent-testing/transcript-edit-loop-cli-testing.md`
- Live validation scenario: `docs/transcript-edit-live-validation-path-2026-03-08.md`
- Transcription endpoint: `backend/api/endpoints/dossier/dossier_image_processing.py`
- Scenario resolver: `backend/harness/mission_runtime/cli_support.py` → `resolve_tx_scenario()`
