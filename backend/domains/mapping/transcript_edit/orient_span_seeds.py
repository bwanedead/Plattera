"""Transcript span seeds from orientation outputs (transcript-edit domain)."""
from __future__ import annotations

from typing import Any

from agent_kernel.tooling_artifacts import _read_str
from agent_kernel.tooling_text_spans import _bounded_int

from tooling.mapping.transcription_edit.contracts import (
    Confidence,
    LocatorAnchorsV0,
    TranscriptSpanSeedLabel,
    TranscriptSpanSeedOrigin,
    TranscriptSpanSeedV1,
)


def coerce_orient_span_seed_dict(raw: dict[str, Any]) -> dict[str, Any] | None:
    label_raw = str(raw.get("label") or "misc").strip().lower()
    allowed_labels = {
        "pob",
        "call_chain",
        "plss",
        "tie_to_corner",
        "closure",
        "exception",
        "acreage",
        "misc",
    }
    label = label_raw if label_raw in allowed_labels else "misc"
    start_anchor = str(raw.get("start_anchor") or "").strip()
    end_anchor = str(raw.get("end_anchor") or "").strip()
    if len(start_anchor) < 8 or len(end_anchor) < 8:
        return None
    occurrence = _bounded_int(raw.get("occurrence"), default=1, minimum=1, maximum=200)
    confidence = str(raw.get("confidence") or "medium").strip().lower()
    if confidence not in {"low", "medium", "high"}:
        confidence = "medium"
    return {
        "label": label,
        "confidence": confidence,
        "notes": str(raw.get("notes") or "").strip()[:500] or None,
        "start_anchor": start_anchor[:500],
        "end_anchor": end_anchor[:500],
        "occurrence": occurrence,
    }


def _try_transcript_span_seed_v1(raw_seed: dict[str, Any], *, seq: int) -> TranscriptSpanSeedV1 | None:
    label_value = str(raw_seed.get("label") or "misc")
    try:
        label = TranscriptSpanSeedLabel(label_value)
    except Exception:
        label = TranscriptSpanSeedLabel.MISC
    confidence_value = str(raw_seed.get("confidence") or "medium")
    try:
        confidence = Confidence(confidence_value)
    except Exception:
        confidence = Confidence.MEDIUM
    try:
        return TranscriptSpanSeedV1(
            seed_id=f"seed_orient_{seq:02d}",
            label=label,
            seed_origin=TranscriptSpanSeedOrigin.AGENT,
            seed_confidence=confidence,
            notes=_read_str(raw_seed.get("notes")),
            locator=LocatorAnchorsV0(
                start_anchor=str(raw_seed.get("start_anchor")),
                end_anchor=str(raw_seed.get("end_anchor")),
                occurrence=_bounded_int(raw_seed.get("occurrence"), default=1, minimum=1, maximum=200),
            ),
        )
    except Exception:
        return None


def build_transcript_orient_span_seeds(
    *,
    startup_understanding: dict[str, Any],
    checklist_seed_items: list[dict[str, Any]],
) -> list[TranscriptSpanSeedV1]:
    """Collect span seeds from generic ledger rows and optional checklist rows."""
    seeds: list[TranscriptSpanSeedV1] = []
    seq = 0
    for item in checklist_seed_items:
        if not isinstance(item, dict):
            continue
        raw_seed = item.get("span_seed")
        if not isinstance(raw_seed, dict):
            continue
        coerced = coerce_orient_span_seed_dict(raw_seed) or raw_seed
        seq += 1
        seed = _try_transcript_span_seed_v1(coerced, seq=seq)
        if seed is not None:
            seeds.append(seed)
        if len(seeds) >= 24:
            return seeds
    for row in list(startup_understanding.get("initial_ledger_items") or []):
        if not isinstance(row, dict):
            continue
        raw_seed = row.get("span_seed")
        if not isinstance(raw_seed, dict):
            continue
        coerced = coerce_orient_span_seed_dict(raw_seed) or raw_seed
        seq += 1
        seed = _try_transcript_span_seed_v1(coerced, seq=seq)
        if seed is not None:
            seeds.append(seed)
        if len(seeds) >= 24:
            break
    return seeds


