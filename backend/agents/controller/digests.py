from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from time import time
from typing import Any

from pydantic import BaseModel, Field

from config.paths import agent_kernel_artifacts_root

from .controller_guardrails import _flatten_latest_refs_payload

_MAX_DIGEST_BYTES = 2048
_MAX_NOTES = 3
_MAX_NOTE_CHARS = 160
_MAX_EXCERPT_CHARS = 220


class IterationDigest(BaseModel):
    iter: int = Field(..., ge=1)
    result: str = Field(..., max_length=64)
    proposed: dict[str, object] = Field(default_factory=dict)
    failure: dict[str, object] | None = None
    correction: dict[str, object] | None = None
    progress: dict[str, object] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list, max_length=_MAX_NOTES)


def build_fallback_iteration_digest(*, seed: dict[str, object]) -> dict[str, object]:
    iter_no = int(seed.get("iter", 0) or 0)
    proposal = seed.get("proposal") if isinstance(seed.get("proposal"), dict) else {}
    outcome = seed.get("outcome") if isinstance(seed.get("outcome"), dict) else {}
    progress = seed.get("progress") if isinstance(seed.get("progress"), dict) else {}
    context_inputs = seed.get("context_inputs") if isinstance(seed.get("context_inputs"), dict) else {}
    action_type = str(proposal.get("action_type", "unknown"))
    args = proposal.get("args") if isinstance(proposal.get("args"), dict) else {}
    outcome_kind = str(outcome.get("kind", "unknown"))
    reason_code = outcome.get("reason_code")
    latest_refs = progress.get("latest_refs") if isinstance(progress.get("latest_refs"), dict) else {}
    flat_lr = _flatten_latest_refs_payload(latest_refs)
    new_refs: list[str] = []
    for k, v in flat_lr.items():
        if isinstance(v, str) and v.strip():
            new_refs.append(str(k))
        elif isinstance(v, dict):
            p = v.get("artifact_path")
            if isinstance(p, str) and p.strip():
                new_refs.append(str(k))
    notes: list[str] = []
    if context_inputs.get("deed_text_full"):
        notes.append("inputs.deed_text_full is present; avoid OPEN_ARTIFACT for deed text unless missing.")
    if action_type == "open_artifact" and not args:
        notes.append("OPEN_ARTIFACT requires artifact_ref|artifact_path|corpus_entry_ref.")
    digest = IterationDigest(
        iter=max(1, iter_no),
        result=outcome_kind,
        proposed={"action_type": action_type, "args_keys": sorted(str(k) for k in args.keys())},
        failure=(
            {
                "reason_code": str(reason_code) if reason_code is not None else None,
                "missing_inputs": outcome.get("missing_inputs", []),
            }
            if outcome_kind in {"controller_refusal", "kernel_refusal", "parse_failed"}
            else None
        ),
        correction={
            "next_step_skeleton": {
                "action_type": action_type,
                "args": _digest_correction_args(action_type=action_type, context_inputs=context_inputs),
            }
        },
        progress={"phase_hint": seed.get("phase_hint"), "new_refs": new_refs[:4]},
        notes=[_bounded_note(n) for n in notes[:_MAX_NOTES]],
    )
    return _bound_digest_dict(digest.model_dump(mode="json"))


def persist_iteration_digest(
    *,
    request_id: str,
    session_id: str,
    iteration: int,
    digest: dict[str, object],
) -> tuple[str, str]:
    root = agent_kernel_artifacts_root() / "iteration_digests" / request_id
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{session_id.replace(':', '_')}_iter_{iteration:03d}.json"
    payload = _bound_digest_dict(dict(digest))
    fd, tmp_path = tempfile.mkstemp(prefix="iter_digest_", suffix=".json", dir=str(root))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.replace(tmp_path, str(path))
        except PermissionError:
            with path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
    excerpt = _build_digest_excerpt(payload)
    return str(path), excerpt


def _build_digest_excerpt(digest: dict[str, object]) -> str:
    proposed = digest.get("proposed") if isinstance(digest.get("proposed"), dict) else {}
    action = str(proposed.get("action_type", "unknown"))
    result = str(digest.get("result", "unknown"))
    failure = digest.get("failure") if isinstance(digest.get("failure"), dict) else {}
    reason = str(failure.get("reason_code", "") or "")
    text = f"iter={digest.get('iter')}; action={action}; result={result}; reason={reason}".strip("; ")
    return text[:_MAX_EXCERPT_CHARS]


def _bound_digest_dict(digest: dict[str, object]) -> dict[str, object]:
    out = dict(digest)
    notes = out.get("notes")
    if isinstance(notes, list):
        out["notes"] = [_bounded_note(str(n)) for n in notes[:_MAX_NOTES]]
    encoded = json.dumps(out, ensure_ascii=True).encode("utf-8")
    if len(encoded) <= _MAX_DIGEST_BYTES:
        return out
    if isinstance(out.get("notes"), list):
        out["notes"] = [str(n)[:80] for n in list(out["notes"])[:1]]
    encoded = json.dumps(out, ensure_ascii=True).encode("utf-8")
    if len(encoded) <= _MAX_DIGEST_BYTES:
        return out
    progress = out.get("progress")
    if isinstance(progress, dict):
        progress["new_refs"] = list(progress.get("new_refs", []))[:1]
    failure = out.get("failure")
    if isinstance(failure, dict):
        failure["missing_inputs"] = list(failure.get("missing_inputs", []))[:2]
    encoded = json.dumps(out, ensure_ascii=True).encode("utf-8")
    if len(encoded) <= _MAX_DIGEST_BYTES:
        return out
    return {
        "iter": out.get("iter"),
        "result": out.get("result"),
        "proposed": out.get("proposed"),
        "failure": out.get("failure"),
        "correction": out.get("correction"),
        "progress": {"phase_hint": (out.get("progress") or {}).get("phase_hint") if isinstance(out.get("progress"), dict) else None},
        "notes": list(out.get("notes", []))[:1] if isinstance(out.get("notes"), list) else [],
        "truncated": True,
        "created_at_epoch_seconds": int(time()),
    }


def _digest_correction_args(*, action_type: str, context_inputs: dict[str, object]) -> dict[str, object]:
    deed_ref = context_inputs.get("deed_text_artifact_ref")
    dossier_id = context_inputs.get("dossier_id")
    if action_type == "open_artifact":
        return {"artifact_ref": deed_ref or "<inputs.deed_text_artifact_ref>"}
    if action_type == "draft_ir":
        return {
            "dossier_id": dossier_id or "<inputs.dossier_id>",
            "deed_text_artifact_ref": deed_ref or "<inputs.deed_text_artifact_ref>",
        }
    return {}


def _bounded_note(value: str) -> str:
    return value if len(value) <= _MAX_NOTE_CHARS else value[: _MAX_NOTE_CHARS - 14] + "...[truncated]"
