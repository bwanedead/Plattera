from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from config.paths import assets_state_root
from .models import AssetProgress, AssetStatus


def _progress_path(asset_id: str) -> Path:
    return assets_state_root() / f"{asset_id}_progress.json"


def _cancel_path(asset_id: str) -> Path:
    return assets_state_root() / f"{asset_id}_cancel.json"


def write_progress(asset_id: str, progress: AssetProgress) -> None:
    path = _progress_path(asset_id)
    data = progress.to_dict()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_progress(asset_id: str) -> Optional[AssetProgress]:
    path = _progress_path(asset_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    status = data.get("status") or AssetStatus.MISSING.value
    return AssetProgress(
        status=AssetStatus(status),
        stage=data.get("stage"),
        message=data.get("message"),
        percent=data.get("percent"),
        error=data.get("error"),
    )


def request_cancel(asset_id: str) -> None:
    path = _cancel_path(asset_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("1", encoding="utf-8")


def clear_cancel(asset_id: str) -> None:
    path = _cancel_path(asset_id)
    if path.exists():
        path.unlink()


def clear_progress(asset_id: str) -> None:
    path = _progress_path(asset_id)
    if path.exists():
        path.unlink()


def cancel_requested(asset_id: str) -> bool:
    return _cancel_path(asset_id).exists()
