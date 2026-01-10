from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from config.paths import embeddings_root
from services.assets.registry import EMBEDDING_MODEL_ASSET_ID
from services.assets.service import AssetsService


@dataclass(frozen=True)
class EmbeddingModelInfo:
    asset_id: str
    model_dir: Path
    manifest: Optional[Dict[str, Any]] = None


class EmbeddingAssetMissingError(RuntimeError):
    def __init__(self, asset_id: str) -> None:
        super().__init__(f"embedding_asset_missing:{asset_id}")
        self.asset_id = asset_id


def resolve_embedding_model(assets_service: AssetsService, asset_id: str = EMBEDDING_MODEL_ASSET_ID) -> EmbeddingModelInfo:
    status = assets_service.get_asset_status(asset_id)
    if status.value != "installed":
        raise EmbeddingAssetMissingError(asset_id)
    model_dir = embeddings_root() / asset_id
    manifest_path = model_dir / "manifest.json"
    manifest: Optional[Dict[str, Any]] = None
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = None
    return EmbeddingModelInfo(asset_id=asset_id, model_dir=model_dir, manifest=manifest)

