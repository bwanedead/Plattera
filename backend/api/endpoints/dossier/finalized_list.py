from fastapi import APIRouter, HTTPException
from pathlib import Path
import json

from config.paths import dossiers_state_root, dossiers_views_root
from services.dossier.management_service import DossierManagementService
from services.dossier.final_registry_service import FinalRegistryService

router = APIRouter()


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def _load_pointer_snapshot(dossier_id: str) -> dict:
    pointer_path = dossiers_views_root() / dossier_id / "final" / "dossier_final.json"
    if not pointer_path.exists():
        return {}
    try:
        with open(pointer_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


@router.get("/finalized/list")
async def list_finalized():
    try:
        mgmt = DossierManagementService()
        reg = FinalRegistryService()
        out = []
        dossiers = mgmt.list_dossiers(limit=5000, offset=0)
        for dossier in dossiers:
            dossier_id = str(getattr(dossier, "id", "") or "").strip()
            if not dossier_id:
                continue
            segments = reg.list_finals(dossier_id)
            if not isinstance(segments, dict):
                continue
            live_segment_entries = [
                entry
                for entry in segments.values()
                if isinstance(entry, dict)
                and isinstance(entry.get("transcription_id"), str)
                and entry.get("transcription_id")
                and isinstance(entry.get("draft_id"), str)
                and entry.get("draft_id")
            ]
            if not live_segment_entries:
                continue
            pointer = _load_pointer_snapshot(dossier_id)
            latest_set_at = max(
                (
                    str(e.get("set_at") or "")
                    for e in live_segment_entries
                    if isinstance(e.get("set_at"), str)
                ),
                default="",
            )
            out.append(
                {
                    "dossier_id": dossier_id,
                    "title": pointer.get("dossier_title") or getattr(dossier, "title", None),
                    "latest_generated_at": pointer.get("generated_at") or latest_set_at or None,
                    "text_length": (pointer.get("counts") or {}).get("text_length"),
                    "section_count": len(live_segment_entries),
                    "has_errors": bool(pointer.get("errors")),
                }
            )
        out.sort(key=lambda e: e.get("latest_generated_at", ""), reverse=True)
        _atomic_write_json(dossiers_state_root() / "finalized_index.json", {"finalized": out})
        return {"success": True, "finalized": out}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

