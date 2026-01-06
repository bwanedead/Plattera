from __future__ import annotations

import argparse
from datetime import datetime, timezone

from .embedding_installer import EmbeddingInstaller
from .models import AssetProgress, AssetStatus
from .progress_store import clear_cancel, write_progress


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Embedding asset installer worker")
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()

    clear_cancel(args.asset_id)
    installer = EmbeddingInstaller()
    try:
        installer.install(asset_id=args.asset_id, repo_id=args.repo_id, revision=args.revision)
        return 0
    except RuntimeError as exc:
        if "stopped" in str(exc) or "canceled" in str(exc):
            write_progress(
                args.asset_id,
                AssetProgress(
                    status=AssetStatus.STOPPED,
                    stage="stopped",
                    headline="Download stopped",
                    detail="Download stopped",
                    message="Stopped",
                    progress_bar="none",
                    phase="stopped",
                    updated_at=_now_iso(),
                ),
            )
            return 2
        write_progress(
            args.asset_id,
            AssetProgress(
                status=AssetStatus.FAILED,
                stage="error",
                headline="Install failed",
                detail=str(exc),
                message=str(exc),
                progress_bar="none",
                phase="failed",
                updated_at=_now_iso(),
            ),
        )
        return 1
    except Exception as exc:
        write_progress(
            args.asset_id,
            AssetProgress(
                status=AssetStatus.FAILED,
                stage="error",
                headline="Install failed",
                detail=str(exc),
                message=str(exc),
                progress_bar="none",
                phase="failed",
                updated_at=_now_iso(),
            ),
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
