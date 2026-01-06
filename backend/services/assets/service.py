from __future__ import annotations

import json
import shutil
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from config.paths import embeddings_root
from services.plss.plss_data_service import PLSSDataService

from .embedding_installer import EmbeddingInstaller
from .models import AssetDefinition, AssetManifest, AssetProgress, AssetStatus
from .progress_store import (
    cancel_requested,
    clear_cancel,
    clear_progress,
    read_progress,
    request_cancel,
    write_progress,
)
from .registry import ASSET_DEFINITIONS, EMBEDDING_MODEL_ASSET_ID


@dataclass
class AssetsService:
    installer: EmbeddingInstaller = field(default_factory=EmbeddingInstaller)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _threads: Dict[str, threading.Thread] = field(default_factory=dict)

    def list_assets(self, *, plss_state: Optional[str] = None) -> List[Dict[str, object]]:
        assets = []
        for asset in ASSET_DEFINITIONS.values():
            if asset.asset_id == "plss":
                assets.append(self._plss_asset_row(asset, plss_state))
            else:
                assets.append(self._embedding_asset_row(asset))
        return assets

    def start_install(self, asset_id: str) -> Dict[str, object]:
        asset = ASSET_DEFINITIONS.get(asset_id)
        if not asset:
            return {"success": False, "error": "unknown_asset"}
        if asset.asset_id == "plss":
            return {"success": False, "error": "plss_managed_externally"}

        with self._lock:
            existing = self._threads.get(asset_id)
            if existing and existing.is_alive():
                return {"success": True, "status": "installing"}

            thread = threading.Thread(target=self._install_embedding, args=(asset,), daemon=True)
            self._threads[asset_id] = thread
            thread.start()
        return {"success": True, "status": "installing"}

    def get_progress(self, asset_id: str) -> Dict[str, object]:
        progress = read_progress(asset_id)
        if progress:
            return {"success": True, **progress.to_dict()}
        status = self._current_status(asset_id)
        return {"success": True, "status": status.value}

    def cancel_install(self, asset_id: str) -> Dict[str, object]:
        asset = ASSET_DEFINITIONS.get(asset_id)
        if not asset:
            return {"success": False, "error": "unknown_asset"}
        if asset.asset_id == "plss":
            return {"success": False, "error": "plss_managed_externally"}
        request_cancel(asset_id)
        write_progress(
            asset_id,
            AssetProgress(
                status=AssetStatus.CANCELED,
                stage="canceled",
                headline="Cancel requested",
                detail="Will stop after current download step completes",
                message="Cancel requested; will stop after current download step completes",
                progress_bar="none",
                phase="canceled",
                updated_at=datetime.now(timezone.utc).isoformat(),
            ),
        )
        return {"success": True, "status": "canceled"}

    def get_asset_status(self, asset_id: str) -> AssetStatus:
        return self._current_status(asset_id)

    def purge_asset(self, asset_id: str) -> Dict[str, object]:
        asset = ASSET_DEFINITIONS.get(asset_id)
        if not asset:
            return {"success": False, "error": "unknown_asset"}
        if asset.asset_id == "plss":
            return {"success": False, "error": "plss_managed_externally"}
        target_dir = embeddings_root() / asset_id
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        clear_progress(asset_id)
        clear_cancel(asset_id)
        return {"success": True}

    def _install_embedding(self, asset: AssetDefinition) -> None:
        clear_cancel(asset.asset_id)
        repo_id = asset.meta.get("repo_id")
        revision = asset.meta.get("revision") or "main"
        if not repo_id:
            write_progress(
                asset.asset_id,
                AssetProgress(
                    status=AssetStatus.FAILED,
                    stage="error",
                    headline="Install failed",
                    detail="Missing repo_id",
                    message="Missing repo_id",
                    progress_bar="none",
                    phase="failed",
                    updated_at=datetime.now(timezone.utc).isoformat(),
                ),
            )
            return
        try:
            self.installer.install(asset_id=asset.asset_id, repo_id=repo_id, revision=revision)
        except RuntimeError as exc:
            if "canceled" in str(exc):
                write_progress(
                    asset.asset_id,
                    AssetProgress(
                        status=AssetStatus.CANCELED,
                        stage="canceled",
                        headline="Install canceled",
                        detail="Canceled after download step completed",
                        message="Install canceled",
                        progress_bar="none",
                        phase="canceled",
                        updated_at=datetime.now(timezone.utc).isoformat(),
                    ),
                )
                return
            write_progress(
                asset.asset_id,
                AssetProgress(
                    status=AssetStatus.FAILED,
                    stage="error",
                    headline="Install failed",
                    detail=str(exc),
                    message=str(exc),
                    progress_bar="none",
                    phase="failed",
                    updated_at=datetime.now(timezone.utc).isoformat(),
                ),
            )
        except Exception as exc:
            write_progress(
                asset.asset_id,
                AssetProgress(
                    status=AssetStatus.FAILED,
                    stage="error",
                    headline="Install failed",
                    detail=str(exc),
                    message=str(exc),
                    progress_bar="none",
                    phase="failed",
                    updated_at=datetime.now(timezone.utc).isoformat(),
                ),
            )

    def _embedding_asset_row(self, asset: AssetDefinition) -> Dict[str, object]:
        status = self._current_status(asset.asset_id)
        manifest = self._manifest_summary(asset.asset_id)
        progress = read_progress(asset.asset_id)
        return {
            "asset_id": asset.asset_id,
            "display_name": asset.display_name,
            "kind": asset.kind,
            "source": asset.source,
            "status": status.value,
            "stage": progress.stage if progress else None,
            "message": progress.message if progress else None,
            "headline": progress.headline if progress else None,
            "detail": progress.detail if progress else None,
            "progress_bar": progress.progress_bar if progress else None,
            "percent": progress.percent if progress else None,
            "bytes_downloaded": progress.bytes_downloaded if progress else None,
            "bytes_total": progress.bytes_total if progress else None,
            "current_file": progress.current_file if progress else None,
            "phase": progress.phase if progress else None,
            "updated_at": progress.updated_at if progress else None,
            "manifest": manifest,
        }

    def _plss_asset_row(self, asset: AssetDefinition, plss_state: Optional[str]) -> Dict[str, object]:
        row = {
            "asset_id": asset.asset_id,
            "display_name": asset.display_name,
            "kind": asset.kind,
            "source": asset.source,
            "status": AssetStatus.MISSING.value,
            "stage": None,
            "message": None,
            "percent": None,
            "manifest": None,
        }
        if not plss_state:
            row["message"] = "state_required"
            return row
        service = PLSSDataService()
        status = service.check_state_data_status(plss_state)
        if status.get("available"):
            row["status"] = AssetStatus.INSTALLED.value
            row["message"] = "ready"
        else:
            row["status"] = AssetStatus.MISSING.value
            row["message"] = status.get("message")
        row["plss_state"] = plss_state
        return row

    def _current_status(self, asset_id: str) -> AssetStatus:
        progress = read_progress(asset_id)
        if progress:
            return progress.status
        manifest = self._manifest_summary(asset_id)
        if manifest:
            return AssetStatus.INSTALLED
        return AssetStatus.MISSING

    def _manifest_summary(self, asset_id: str) -> Optional[Dict[str, object]]:
        manifest_path = (embeddings_root() / asset_id / "manifest.json")
        if not manifest_path.exists():
            return None
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return {
            "revision": data.get("revision"),
            "installed_at": data.get("installed_at"),
            "total_bytes": data.get("total_bytes"),
            "smoke_test": data.get("smoke_test"),
        }
