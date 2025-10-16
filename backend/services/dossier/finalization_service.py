from __future__ import annotations

import json
import hashlib
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from services.dossier.management_service import DossierManagementService
from services.dossier.view_service import DossierViewService
from services.dossier.final_registry_service import FinalRegistryService


class FinalizationService:
    def __init__(self) -> None:
        self._backend_dir = Path(__file__).resolve().parents[2]
        self._trans_root = self._backend_dir / "dossiers_data" / "views" / "transcriptions"
        self._state_dir = self._backend_dir / "dossiers_data" / "state"
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._state_dir / "finalized_index.json"

    def _atomic_write(self, path: Path, data: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix="final_idx_", suffix=".json", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, str(path))
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    def _extract_text(self, content: Dict[str, Any]) -> str:
        if isinstance(content, dict):
            if "sections" in content:
                sections = content.get("sections", [])
                return "\n\n".join(s.get("body", "") for s in sections if isinstance(s, dict)).strip()
            if "text" in content:
                return str(content.get("text") or "").strip()
        return ""

    def _pick_first_run(self, runs: list) -> Optional[Any]:
        if not runs:
            return None
        return sorted(runs, key=lambda r: (getattr(r, "position", 0) or 0))[0]

    def _load_with_policy(self, view_svc: DossierViewService, run: Any, dossier_id: str) -> Tuple[str, str]:
        drafts = getattr(run, "drafts", []) or []
        if not drafts:
            return ("none", "")
        # Consensus first: LLM then alignment
        cons = [d for d in drafts if isinstance(d.id, str) and ("_consensus_llm" in d.id or "_consensus_alignment" in d.id)]
        if cons:
            try:
                pick = max(cons, key=lambda d: (d.metadata or {}).get("createdAt", ""))
            except Exception:
                pick = cons[0]
            content = view_svc._load_transcription_content_scoped(pick.id, dossier_id)
            if content:
                text = self._extract_text(content)
                if text:
                    return (pick.id, text)
        # Best flag
        best = next((d for d in drafts if getattr(d, "is_best", False) or getattr(d, "isBest", False)), None)
        if best:
            content = view_svc._load_transcription_content_scoped(best.id, dossier_id)
            if content:
                text = self._extract_text(content)
                if text:
                    return (best.id, text)
        # Longest by sizeBytes
        try:
            longest = max(drafts, key=lambda d: (d.metadata or {}).get("sizeBytes", 0))
            content = view_svc._load_transcription_content_scoped(longest.id, dossier_id)
            if content:
                text = self._extract_text(content)
                if text:
                    return (longest.id, text)
        except Exception:
            pass
        # Fallback to first draft
        first = drafts[0]
        content = view_svc._load_transcription_content_scoped(first.id, dossier_id)
        if content:
            text = self._extract_text(content)
            return (first.id, text)
        return ("none", "")

    def finalize_dossier(self, dossier_id: str) -> Dict[str, Any]:
        mgmt = DossierManagementService()
        view = DossierViewService()
        reg = FinalRegistryService()

        dossier = mgmt.get_dossier(dossier_id)
        if not dossier:
            raise ValueError(f"Dossier not found: {dossier_id}")

        stitched_parts: List[str] = []
        sections: List[Dict[str, Any]] = []
        selection_map: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []

        for seg in getattr(dossier, "segments", []) or []:
            run = self._pick_first_run(getattr(seg, "runs", []) or [])
            if not run:
                continue
            transcription_id = getattr(run, "transcription_id", None) or getattr(run, "transcriptionId", None)
            if not transcription_id:
                continue

            # finals-first
            entry = reg.get_segment_final(dossier_id, str(getattr(seg, "id", "")))
            final_id = (entry or {}).get("draft_id")

            draft_id_used = None
            text_out = ""
            if isinstance(final_id, str) and final_id.strip():
                content = view._load_transcription_content_scoped(final_id, dossier_id)
                if isinstance(content, dict):
                    text_out = self._extract_text(content)
                    draft_id_used = final_id
                else:
                    errors.append({
                        "segment_id": getattr(seg, "id", ""),
                        "transcription_id": transcription_id,
                        "draft_id": final_id,
                        "reason": "Draft not found or empty"
                    })
            else:
                draft_id_used, text_out = self._load_with_policy(view, run, dossier_id)

            if text_out:
                stitched_parts.append(text_out)
                sections.append({
                    "segment_id": getattr(seg, "id", ""),
                    "order": getattr(seg, "position", 0) or 0,
                    "transcription_id": transcription_id,
                    "draft_id_used": draft_id_used,
                    "text": text_out
                })
                selection_map.append({
                    "segment_id": getattr(seg, "id", ""),
                    "transcription_id": transcription_id,
                    "draft_id_used": draft_id_used,
                    "version_type": ("consensus" if (isinstance(draft_id_used, str) and "_consensus_" in draft_id_used) else
                                     ("alignment" if (isinstance(draft_id_used, str) and "_draft_" in draft_id_used) else "raw")),
                    "version_num": (2 if (isinstance(draft_id_used, str) and draft_id_used.endswith("_v2")) else
                                    (1 if (isinstance(draft_id_used, str) and draft_id_used.endswith("_v1")) else None)),
                    "size_bytes": len(text_out.encode("utf-8"))
                })

        stitched_text = "\n\n".join(stitched_parts)
        sha = hashlib.sha256(stitched_text.encode("utf-8")).hexdigest()

        # Write snapshot
        final_dir = self._trans_root / str(dossier_id) / "final"
        final_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        snap_path = final_dir / f"dossier_final_{ts}.json"
        pointer_path = final_dir / "dossier_final.json"

        payload = {
            "dossier_id": dossier_id,
            "dossier_title": getattr(dossier, "title", None),
            "generated_at": datetime.utcnow().isoformat(),
            "stitched_text": stitched_text,
            "sections": sections,
            "selection_map": selection_map,
            "counts": { "segments": len(sections), "text_length": len(stitched_text) },
            "errors": errors,
            "sha256": sha
        }

        with open(snap_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        with open(pointer_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

        # Update index
        index = { "finalized": [] }
        if self._index_path.exists():
            try:
                with open(self._index_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        index = data
            except Exception:
                index = { "finalized": [] }
        entries = [e for e in index.get("finalized", []) if (e or {}).get("dossier_id") != str(dossier_id)]
        entries.append({
            "dossier_id": dossier_id,
            "title": getattr(dossier, "title", None),
            "latest_generated_at": payload["generated_at"],
            "text_length": len(stitched_text),
            "section_count": len(sections),
            "has_errors": bool(errors)
        })
        index["finalized"] = sorted(entries, key=lambda e: e.get("latest_generated_at", ""), reverse=True)
        self._atomic_write(self._index_path, index)

        return payload




