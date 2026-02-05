from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from corpus.types import CorpusEntry, CorpusEntryRef, CorpusView
from corpus.virtual_provider import VirtualCorpusProvider
from retrieval.engine.diagnose import RuntimeIndexIdentity
from retrieval.engine.pool_maintenance import PoolMaintenanceController
from retrieval.engine.retrieval_engine import RetrievalEngine
from retrieval.filters.models import RetrievalFilters
from services.assets.service import AssetsService
from retrieval.lanes.semantic.embeddings import compute_model_fingerprint
from retrieval.lanes.semantic.chunking import FINAL_SEGMENTS_POLICY
from retrieval.lanes.semantic.provider import resolve_embedding_model
from retrieval.lanes.semantic.lane import LocalSemanticLane


def _parse_view(value: Optional[str]) -> Optional[CorpusView]:
    if not value:
        return None
    normalized = value.strip().lower()
    try:
        return CorpusView(normalized)
    except ValueError:
        raise ValueError(f"Unknown view: {value!r}")


def _parse_lanes(values: Optional[List[str]]) -> List[str]:
    if not values:
        return ["hybrid_semantic"]
    lanes: List[str] = []
    for raw in values:
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        lanes.extend(parts)
    return lanes


def _lane_view_notes(
    lanes: List[str],
    filters: Optional[RetrievalFilters],
    *,
    semantic_pool: str,
) -> List[str]:
    notes: List[str] = []
    if not filters or not filters.view:
        view = None
    else:
        view = filters.view.value
    has_lexical = any(lane.startswith("lexical") or lane == "hybrid" or lane == "hybrid_semantic" for lane in lanes)
    has_semantic = any("semantic" in lane for lane in lanes)
    if has_lexical and view == "final_segments":
        notes.append("lexical lanes do not target final_segments view")
    if has_semantic and view and view not in ("final_segments", "everything"):
        notes.append("semantic lane expects final_segments/everything views")
    if has_semantic and view and semantic_pool.lower() != view:
        notes.append(f"semantic lane uses pool={semantic_pool} (ignores view={view})")
    if "provenance" in lanes and not (filters and (filters.dossier_id or "")):
        notes.append("provenance lane requires dossier_id filter")
    return notes


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


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


def _snapshot_index_health(pools: Iterable[str]) -> Dict[str, Any]:
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


def _build_filters(args) -> Optional[RetrievalFilters]:
    view = _parse_view(args.view)
    if not any([view, args.dossier_id, args.transcription_id, args.artifact_type, args.since_iso, args.until_iso]):
        return None
    return RetrievalFilters(
        view=view,
        dossier_id=args.dossier_id,
        transcription_id=args.transcription_id,
        artifact_type=args.artifact_type,
        since_iso=args.since_iso,
        until_iso=args.until_iso,
        extra={},
    )


def _print_results(result, limit: int) -> None:
    print(f"\nQuery: {result.query}")
    print(f"Results: {len(result.cards)}\n")
    for i, card in enumerate(result.cards[:limit], start=1):
        span = card.spans[0] if card.spans else None
        entry_id = span.entry.entry_id if span else "unknown"
        dossier_id = span.entry.dossier_id if span else "unknown"
        preview = span.preview or span.text or ""
        preview = _truncate(preview, 160)
        print(f"{i:02d}. lane={card.lane} score={card.score:.4f} dossier={dossier_id} entry={entry_id}")
        if preview:
            print(f"    {preview}")


def _write_run_artifact(
    *,
    root: Path,
    query: str,
    lanes: List[str],
    payload: Dict[str, Any],
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    lane_tag = "-".join(lanes) if lanes else "all"
    q_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()[:8]
    filename = f"{timestamp}__{lane_tag}__{q_hash}.json"
    path = root / filename
    path.write_text(json.dumps(payload, indent=2))
    return path


def _evaluate_query_set(
    engine: RetrievalEngine,
    query_set_path: Path,
    *,
    lanes: List[str],
    limit: int,
    filters: Optional[RetrievalFilters],
    include_index_health: bool,
    semantic_pool: str,
) -> Path:
    items = json.loads(query_set_path.read_text())
    run_rows = []
    summary = {
        "total": 0,
        "empty_results": 0,
        "anchor_hit_rate": 0.0,
        "precision_at_k": 0.0,
    }
    hits = 0
    precision_sum = 0.0

    for item in items:
        query = item.get("query", "")
        expected = set(item.get("expected_dossier_ids", []))
        result = engine.search(query, filters=filters, limit=limit, lanes=lanes)
        notes = _lane_view_notes(lanes, filters, semantic_pool=semantic_pool)
        if notes:
            debug = result.debug or {}
            debug_notes = list(debug.get("notes", []) or [])
            debug_notes.extend(notes)
            debug["notes"] = debug_notes
            result.debug = debug
        dossier_hits = []
        for card in result.cards:
            if not card.spans:
                continue
            dossier_id = card.spans[0].entry.dossier_id
            if dossier_id:
                dossier_hits.append(dossier_id)
        top_k = dossier_hits[:limit]
        match_count = len([d for d in top_k if d in expected])
        precision = match_count / limit if limit else 0.0
        anchor_hit = 1 if expected and any(d in expected for d in top_k) else 0

        if not result.cards:
            summary["empty_results"] += 1
        hits += anchor_hit
        precision_sum += precision

        run_rows.append(
            {
                "id": item.get("id"),
                "query": query,
                "expected_dossier_ids": list(expected),
                "top_k_dossier_ids": top_k,
                "precision_at_k": precision,
                "anchor_hit": bool(anchor_hit),
                "result": _serialize_result(result),
            }
        )

    total = len(items)
    summary["total"] = total
    summary["anchor_hit_rate"] = (hits / total) if total else 0.0
    summary["precision_at_k"] = (precision_sum / total) if total else 0.0

    payload = {
        "query_set": str(query_set_path),
        "lanes": lanes,
        "limit": limit,
        "filters": (filters.__dict__ if filters else None),
        "summary": summary,
        "runs": run_rows,
    }
    if include_index_health:
        pools = [semantic_pool] if any("semantic" in lane for lane in lanes) else []
        payload["index_health"] = _snapshot_index_health(pools)
        payload["index_health_scope"] = "batch"

    root = Path(__file__).resolve().parents[3] / "assets" / "rag_runs"
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    path = root / f"batch_{timestamp}.json"
    root.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieval playground CLI")
    parser.add_argument("query", nargs="?", help="Query string")
    parser.add_argument("--lanes", action="append", help="Comma-separated lanes (repeatable)")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--view", help="Corpus view (finalized, final_segments, everything, artifacts)")
    parser.add_argument("--dossier-id")
    parser.add_argument("--transcription-id")
    parser.add_argument("--artifact-type")
    parser.add_argument("--since-iso")
    parser.add_argument("--until-iso")
    parser.add_argument("--expand", action="store_true", help="Hydrate full text for top results")
    parser.add_argument("--max-expand", type=int, default=3)
    parser.add_argument("--include-index-health", action="store_true")
    parser.add_argument("--query-set", help="Run a batch query set JSON")
    parser.add_argument("--interactive", action="store_true", help="Interactive query loop (warm cache)")
    parser.add_argument(
        "--semantic-pool",
        default="FINAL_SEGMENTS",
        help="Semantic pool identifier (FINAL_SEGMENTS or EVERYTHING)",
    )
    args = parser.parse_args()

    lanes = _parse_lanes(args.lanes)
    filters = _build_filters(args)
    semantic_pool = args.semantic_pool.strip().upper()
    if semantic_pool not in ("FINAL_SEGMENTS", "EVERYTHING"):
        raise SystemExit("semantic-pool must be FINAL_SEGMENTS or EVERYTHING")
    engine = RetrievalEngine(semantic_lane=LocalSemanticLane(pool_identifier=semantic_pool))

    if args.query_set:
        path = _evaluate_query_set(
            engine,
            Path(args.query_set),
            lanes=lanes,
            limit=args.limit,
            filters=filters,
            include_index_health=args.include_index_health,
            semantic_pool=semantic_pool,
        )
        print(f"Wrote batch run: {path}")
        return

    run_id = hashlib.sha256(str(datetime.utcnow().timestamp()).encode("utf-8")).hexdigest()[:8]
    run_seq = 0

    def _run_single_query(query: str) -> None:
        nonlocal run_seq
        run_seq += 1
        result = engine.search(query, filters=filters, limit=args.limit, lanes=lanes)
        notes = _lane_view_notes(lanes, filters, semantic_pool=semantic_pool)
        if notes:
            debug = result.debug or {}
            debug_notes = list(debug.get("notes", []) or [])
            debug_notes.extend(notes)
            debug["notes"] = debug_notes
            result.debug = debug
        _print_results(result, args.limit)

        run_payload: Dict[str, Any] = {
            "request": {
                "query": query,
                "lanes": lanes,
                "limit": args.limit,
                "filters": (filters.__dict__ if filters else None),
            },
            "run": {
                "run_id": run_id,
                "seq": run_seq,
                "timestamp": datetime.utcnow().isoformat(),
            },
            "result": _serialize_result(result),
        }

        if args.include_index_health:
            pools = [semantic_pool] if any("semantic" in lane for lane in lanes) else []
            run_payload["index_health"] = _snapshot_index_health(pools)

        if args.expand:
            run_payload["expanded_entries"] = _expand_entries(result.cards, args.max_expand)

        root = Path(__file__).resolve().parents[3] / "assets" / "rag_runs"
        path = _write_run_artifact(root=root, query=query, lanes=lanes, payload=run_payload)
        print(f"\nWrote run artifact: {path}")

    if args.interactive:
        if args.query:
            _run_single_query(args.query)
        print("\nInteractive mode (type 'exit' to quit).")
        while True:
            try:
                line = input("query> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("")
                break
            if not line:
                continue
            if line.lower() in {"exit", "quit"}:
                break
            _run_single_query(line)
        return

    if not args.query:
        raise SystemExit("Query required unless --query-set or --interactive is provided.")

    _run_single_query(args.query)


if __name__ == "__main__":
    main()
