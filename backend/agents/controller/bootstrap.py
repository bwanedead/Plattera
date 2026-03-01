"""Bootstrap helpers for controller run inputs."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from config.paths import agent_kernel_artifacts_root, dossiers_artifacts_root
from corpus.types import CorpusEntryKind, CorpusEntryRef, CorpusView
from corpus.virtual_provider import VirtualCorpusProvider


@dataclass(frozen=True)
class DeedTextArtifact:
    artifact_path: str
    excerpt: str


@dataclass(frozen=True)
class TranscriptSpanSeedsBundle:
    source_transcript_ref: str
    source_transcript_hash: str
    seeds: list[dict[str, Any]]


def persist_deed_text_artifact(*, request_id: str, deed_text: str, dossier_id: str | None) -> DeedTextArtifact:
    root = agent_kernel_artifacts_root() / "controller_inputs" / "deed_text" / request_id
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{uuid4().hex[:10]}.json"
    payload = {
        "artifact_type": "deed_text",
        "request_id": request_id,
        "dossier_id": dossier_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "text": deed_text,
    }
    fd, tmp_path = tempfile.mkstemp(prefix="controller_deed_", suffix=".json", dir=str(root))
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
    return DeedTextArtifact(artifact_path=str(path), excerpt=deed_text[:1000])


def hydrate_and_persist_finalized_dossier_text(
    *,
    request_id: str,
    dossier_id: str,
    provider: VirtualCorpusProvider | None = None,
) -> DeedTextArtifact | None:
    promoted_text = _load_promoted_transcript_text_for_mapping(dossier_id=dossier_id)
    if promoted_text:
        return persist_deed_text_artifact(
            request_id=request_id,
            deed_text=promoted_text,
            dossier_id=dossier_id,
        )

    corpus = provider or VirtualCorpusProvider()
    ref = CorpusEntryRef(
        view=CorpusView.FINALIZED,
        entry_id=f"final:{dossier_id}",
        kind=CorpusEntryKind.FINALIZED_DOSSIER_TEXT,
        dossier_id=dossier_id,
    )
    entry = corpus.hydrate_entry(ref)
    text = (entry.text or "").strip()
    if not text:
        return None
    provenance_error = str((entry.provenance or {}).get("error") or "").strip()
    if provenance_error:
        return None
    return persist_deed_text_artifact(
        request_id=request_id,
        deed_text=text,
        dossier_id=dossier_id,
    )


def _load_promoted_transcript_text_for_mapping(*, dossier_id: str) -> str | None:
    pointer = dossiers_artifacts_root() / "transcription_edit" / str(dossier_id) / "latest_transcript_for_mapping.json"
    if not pointer.exists():
        return None
    try:
        pointer_payload = json.loads(pointer.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(pointer_payload, dict):
        return None
    transcript_ref = pointer_payload.get("transcript_ref")
    if not isinstance(transcript_ref, str) or not transcript_ref.strip():
        return None
    transcript_path = Path(transcript_ref)
    if not transcript_path.exists():
        return None
    try:
        payload = json.loads(transcript_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return _extract_transcript_text(payload)


def load_transcript_span_seeds_for_mapping(*, dossier_id: str) -> TranscriptSpanSeedsBundle | None:
    root = dossiers_artifacts_root() / "transcription_edit" / str(dossier_id)
    tx_pointer = root / "latest_transcript_for_mapping.json"
    seeds_pointer = root / "latest_transcript_span_seeds.json"
    if not tx_pointer.exists() or not seeds_pointer.exists():
        return None
    try:
        tx_payload = json.loads(tx_pointer.read_text(encoding="utf-8"))
        seeds_meta = json.loads(seeds_pointer.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(tx_payload, dict) or not isinstance(seeds_meta, dict):
        return None
    tx_hash = tx_payload.get("transcript_hash")
    seeds_hash = seeds_meta.get("source_transcript_hash")
    if not isinstance(tx_hash, str) or not tx_hash.strip():
        return None
    if not isinstance(seeds_hash, str) or seeds_hash != tx_hash:
        return None
    seeds_ref = seeds_meta.get("seeds_ref")
    if not isinstance(seeds_ref, str) or not seeds_ref.strip():
        return None
    seeds_path = Path(seeds_ref)
    if not seeds_path.exists():
        return None
    try:
        seeds_payload = json.loads(seeds_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(seeds_payload, dict):
        return None
    source_ref = seeds_payload.get("source_transcript_ref")
    source_hash = seeds_payload.get("source_transcript_hash")
    raw_seeds = seeds_payload.get("seeds")
    if not isinstance(source_ref, str) or not source_ref.strip():
        return None
    if not isinstance(source_hash, str) or source_hash != tx_hash:
        return None
    if not isinstance(raw_seeds, list):
        return None
    seeds: list[dict[str, Any]] = [seed for seed in raw_seeds if isinstance(seed, dict)]
    if not seeds:
        return None
    return TranscriptSpanSeedsBundle(
        source_transcript_ref=source_ref,
        source_transcript_hash=source_hash,
        seeds=seeds[:30],
    )


def materialize_seed_spans_from_text(
    *,
    deed_text: str,
    seed_bundle: TranscriptSpanSeedsBundle,
    max_spans: int = 30,
) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    for seed in seed_bundle.seeds[: max(1, min(30, max_spans))]:
        locator = seed.get("locator")
        if not isinstance(locator, dict):
            continue
        if str(locator.get("locator_type") or "") != "anchors":
            continue
        start_anchor = locator.get("start_anchor")
        end_anchor = locator.get("end_anchor")
        occurrence = locator.get("occurrence")
        if not isinstance(start_anchor, str) or not isinstance(end_anchor, str):
            continue
        if not start_anchor.strip() or not end_anchor.strip():
            continue
        try:
            occ = int(occurrence)
        except Exception:
            occ = 1
        occ = max(1, min(200, occ))
        start_from = 0
        start_idx = -1
        end_idx = -1
        for _ in range(occ):
            start_idx = deed_text.find(start_anchor, start_from)
            if start_idx < 0:
                break
            end_search_from = start_idx + len(start_anchor)
            end_idx = deed_text.find(end_anchor, end_search_from)
            if end_idx < 0:
                break
            start_from = end_idx + len(end_anchor)
        if start_idx < 0 or end_idx < 0:
            continue
        span_start = start_idx
        span_end = end_idx + len(end_anchor)
        if span_end <= span_start:
            continue
        spans.append(
            {
                "seed_id": str(seed.get("seed_id") or f"seed_{len(spans)+1:02d}"),
                "label": str(seed.get("label") or "misc"),
                "start_char": span_start,
                "end_char": span_end,
                "start_anchor": start_anchor,
                "end_anchor": end_anchor,
            }
        )
    return spans


def _extract_transcript_text(payload: Any) -> str | None:
    if isinstance(payload, str):
        text = payload.strip()
        return text or None
    if not isinstance(payload, dict):
        return None
    text = payload.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
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
    return None
