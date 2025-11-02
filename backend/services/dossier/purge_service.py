import logging
import json
import shutil
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class DossierPurgeService:
    def __init__(self) -> None:
        self.backend_dir = Path(__file__).resolve().parents[2]

    def _collect_transcription_ids(self, dossier_id: str) -> List[str]:
        ids: List[str] = []

        # Preferred: associations file
        assoc_file = self.backend_dir / "dossiers_data" / "associations" / f"assoc_{dossier_id}.json"
        try:
            if assoc_file.exists():
                with assoc_file.open("r", encoding="utf-8") as f:
                    data = json.load(f) or {}
                if isinstance(data, dict):
                    associations = data.get("associations")
                    if isinstance(associations, list):
                        for it in associations:
                            tid = (it or {}).get("transcription_id")
                            if tid:
                                ids.append(str(tid))
                    else:
                        items = data.get("transcriptions") or data.get("items") or []
                        for it in items:
                            tid = it.get("transcription_id") or it.get("id") or it.get("transcriptionId")
                            if tid:
                                ids.append(str(tid))
        except Exception as e:
            logger.warning(f"⚠️ Failed to read associations file for {dossier_id}: {e}")

        # Fallback: association service
        if not ids:
            try:
                from .association_service import TranscriptionAssociationService  # local import to avoid cycles
                svc = TranscriptionAssociationService()
                entries = svc.get_dossier_transcriptions(str(dossier_id)) or []
                for e in entries:
                    tid = getattr(e, "transcription_id", None)
                    if tid:
                        ids.append(str(tid))
            except Exception as e:
                logger.debug(f"(non-fatal) assoc service fallback failed: {e}")

        # Last resort: scan structured views folders
        if not ids:
            try:
                dossier_root = self.backend_dir / "dossiers_data" / "views" / "transcriptions" / str(dossier_id)
                if dossier_root.exists():
                    for child in dossier_root.iterdir():
                        if child.is_dir():
                            ids.append(child.name)
            except Exception as e:
                logger.debug(f"(non-fatal) views scan failed: {e}")

        return sorted(set(ids))

    def _remove_if_exists(self, p: Path, removed_files: List[str], removed_dirs: List[str]) -> None:
        try:
            if p.is_dir():
                shutil.rmtree(p)
                removed_dirs.append(str(p))
            elif p.exists():
                p.unlink()
                removed_files.append(str(p))
        except Exception as e:
            logger.warning(f"⚠️ Failed to remove {p}: {e}")

    def _scrub_processing_jobs(self, dossier_id: str) -> int:
        removed = 0
        try:
            from services.image_queue.job_store import ImageToTextJobStore
            store = ImageToTextJobStore()
            index = store._read_index()  # type: ignore[attr-defined]
            to_remove: List[str] = []
            for job_id in list(index.keys()):
                data = store.get(job_id) or {}
                if (data.get("dossier_id") or "") == str(dossier_id):
                    job_path = store._job_path(job_id)  # type: ignore[attr-defined]
                    try:
                        if job_path.exists():
                            job_path.unlink()
                            removed += 1
                    except Exception:
                        pass
                    to_remove.append(job_id)
            if to_remove:
                for jid in to_remove:
                    index.pop(jid, None)
                store._write_index(index)  # type: ignore[attr-defined]
        except Exception as e:
            logger.warning(f"⚠️ Failed to scrub processing jobs for dossier {dossier_id}: {e}")
        return removed

    def purge_dossier(self, dossier_id: str, scrub_jobs: bool = True) -> Dict[str, Any]:
        removed_files: List[str] = []
        removed_dirs: List[str] = []
        removed_images = 0
        removed_jobs = 0

        transcription_ids = self._collect_transcription_ids(dossier_id)

        mgmt_file = self.backend_dir / "dossiers_data" / "management" / f"dossier_{dossier_id}.json"
        assoc_file = self.backend_dir / "dossiers_data" / "associations" / f"assoc_{dossier_id}.json"
        views_dossier_dir = self.backend_dir / "dossiers_data" / "views" / "transcriptions" / str(dossier_id)
        state_dir = self.backend_dir / "dossiers_data" / "state" / str(dossier_id)
        navigation_dir = self.backend_dir / "dossiers_data" / "navigation" / str(dossier_id)
        views_root = self.backend_dir / "dossiers_data" / "views" / "transcriptions"

        # Remove structured folders/files
        self._remove_if_exists(views_dossier_dir, removed_files, removed_dirs)
        self._remove_if_exists(assoc_file, removed_files, removed_dirs)
        self._remove_if_exists(mgmt_file, removed_files, removed_dirs)
        self._remove_if_exists(state_dir, removed_files, removed_dirs)
        self._remove_if_exists(navigation_dir, removed_files, removed_dirs)

        # Legacy flat files for each transcription id
        try:
            for tid in transcription_ids:
                for p in list(views_root.glob(f"{tid}.json")) + list(views_root.glob(f"{tid}_v*.json")):
                    self._remove_if_exists(p, removed_files, removed_dirs)
                for cp in [
                    views_root / f"{tid}_consensus_llm.json",
                    views_root / f"{tid}_consensus_alignment.json",
                ]:
                    self._remove_if_exists(cp, removed_files, removed_dirs)
        except Exception as e:
            logger.debug(f"(non-fatal) legacy cleanup failed: {e}")

        # Images for each transcription id
        try:
            if transcription_ids:
                from .image_storage_service import ImageStorageService
                iss = ImageStorageService()
                for tid in transcription_ids:
                    try:
                        ok = iss.delete_images(str(tid))
                        if ok:
                            removed_images += 1
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"⚠️ Image purge encountered issues: {e}")

        # Processing jobs scrub (optional)
        if scrub_jobs:
            removed_jobs = self._scrub_processing_jobs(dossier_id)

        summary = {
            "success": True,
            "dossier_id": str(dossier_id),
            "transcription_ids": transcription_ids,
            "removed_files": removed_files,
            "removed_dirs": removed_dirs,
            "removed_images_groups": removed_images,
            "removed_jobs": removed_jobs,
        }

        logger.info(
            f"PURGE_SUMMARY dossier={dossier_id} "
            f"assoc_tids={len(transcription_ids)} "
            f"files={len(removed_files)} dirs={len(removed_dirs)} "
            f"image_groups={removed_images} jobs={removed_jobs}"
        )
        return summary


