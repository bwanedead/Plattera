from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from config.paths import embeddings_root
from .models import AssetManifest, AssetFileEntry, AssetProgress, AssetStatus
from .progress_store import cancel_requested, clear_cancel, request_cancel, write_progress

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
        local_dir_use_symlinks=False,
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


@dataclass
class EmbeddingInstaller:
    downloader: DownloaderFn = _default_downloader

    def install(self, *, asset_id: str, repo_id: str, revision: str) -> AssetManifest:
        if cancel_requested(asset_id):
            clear_cancel(asset_id)
            raise RuntimeError("cancel_requested_before_start")

        write_progress(
            asset_id,
            AssetProgress(status=AssetStatus.INSTALLING, stage="initializing", message="Preparing install"),
        )

        target_dir = embeddings_root() / asset_id
        resolved_revision = revision

        write_progress(
            asset_id,
            AssetProgress(status=AssetStatus.INSTALLING, stage="downloading", message="Downloading model files"),
        )

        resolved_revision = self.downloader(repo_id, revision, target_dir)

        if cancel_requested(asset_id):
            write_progress(
                asset_id,
                AssetProgress(status=AssetStatus.CANCELED, stage="canceled", message="Install canceled"),
            )
            raise RuntimeError("install_canceled")

        write_progress(
            asset_id,
            AssetProgress(status=AssetStatus.INSTALLING, stage="verifying", message="Hashing critical files"),
        )

        files: List[AssetFileEntry] = []
        total_bytes = 0
        for path in _list_files(target_dir):
            rel = path.relative_to(target_dir).as_posix()
            size = path.stat().st_size
            total_bytes += size
            sha = _hash_file(path) if path.name in CRITICAL_FILENAMES else None
            files.append(AssetFileEntry(path=rel, bytes=size, sha256=sha))

        smoke_result = _smoke_test(target_dir)

        write_progress(
            asset_id,
            AssetProgress(status=AssetStatus.INSTALLING, stage="writing_manifest", message="Writing manifest"),
        )

        manifest = AssetManifest(
            asset_id=asset_id,
            source=f"hf:{repo_id}",
            revision=resolved_revision,
            installed_at=datetime.now(timezone.utc).isoformat(),
            files=files,
            total_bytes=total_bytes,
            smoke_test=smoke_result,
        )

        manifest_path = target_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

        write_progress(
            asset_id,
            AssetProgress(status=AssetStatus.INSTALLED, stage="complete", message="Install complete"),
        )

        return manifest
