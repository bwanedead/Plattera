"""
Title Lock Service
==================

Derives a stable dossier title from the first segment's consensus (if available)
and locks the dossier title accordingly. Intended for retroactive fixes where
later segments overwrote the original title.

Responsibilities:
- Compute best title candidate from first segment
- Update dossier title if a better first-segment title exists
- Batch operation across all dossiers
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from config.paths import dossiers_views_root
from .management_service import DossierManagementService
from .association_service import TranscriptionAssociationService


logger = logging.getLogger(__name__)


class TitleLockService:
    def __init__(self) -> None:
        self.transcriptions_root = dossiers_views_root()
        self.mgmt = DossierManagementService()
        self.assoc = TranscriptionAssociationService()

    def _load_consensus_title(self, dossier_id: str, transcription_id: str) -> Optional[str]:
        consensus_file = self.transcriptions_root / str(dossier_id) / str(transcription_id) / "consensus" / f"llm_{transcription_id}.json"
        try:
            if consensus_file.exists():
                data = json.loads(consensus_file.read_text(encoding="utf-8") or "{}")
                title = data.get("title")
                if isinstance(title, str) and title.strip():
                    return title.strip()
        except Exception as e:
            logger.debug(f"TitleLock: failed reading consensus for {dossier_id}/{transcription_id}: {e}")
        return None

    def compute_first_segment_title(self, dossier_id: str) -> Optional[str]:
        try:
            trans = self.assoc.get_dossier_transcriptions(str(dossier_id))
            if not trans:
                return None
            first = trans[0]
            tid = getattr(first, "transcription_id", None)
            if not tid:
                return None
            # Prefer consensus title if present
            title = self._load_consensus_title(str(dossier_id), str(tid))
            if title:
                return title
            # No strong signal available; skip change
            return None
        except Exception as e:
            logger.debug(f"TitleLock: compute title failed for dossier {dossier_id}: {e}")
            return None

    def lock_title_from_first_segment(self, dossier_id: str) -> Dict[str, Any]:
        dossier = self.mgmt.get_dossier(str(dossier_id))
        if not dossier:
            return {"updated": False, "dossier_id": str(dossier_id), "reason": "not_found"}

        current_title = (getattr(dossier, "title", "") or "").strip()
        candidate = self.compute_first_segment_title(str(dossier_id))
        if not candidate:
            return {"updated": False, "dossier_id": str(dossier_id), "reason": "no_first_segment_title", "current_title": current_title}

        if current_title == candidate:
            return {"updated": False, "dossier_id": str(dossier_id), "reason": "already_locked", "current_title": current_title}

        try:
            self.mgmt.update_dossier(str(dossier_id), {"title": candidate})
            return {"updated": True, "dossier_id": str(dossier_id), "new_title": candidate}
        except Exception as e:
            return {"updated": False, "dossier_id": str(dossier_id), "reason": f"update_failed:{e}"}

    def lock_all(self) -> Dict[str, Any]:
        results = {"updated": [], "skipped": [], "errors": []}
        try:
            dossiers = self.mgmt.list_dossiers(limit=10_000, offset=0)
        except Exception as e:
            return {"error": f"list_failed:{e}"}

        for d in dossiers:
            try:
                out = self.lock_title_from_first_segment(d.id)
                if out.get("updated"):
                    results["updated"].append(out["dossier_id"])
                else:
                    results["skipped"].append({"dossier_id": out.get("dossier_id"), "reason": out.get("reason")})
            except Exception as e:
                results["errors"].append({"dossier_id": d.id, "error": str(e)})
        return results


