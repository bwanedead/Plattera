from __future__ import annotations

import hashlib
import json
import shutil
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from config.paths import embeddings_root
from .models import AssetManifest, AssetFileEntry, AssetProgress, AssetStatus
from .progress_store import cancel_requested, clear_cancel, read_progress, write_progress

DownloaderFn = Callable[[str, str, Path], str]


CRITICAL_FILENAMES = {
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "vocab.txt",
    "model.safetensors",
    "pytorch_model.bin",
}


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _list_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if path.is_file():
            yield path


def _default_downloader(repo_id: str, revision: str, target_dir: Path) -> str:
    from huggingface_hub import HfApi, snapshot_download

    target_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=repo_id,
        revision=revision,
        local_dir=str(target_dir),
        cache_dir=str(target_dir.parent / "hf_cache"),
        resume_download=True,
    )
    api = HfApi()
    info = api.model_info(repo_id=repo_id, revision=revision)
    return info.sha or revision


def _smoke_test(model_dir: Path) -> str:
    try:
        from transformers import AutoConfig
    except Exception:
        return "skipped"

    try:
        AutoConfig.from_pretrained(str(model_dir), local_files_only=True)
        return "passed"
    except Exception:
        return "failed"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_bytes(value: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def _resolve_repo_info(repo_id: str, revision: str) -> Tuple[Optional[str], Optional[int], Optional[List[str]]]:
    try:
        from huggingface_hub import HfApi
    except Exception:
        return None, None, None

    try:
        info = HfApi().model_info(repo_id=repo_id, revision=revision)
    except Exception:
        return None, None, None

    total = 0
    siblings = getattr(info, "siblings", None) or []
    filenames: List[str] = []
    for sibling in siblings:
        filename = getattr(sibling, "rfilename", None)
        if isinstance(filename, str):
            filenames.append(filename)
        size = getattr(sibling, "size", None)
        if isinstance(size, int):
            total += size
    resolved = getattr(info, "sha", None) or revision
    return resolved, (total or None), (filenames or None)


def _scan_download_progress(target_dir: Path) -> tuple[int, Optional[str]]:
    bytes_downloaded = 0
    latest_path: Optional[Path] = None
    latest_mtime = 0.0
    if not target_dir.exists():
        return 0, None
    for path in target_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        bytes_downloaded += stat.st_size
        if stat.st_mtime > latest_mtime:
            latest_mtime = stat.st_mtime
            latest_path = path
    current_file = latest_path.relative_to(target_dir).as_posix() if latest_path else None
    return bytes_downloaded, current_file


def _cache_repo_root(cache_dir: Path, repo_id: str) -> Path:
    repo_key = repo_id.replace("/", "--")
    return cache_dir / f"models--{repo_key}"


def _scan_cache_progress(cache_dir: Path, repo_id: str) -> int:
    repo_root = _cache_repo_root(cache_dir, repo_id)
    blobs_dir = repo_root / "blobs"
    if not blobs_dir.exists():
        return 0
    total = 0
    for path in blobs_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            total += path.stat().st_size
        except OSError:
            continue
    return total


def _staging_dir(asset_id: str) -> Path:
    nonce = uuid.uuid4().hex[:8]
    return embeddings_root() / f"{asset_id}.staging.{nonce}"


def _commit_staging(staging_dir: Path, final_dir: Path) -> None:
    backup_dir = None
    if final_dir.exists():
        backup_dir = final_dir.parent / f"{final_dir.name}.bak.{uuid.uuid4().hex[:6]}"
        shutil.move(str(final_dir), str(backup_dir))
    try:
        shutil.move(str(staging_dir), str(final_dir))
    except Exception:
        if backup_dir and backup_dir.exists():
            try:
                shutil.move(str(backup_dir), str(final_dir))
            except Exception:
                pass
        raise
    if backup_dir and backup_dir.exists():
        shutil.rmtree(backup_dir, ignore_errors=True)


def _download_heartbeat(
    *,
    asset_id: str,
    target_dir: Path,
    bytes_total: Optional[int],
    repo_id: str,
    cache_dir: Path,
    stop_event: threading.Event,
) -> None:
    while not stop_event.wait(1.0):
        if cancel_requested(asset_id):
            return
        existing = read_progress(asset_id)
        if existing and existing.progress_bar == "determinate":
            return
        bytes_downloaded = _scan_cache_progress(cache_dir, repo_id)
        current_file = None
        if bytes_downloaded == 0:
            bytes_downloaded, current_file = _scan_download_progress(target_dir)
        progress_bar = "indeterminate"
        percent = None
        if bytes_total and bytes_total > 0:
            percent = min(99.0, round((bytes_downloaded / bytes_total) * 100, 1))
            progress_bar = "determinate"

        detail = "Downloading model files"
        if current_file:
            detail = f"Downloading {current_file}"

        message = detail
        if bytes_downloaded > 0:
            downloaded_label = _format_bytes(bytes_downloaded)
            total_label = _format_bytes(bytes_total) if bytes_total else None
            if total_label:
                message = f"{downloaded_label} of {total_label}"
            else:
                message = f"{downloaded_label} downloaded"
        if percent is not None and bytes_total:
            message = f"{percent}% of { _format_bytes(bytes_total) }"

        write_progress(
            asset_id,
            AssetProgress(
                status=AssetStatus.INSTALLING,
                stage="downloading",
                headline="Downloading embedding model",
                detail=detail,
                message=message,
                progress_bar=progress_bar,
                percent=percent,
                bytes_downloaded=bytes_downloaded or None,
                bytes_total=bytes_total,
                current_file=current_file,
                phase="downloading",
                updated_at=_now_iso(),
            ),
        )


@dataclass
class EmbeddingInstaller:
    downloader: DownloaderFn = _default_downloader

    def install(self, *, asset_id: str, repo_id: str, revision: str) -> AssetManifest:
        if cancel_requested(asset_id):
            clear_cancel(asset_id)
            raise RuntimeError("stopped_before_start")

        write_progress(
            asset_id,
            AssetProgress(
                status=AssetStatus.INSTALLING,
                stage="initializing",
                headline="Preparing download",
                detail="Initializing embedding installer",
                message="Preparing install",
                progress_bar="indeterminate",
                phase="initializing",
                updated_at=_now_iso(),
            ),
        )

        final_dir = embeddings_root() / asset_id
        staging_dir = _staging_dir(asset_id)
        resolved_revision, bytes_total, _expected_files = _resolve_repo_info(repo_id, revision)
        resolved_revision = resolved_revision or revision
        if bytes_total:
            total_free = shutil.disk_usage(str(embeddings_root())).free
            if total_free < bytes_total:
                write_progress(
                    asset_id,
                    AssetProgress(
                        status=AssetStatus.FAILED,
                        stage="error",
                        headline="Install failed",
                        detail="insufficient_disk_space",
                        message=f"Need {_format_bytes(bytes_total)} free, have {_format_bytes(total_free)}",
                        progress_bar="none",
                        phase="failed",
                        updated_at=_now_iso(),
                    ),
                )
                raise RuntimeError("insufficient_disk_space")
        stop_event = threading.Event()
        heartbeat: Optional[threading.Thread] = None
        committed = False
        final_written = False

        write_progress(
            asset_id,
            AssetProgress(
                status=AssetStatus.INSTALLING,
                stage="downloading",
                headline="Downloading embedding model",
                detail="Downloading model files",
                message="Downloading model files",
                progress_bar="indeterminate",
                bytes_total=bytes_total,
                phase="downloading",
                updated_at=_now_iso(),
            ),
        )

        try:
            heartbeat = threading.Thread(
                target=_download_heartbeat,
                kwargs={
                    "asset_id": asset_id,
                    "target_dir": staging_dir,
                    "bytes_total": bytes_total,
                    "repo_id": repo_id,
                    "cache_dir": staging_dir.parent / "hf_cache",
                    "stop_event": stop_event,
                },
                daemon=True,
            )
            heartbeat.start()
            try:
                resolved_revision = self.downloader(repo_id, resolved_revision, staging_dir)
            finally:
                stop_event.set()
                if heartbeat:
                    heartbeat.join(timeout=2.0)

            if cancel_requested(asset_id):
                write_progress(
                    asset_id,
                    AssetProgress(
                        status=AssetStatus.STOPPED,
                        stage="stopped",
                        headline="Download stopped",
                        detail="Download stopped after download step",
                        message="Stopped",
                        progress_bar="none",
                        phase="stopped",
                        updated_at=_now_iso(),
                    ),
                )
                raise RuntimeError("stopped")

            write_progress(
                asset_id,
                AssetProgress(
                    status=AssetStatus.INSTALLING,
                    stage="verifying",
                    headline="Verifying download",
                    detail="Hashing critical files",
                    message="Hashing critical files",
                    progress_bar="indeterminate",
                    phase="verifying",
                    updated_at=_now_iso(),
                ),
            )

            files: List[AssetFileEntry] = []
            total_bytes = 0
            for path in _list_files(staging_dir):
                rel = path.relative_to(staging_dir).as_posix()
                size = path.stat().st_size
                total_bytes += size
                sha = _hash_file(path) if path.name in CRITICAL_FILENAMES else None
                files.append(AssetFileEntry(path=rel, bytes=size, sha256=sha))

            smoke_result = _smoke_test(staging_dir)

            write_progress(
                asset_id,
                AssetProgress(
                    status=AssetStatus.INSTALLING,
                    stage="writing_manifest",
                    headline="Finalizing install",
                    detail="Writing manifest",
                    message="Writing manifest",
                    progress_bar="indeterminate",
                    phase="finalizing",
                    updated_at=_now_iso(),
                ),
            )

            _commit_staging(staging_dir, final_dir)

            manifest = AssetManifest(
                asset_id=asset_id,
                source=f"hf:{repo_id}",
                requested_revision=revision,
                resolved_revision=resolved_revision,
                installed_at=datetime.now(timezone.utc).isoformat(),
                files=files,
                total_bytes=total_bytes,
                smoke_test=smoke_result,
            )

            manifest_path = final_dir / "manifest.json"
            tmp_path = final_dir / "manifest.json.tmp"
            tmp_path.write_text(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_path.replace(manifest_path)
            final_written = True
            committed = True

            write_progress(
                asset_id,
                AssetProgress(
                    status=AssetStatus.INSTALLED,
                    stage="complete",
                    headline="Install complete",
                    detail="Embedding model is ready",
                    message="Install complete",
                    progress_bar="none",
                    phase="complete",
                    updated_at=_now_iso(),
                ),
            )

            return manifest
        finally:
            if not committed and staging_dir.exists():
                shutil.rmtree(staging_dir, ignore_errors=True)
            if not final_written and final_dir.exists():
                shutil.rmtree(final_dir, ignore_errors=True)
