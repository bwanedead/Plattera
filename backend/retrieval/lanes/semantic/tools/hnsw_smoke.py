from __future__ import annotations

import argparse
import time

from retrieval.lanes.semantic.embeddings import build_embedding_provider
from retrieval.lanes.semantic.manifest import (
    hnsw_index_path,
    metadata_db_path,
    read_manifest,
)
from retrieval.lanes.semantic.persistent_store import load_persistent_store
from services.assets.service import AssetsService


def _load_store(pool_identifier: str):
    manifest = read_manifest(pool_identifier)
    if manifest is None:
        raise SystemExit(f"Missing manifest for pool={pool_identifier}")
    return load_persistent_store(
        pool_identifier=pool_identifier,
        embedding_dim=manifest.embedding_dim,
        hnsw_path=hnsw_index_path(pool_identifier),
        metadata_db_path=metadata_db_path(pool_identifier),
    )


def _embed_query(text: str):
    provider = build_embedding_provider(assets_service=AssetsService())
    vectors = provider.embed([text])
    if not vectors or not vectors[0]:
        raise SystemExit("Embedding provider returned empty vector")
    return vectors[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="HNSW smoke test loop")
    parser.add_argument("--pool", default="FINAL_SEGMENTS")
    parser.add_argument("--query", default="ZZZTEST_0128")
    parser.add_argument("--iterations", type=int, default=2000)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--report-every", type=int, default=100)
    args = parser.parse_args()

    pool_identifier = args.pool.strip().upper()
    if pool_identifier not in ("FINAL_SEGMENTS", "EVERYTHING"):
        raise SystemExit("pool must be FINAL_SEGMENTS or EVERYTHING")

    store = _load_store(pool_identifier)
    query_vector = _embed_query(args.query)

    started = time.monotonic()
    for i in range(1, args.iterations + 1):
        _ = store.hnsw_store.knn_query(query_vector, k=args.k)
        if i % args.report_every == 0:
            elapsed = time.monotonic() - started
            print(f"[{pool_identifier}] iter={i} elapsed_s={elapsed:.2f}")

    elapsed = time.monotonic() - started
    print(f"[{pool_identifier}] completed {args.iterations} iterations in {elapsed:.2f}s")


if __name__ == "__main__":
    main()
