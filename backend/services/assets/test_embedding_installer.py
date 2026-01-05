from __future__ import annotations

import json
from pathlib import Path

from .embedding_installer import EmbeddingInstaller
from .progress_store import request_cancel
import config.paths as paths_mod


def _stub_downloader(repo_id: str, revision: str, target_dir: Path) -> str:
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "config.json").write_text("{}", encoding="utf-8")
    (target_dir / "tokenizer.json").write_text("{}", encoding="utf-8")
    (target_dir / "model.safetensors").write_text("weights", encoding="utf-8")
    return "rev123"


def _patch_assets_roots(monkeypatch, root: Path) -> None:
    def _assets_root() -> Path:
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _assets_state_root() -> Path:
        state_root = root / "state"
        state_root.mkdir(parents=True, exist_ok=True)
        return state_root

    def _embeddings_root() -> Path:
        emb_root = root / "embeddings"
        emb_root.mkdir(parents=True, exist_ok=True)
        return emb_root

    monkeypatch.setattr(paths_mod, "assets_root", _assets_root)
    monkeypatch.setattr(paths_mod, "assets_state_root", _assets_state_root)
    monkeypatch.setattr(paths_mod, "embeddings_root", _embeddings_root)


def test_embedding_installer_writes_manifest_and_hashes(tmp_path, monkeypatch) -> None:
    _patch_assets_roots(monkeypatch, tmp_path)
    installer = EmbeddingInstaller(downloader=_stub_downloader)

    manifest = installer.install(
        asset_id="embedding_model_bge_small_en_v1_5",
        repo_id="BAAI/bge-small-en-v1.5",
        revision="main",
    )

    manifest_path = tmp_path / "embeddings" / "embedding_model_bge_small_en_v1_5" / "manifest.json"
    assert manifest_path.exists()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["revision"] == "rev123"
    files = {f["path"]: f for f in data["files"]}
    assert files["config.json"]["sha256"]
    assert files["tokenizer.json"]["sha256"]
    assert files["model.safetensors"]["sha256"]
    assert manifest.total_bytes > 0


def test_embedding_installer_cancel_before_start(tmp_path, monkeypatch) -> None:
    _patch_assets_roots(monkeypatch, tmp_path)
    request_cancel("embedding_model_bge_small_en_v1_5")
    installer = EmbeddingInstaller(downloader=_stub_downloader)

    raised = False
    try:
        installer.install(
            asset_id="embedding_model_bge_small_en_v1_5",
            repo_id="BAAI/bge-small-en-v1.5",
            revision="main",
        )
    except RuntimeError:
        raised = True

    assert raised is True
