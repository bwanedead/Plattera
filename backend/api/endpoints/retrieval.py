from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from corpus.types import CorpusEntry, CorpusEntryRef, CorpusView
from corpus.virtual_provider import VirtualCorpusProvider
from retrieval.engine.diagnose import RuntimeIndexIdentity
from retrieval.engine.pool_maintenance import PoolMaintenanceController
from retrieval.engine.retrieval_engine import RetrievalEngine
from retrieval.filters.models import RetrievalFilters
from retrieval.lanes.semantic.chunking import FINAL_SEGMENTS_POLICY
from retrieval.lanes.semantic.embeddings import compute_model_fingerprint
from retrieval.lanes.semantic.provider import resolve_embedding_model
from services.assets.service import AssetsService


router = APIRouter()
engine = RetrievalEngine()


class RetrievalSearchFilters(BaseModel):
    view: Optional[str] = None
    dossier_id: Optional[str] = None
    transcription_id: Optional[str] = None
    artifact_type: Optional[str] = None
    since_iso: Optional[str] = None
    until_iso: Optional[str] = None


class RetrievalSearchOptions(BaseModel):
    include_index_health: bool = False
    expand_fulltext: bool = False
    max_expand: int = 3


class RetrievalSearchRequest(BaseModel):
    query: str
    lanes: List[str] = Field(default_factory=list)
    limit: int = 10
    filters: Optional[RetrievalSearchFilters] = None
    options: Optional[RetrievalSearchOptions] = None


def _parse_view(value: Optional[str]) -> Optional[CorpusView]:
    if not value:
        return None
    normalized = value.strip().lower()
    try:
        return CorpusView(normalized)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown view: {value}") from exc


def _lane_view_notes(lanes: List[str], filters: Optional[RetrievalFilters]) -> List[str]:
    notes: List[str] = []
    if not filters or not filters.view:
        return notes
    view = filters.view.value
    has_lexical = any(lane.startswith("lexical") or lane == "hybrid" or lane == "hybrid_semantic" for lane in lanes)
    has_semantic = any("semantic" in lane for lane in lanes)
    if has_lexical and view == "final_segments":
        notes.append("lexical lanes do not target final_segments view")
    if has_semantic and view not in ("final_segments", "everything"):
        notes.append("semantic lane expects final_segments/everything views")
    if "provenance" in lanes and not (filters.dossier_id or ""):
        notes.append("provenance lane requires dossier_id filter")
    return notes


def _build_filters(filters: Optional[RetrievalSearchFilters]) -> Optional[RetrievalFilters]:
    if not filters:
        return None
    view = _parse_view(filters.view)
    return RetrievalFilters(
        view=view,
        dossier_id=filters.dossier_id,
        transcription_id=filters.transcription_id,
        artifact_type=filters.artifact_type,
        since_iso=filters.since_iso,
        until_iso=filters.until_iso,
        extra={},
    )


def _entry_ref_payload(ref: CorpusEntryRef) -> Dict[str, Any]:
    return {
        "view": ref.view.value,
        "entry_id": ref.entry_id,
        "kind": ref.kind.value,
        "dossier_id": ref.dossier_id,
        "transcription_id": ref.transcription_id,
        "segment_id": ref.segment_id,
        "draft_id": ref.draft_id,
        "artifact_type": ref.artifact_type,
        "artifact_id": ref.artifact_id,
        "metadata": ref.metadata,
    }


def _serialize_result(result) -> Dict[str, Any]:
    cards_payload = []
    for card in result.cards:
        spans_payload = []
        for span in card.spans:
            chunk_payload = None
            if span.chunk:
                chunk_payload = {
                    "entry": _entry_ref_payload(span.chunk.entry),
                    "chunk_id": span.chunk.chunk_id,
                    "start": span.chunk.start,
                    "end": span.chunk.end,
                    "metadata": span.chunk.metadata,
                }
            spans_payload.append(
                {
                    "entry": _entry_ref_payload(span.entry),
                    "text": span.text,
                    "chunk": chunk_payload,
                    "start": span.start,
                    "end": span.end,
                    "content_hash": span.content_hash,
                    "preview": span.preview,
                    "trace": asdict(span.trace) if span.trace else None,
                    "metadata": span.metadata,
                }
            )
        cards_payload.append(
            {
                "id": card.id,
                "lane": card.lane,
                "score": card.score,
                "title": card.title,
                "provenance": card.provenance,
                "spans": spans_payload,
            }
        )
    return {"query": result.query, "cards": cards_payload, "debug": result.debug}


def _expand_entries(cards, max_expand: int) -> List[Dict[str, Any]]:
    provider = VirtualCorpusProvider()
    expanded: List[Dict[str, Any]] = []
    seen = set()
    max_expand = max(1, min(max_expand, 10))
    for card in cards:
        for span in card.spans:
            ref = span.entry
            key = (ref.view.value, ref.entry_id, ref.dossier_id or "")
            if key in seen:
                continue
            seen.add(key)
            entry: CorpusEntry = provider.hydrate_entry(ref)
            text = entry.text or ""
            if len(text) > 5000:
                text = text[:4997] + "..."
            expanded.append(
                {
                    "ref": _entry_ref_payload(entry.ref),
                    "title": entry.title,
                    "text": text,
                    "content_hash": entry.content_hash,
                    "mime_type": entry.mime_type,
                    "created_at": entry.created_at,
                    "provenance": entry.provenance,
                    "extra": entry.extra,
                }
            )
            if len(expanded) >= max_expand:
                return expanded
    return expanded


def _snapshot_index_health(pools: List[str]) -> Dict[str, Any]:
    provider = VirtualCorpusProvider()
    controller = PoolMaintenanceController(corpus_provider=provider)
    assets_service = AssetsService()
    identity = None
    try:
        model_info = resolve_embedding_model(assets_service)
        fingerprint = compute_model_fingerprint(model_info)
        identity = RuntimeIndexIdentity(
            embedding_model_fingerprint=fingerprint,
            chunking_policy_id=FINAL_SEGMENTS_POLICY.policy_id,
        )
    except Exception:
        identity = None

    snapshot: Dict[str, Any] = {}
    for pool_identifier in pools:
        report = controller.diagnose_pool(
            pool_identifier=pool_identifier,
            runtime_identity=identity,
        )
        counts = {"healthy": 0, "missing": 0, "stale": 0, "unavailable": 0, "orphaned": 0}
        for diag in report.slice_diagnoses or []:
            status = diag.status.value
            if status == "healthy":
                counts["healthy"] += 1
            elif status == "missing":
                counts["missing"] += 1
            elif status in ("stale_content", "stale_identity"):
                counts["stale"] += 1
            elif status == "unavailable":
                counts["unavailable"] += 1
            elif status == "orphaned":
                counts["orphaned"] += 1
        snapshot[pool_identifier] = {
            "pool_open": {
                "status": report.pool_open.status.value,
                "reason_code": report.pool_open.reason_code.value if report.pool_open.reason_code else None,
                "detail": report.pool_open.detail,
                "action_hint": report.pool_open.action_hint,
            },
            "pool_health": asdict(report.pool_health) if report.pool_health else None,
            "counts": counts,
        }
    return snapshot


@router.post("/retrieval/search")
async def retrieval_search(payload: RetrievalSearchRequest) -> Dict[str, Any]:
    lanes = payload.lanes or ["hybrid_semantic"]
    limit = max(1, min(payload.limit, 100))
    filters = _build_filters(payload.filters)

    result = engine.search(
        payload.query,
        filters=filters,
        limit=limit,
        lanes=lanes,
    )

    response: Dict[str, Any] = {"result": _serialize_result(result)}
    notes = _lane_view_notes(lanes, filters)
    if notes:
        debug = response["result"].get("debug") or {}
        debug_notes = list(debug.get("notes", []) or [])
        debug_notes.extend(notes)
        debug["notes"] = debug_notes
        response["result"]["debug"] = debug

    options = payload.options or RetrievalSearchOptions()
    if options.include_index_health:
        pools = ["FINAL_SEGMENTS"] if any("semantic" in lane for lane in lanes) else []
        response["index_health"] = _snapshot_index_health(pools)
    if options.expand_fulltext:
        response["expanded_entries"] = _expand_entries(result.cards, options.max_expand)

    return response
