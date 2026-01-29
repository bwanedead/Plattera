from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from retrieval.lanes.semantic.hnsw_store import load_hnsw_store


def main() -> None:
    payload = json.loads(sys.stdin.read() or "{}")
    index_path = payload.get("index_path")
    embedding_dim = payload.get("embedding_dim")
    max_elements = payload.get("max_elements")
    vector = payload.get("vector")
    k = payload.get("k", 10)
    ef = payload.get("ef")

    if not index_path or embedding_dim is None or max_elements is None or vector is None:
        raise SystemExit("Missing required payload fields.")

    os.environ["HNSW_QUERY_SUBPROCESS"] = "0"
    store = load_hnsw_store(
        path=Path(index_path),
        embedding_dim=int(embedding_dim),
        max_elements=int(max_elements),
    )
    results = store._knn_query_in_process(vector=vector, k=int(k), ef=ef)
    json.dump({"results": results}, sys.stdout)


if __name__ == "__main__":
    main()
