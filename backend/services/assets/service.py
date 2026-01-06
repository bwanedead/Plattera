from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from config.paths import backend_root, embeddings_root
from services.plss.plss_data_service import PLSSDataService

from .models import AssetDefinition, AssetManifest, AssetProgress, AssetStatus
from .embedding_installer import _format_bytes
from .progress_store import (
    cancel_requested,
    clear_cancel,
    clear_progress,
    read_progress,
    request_cancel,
    write_progress,
)
from .registry import ASSET_DEFINITIONS, EMBEDDING_MODEL_ASSET_ID

logger = logging.getLogger(__name__)


@dataclass
class AssetsService:
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _threads: Dict[str, threading.Thread] = field(default_factory=dict)
    _processes: Dict[str, subprocess.Popen] = field(default_factory=dict)

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
            existing = self._processes.get(asset_id)
            if existing and existing.poll() is None:
                return {"success": True, "status": "installing"}

            process = self._spawn_worker(asset)
            self._processes[asset_id] = process
            thread = threading.Thread(target=self._watch_process, args=(asset_id, process), daemon=True)
            self._threads[asset_id] = thread
            thread.start()
            self._start_stderr_reader(asset_id, process)
        return {"success": True, "status": "installing"}

    def get_progress(self, asset_id: str) -> Dict[str, object]:
        progress = read_progress(asset_id)
        if progress and self._should_clear_progress(asset_id, progress.status):
            clear_progress(asset_id)
            clear_cancel(asset_id)
            progress = None
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

    def stop_install(self, asset_id: str) -> Dict[str, object]:
        asset = ASSET_DEFINITIONS.get(asset_id)
        if not asset:
            return {"success": False, "error": "unknown_asset"}
        if asset.asset_id == "plss":
            return {"success": False, "error": "plss_managed_externally"}

        with self._lock:
            proc = self._processes.get(asset_id)
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        self.purge_asset(asset_id)
        with self._lock:
            self._processes.pop(asset_id, None)
        return {"success": True, "status": "stopped"}

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

    def _spawn_worker(self, asset: AssetDefinition) -> subprocess.Popen:
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
            raise RuntimeError("missing_repo_id")

        env = os.environ.copy()
        py_path = env.get("PYTHONPATH")
        backend_path = str(backend_root())
        env["PYTHONPATH"] = f"{backend_path}{os.pathsep}{py_path}" if py_path else backend_path

        return subprocess.Popen(
            [
                sys.executable,
                "-m",
                "services.assets.embedding_worker",
                "--asset-id",
                asset.asset_id,
                "--repo-id",
                repo_id,
                "--revision",
                revision,
            ],
            cwd=str(backend_root()),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def _watch_process(self, asset_id: str, process: subprocess.Popen) -> None:
        process.wait()
        with self._lock:
            current = self._processes.get(asset_id)
            if current is process:
                self._processes.pop(asset_id, None)

    def _start_stderr_reader(self, asset_id: str, process: subprocess.Popen) -> None:
        if process.stderr is None:
            return

        def reader() -> None:
            pattern = re.compile(
                r"^(?P<file>.*?):\s*(?P<pct>\d+)%\|.*?(?P<done>[\d\.]+)(?P<done_unit>[KMG]?)(?:B)?/(?P<total>[\d\.]+)(?P<total_unit>[KMG]?)(?:B)?"
            )
            files_pattern = re.compile(
                r"^Fetching\s+(?P<total>\d+)\s+files:\s+(?P<pct>\d+)%\|.*?(?P<done>\d+)/(?P=total)"
            )
            unit_map = {"": 1, "K": 1024, "M": 1024 ** 2, "G": 1024 ** 3}
            for line in process.stderr:
                cleaned = line.replace("\r", "").rstrip()
                if cleaned:
                    try:
                        sys.stderr.write(cleaned + "\n")
                        sys.stderr.flush()
                    except Exception:
                        pass
                match = pattern.search(cleaned)
                if match:
                    pct = float(match.group("pct"))
                    done_unit = match.group("done_unit") or ""
                    total_unit = match.group("total_unit") or ""
                    done = float(match.group("done")) * unit_map.get(done_unit, 1)
                    total = float(match.group("total")) * unit_map.get(total_unit, 1)
                    filename = match.group("file").strip()
                    bytes_downloaded = int(done) if done_unit or total_unit else None
                    bytes_total = int(total) if done_unit or total_unit else None
                    detail = f"Downloading {filename}"
                else:
                    match = files_pattern.search(cleaned)
                    if not match:
                        continue
                    pct = float(match.group("pct"))
                    done = int(match.group("done"))
                    total = int(match.group("total"))
                    filename = "Fetching files"
                    bytes_downloaded = None
                    bytes_total = None
                    detail = f"Fetching files ({done}/{total})"
                write_progress(
                    asset_id,
                    AssetProgress(
                        status=AssetStatus.INSTALLING,
                        stage="downloading",
                        headline="Downloading embedding model",
                        detail=detail,
                        message=f"{int(pct)}% complete",
                        progress_bar="determinate",
                        percent=pct,
                        bytes_downloaded=bytes_downloaded,
                        bytes_total=bytes_total,
                        current_file=filename,
                        phase="downloading",
                        updated_at=datetime.now(timezone.utc).isoformat(),
                    ),
                )

        threading.Thread(target=reader, daemon=True).start()
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
        if progress and self._should_clear_progress(asset_id, progress.status):
            clear_progress(asset_id)
            clear_cancel(asset_id)
            progress = None
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

    def _manifest_exists(self, asset_id: str) -> bool:
        return (embeddings_root() / asset_id / "manifest.json").exists()

    def _asset_dir_exists(self, asset_id: str) -> bool:
        return (embeddings_root() / asset_id).exists()

    def _should_clear_progress(self, asset_id: str, status: AssetStatus) -> bool:
        if not self._asset_dir_exists(asset_id):
            return True
        if status == AssetStatus.INSTALLED and not self._manifest_exists(asset_id):
            return True
        return False
