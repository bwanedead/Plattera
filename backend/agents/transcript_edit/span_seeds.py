from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from transcript_edit.contracts import (
    Confidence,
    LocatorAnchorsV0,
    TranscriptSpanSeedLabel,
    TranscriptSpanSeedOrigin,
    TranscriptSpanSeedsArtifactV1,
    TranscriptSpanSeedV1,
)


_LABEL_PATTERNS: list[tuple[TranscriptSpanSeedLabel, str]] = [
    (TranscriptSpanSeedLabel.POB, r"\bbeginning at\b"),
    (TranscriptSpanSeedLabel.CALL_CHAIN, r"\bthence\b"),
    (TranscriptSpanSeedLabel.PLSS, r"\b(section|township|range|principal meridian)\b"),
    (TranscriptSpanSeedLabel.TIE_TO_CORNER, r"\b(corner|quarter corner|line of section)\b"),
    (TranscriptSpanSeedLabel.CLOSURE, r"\b(point of beginning|place of beginning)\b"),
    (TranscriptSpanSeedLabel.EXCEPTION, r"\b(except|exception)\b"),
    (TranscriptSpanSeedLabel.ACREAGE, r"\b(acre|acres)\b"),
]


def load_transcript_text_for_seeds(transcript_ref: str) -> str | None:
    path = Path(transcript_ref)
    if not path.exists():
        return None
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(payload, str):
        text = payload.strip()
        return text or None
    if not isinstance(payload, dict):
        return None
    sections = payload.get("sections")
    if isinstance(sections, list):
        parts: list[str] = []
        for section in sections:
            if not isinstance(section, dict):
                continue
            body = section.get("body")
            if isinstance(body, str) and body.strip():
                parts.append(body.strip())
        joined = "\n\n".join(parts).strip()
        if joined:
            return joined
    text = payload.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return None


def build_transcript_span_seeds_artifact(
    *,
    dossier_id: str,
    source_transcript_ref: str,
    source_transcript_hash: str,
    transcript_text: str,
    max_seeds: int = 24,
) -> TranscriptSpanSeedsArtifactV1:
    seeds = _derive_anchor_seeds(text=transcript_text, max_seeds=max(1, min(30, max_seeds)))
    return TranscriptSpanSeedsArtifactV1(
        created_at=datetime.now(timezone.utc).isoformat(),
        dossier_id=dossier_id,
        source_transcript_ref=source_transcript_ref,
        source_transcript_hash=source_transcript_hash,
        seeds=seeds,
    )


def _derive_anchor_seeds(*, text: str, max_seeds: int) -> list[TranscriptSpanSeedV1]:
    seeds: list[TranscriptSpanSeedV1] = []
    seen_labels: set[TranscriptSpanSeedLabel] = set()
    lowered = text.lower()
    for label, pattern in _LABEL_PATTERNS:
        if label in seen_labels:
            continue
        match = re.search(pattern, lowered, flags=re.IGNORECASE)
        if match is None:
            continue
        start_anchor, end_anchor, occurrence = _paragraph_anchors(text=text, start_index=match.start())
        if not start_anchor or not end_anchor:
            continue
        seeds.append(
            TranscriptSpanSeedV1(
                seed_id=f"seed_{label.value}_{len(seeds) + 1:02d}",
                label=label,
                seed_origin=TranscriptSpanSeedOrigin.HYBRID,
                seed_confidence=Confidence.MEDIUM,
                notes=f"Derived from transcript landmark: {label.value}",
                locator=LocatorAnchorsV0(
                    start_anchor=start_anchor,
                    end_anchor=end_anchor,
                    occurrence=occurrence,
                ),
            )
        )
        seen_labels.add(label)
        if len(seeds) >= max_seeds:
            break
    return seeds


def _paragraph_anchors(*, text: str, start_index: int) -> tuple[str, str, int]:
    para_start = text.rfind("\n\n", 0, start_index)
    para_start = 0 if para_start < 0 else para_start + 2
    para_end = text.find("\n\n", start_index)
    para_end = len(text) if para_end < 0 else para_end
    paragraph = text[para_start:para_end].strip()
    if not paragraph:
        return "", "", 1
    start_anchor = paragraph[: min(120, len(paragraph))].strip()
    end_anchor = paragraph[max(0, len(paragraph) - 120) :].strip()
    if len(start_anchor) < 8 or len(end_anchor) < 8:
        return "", "", 1
    return start_anchor, end_anchor, 1
