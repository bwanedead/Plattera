from __future__ import annotations

import argparse
import logging
import os
import sys

from .server import SemanticWorkerRequestHandler, SemanticWorkerTCPServer


def main() -> None:
    parser = argparse.ArgumentParser(description="Semantic HNSW worker")
    parser.add_argument("--pool", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()

    pool_identifier = args.pool.strip().upper()
    if pool_identifier not in ("FINAL_SEGMENTS", "EVERYTHING"):
        raise SystemExit("pool must be FINAL_SEGMENTS or EVERYTHING")

    os.environ["HNSW_QUERY_SUBPROCESS"] = "0"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s semantic_worker %(message)s",
    )
    logging.getLogger(__name__).info(
        "Starting semantic worker pool=%s host=%s port=%s",
        pool_identifier,
        args.host,
        args.port,
    )

    server = SemanticWorkerTCPServer(
        (args.host, args.port),
        SemanticWorkerRequestHandler,
        pool_identifier=pool_identifier,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
