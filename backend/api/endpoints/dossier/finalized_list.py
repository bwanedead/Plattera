from fastapi import APIRouter, HTTPException
from pathlib import Path
import json

from config.paths import dossiers_state_root, dossiers_views_root
from services.dossier.management_service import DossierManagementService

router = APIRouter()


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def _is_live_finalized_entry(entry: dict, mgmt: DossierManagementService) -> bool:
    dossier_id = str((entry or {}).get("dossier_id") or "").strip()
    if not dossier_id:
        return False
    if mgmt.get_dossier(dossier_id) is None:
        return False
    pointer_path = dossiers_views_root() / dossier_id / "final" / "dossier_final.json"
    return pointer_path.exists()


@router.get("/finalized/list")
async def list_finalized():
    try:
        mgmt = DossierManagementService()
        index_path = dossiers_state_root() / "finalized_index.json"
        if index_path.exists():
            with open(index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            entries = data.get("finalized", []) if isinstance(data, dict) else []
            if not isinstance(entries, list):
                entries = []
            live_entries = [e for e in entries if isinstance(e, dict) and _is_live_finalized_entry(e, mgmt)]
            live_entries.sort(key=lambda e: e.get("latest_generated_at", ""), reverse=True)
            if len(live_entries) != len(entries):
                _atomic_write_json(index_path, {"finalized": live_entries})
            return {"success": True, "finalized": live_entries}
        # Fallback scan
        trans_root = dossiers_views_root()
        out = []
        if trans_root.exists():
            for did_dir in trans_root.iterdir():
                if not did_dir.is_dir():
                    continue
                if mgmt.get_dossier(did_dir.name) is None:
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

