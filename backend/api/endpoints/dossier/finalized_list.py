from fastapi import APIRouter, HTTPException
from pathlib import Path
import json

from config.paths import dossiers_state_root, dossiers_views_root

router = APIRouter()


@router.get("/finalized/list")
async def list_finalized():
    try:
        index_path = dossiers_state_root() / "finalized_index.json"
        if index_path.exists():
            with open(index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {"success": True, "finalized": data.get("finalized", [])}
        # Fallback scan
        trans_root = dossiers_views_root()
        out = []
        if trans_root.exists():
            for did_dir in trans_root.iterdir():
                if not did_dir.is_dir():
                    continue
                p = did_dir / "final" / "dossier_final.json"
                if p.exists():
                    try:
                        with open(p, "r", encoding="utf-8") as f:
                            snap = json.load(f)
                        out.append(
                            {
                                "dossier_id": snap.get("dossier_id") or did_dir.name,
                                "title": snap.get("dossier_title"),
                                "latest_generated_at": snap.get("generated_at"),
                                "text_length": (snap.get("counts") or {}).get("text_length"),
                                "section_count": (snap.get("counts") or {}).get("segments"),
                                "has_errors": bool(snap.get("errors")),
                            }
                        )
                    except Exception:
                        pass
        out.sort(key=lambda e: e.get("latest_generated_at", ""), reverse=True)
        return {"success": True, "finalized": out}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

