from __future__ import annotations

from .models import AssetDefinition


EMBEDDING_MODEL_ASSET_ID = "embedding_model_bge_small_en_v1_5"


ASSET_DEFINITIONS: dict[str, AssetDefinition] = {
    "plss": AssetDefinition(
        asset_id="plss",
        display_name="PLSS data",
        kind="plss",
        source="internal:plss",
    ),
    EMBEDDING_MODEL_ASSET_ID: AssetDefinition(
        asset_id=EMBEDDING_MODEL_ASSET_ID,
        display_name="Embedding model (bge-small-en-v1.5)",
        kind="embedding_model",
        source="hf:BAAI/bge-small-en-v1.5",
        meta={
            "repo_id": "BAAI/bge-small-en-v1.5",
            "revision": "main",
        },
    ),
}
