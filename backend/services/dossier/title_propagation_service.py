from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any

from config.paths import (
    dossiers_schemas_artifacts_root,
    dossiers_georefs_artifacts_root,
    dossiers_state_root,
)


class TitlePropagationService:
    """
    Propagate updated dossier titles to artifact metadata snapshots and indices.
    This avoids changing content-hash IDs by keeping title in metadata only.
    """

    def __init__(self) -> None:
        self.backend = Path(__file__).resolve().parents[2]

    def propagate(self, dossier_id: str, new_title: str) -> int:
        changed = 0
        dossier_id = str(dossier_id)

        # Update schema artifacts
        sch_dir = dossiers_schemas_artifacts_root(dossier_id)
        if sch_dir.exists():
            for p in sch_dir.glob("*.json"):
                try:
                    data = json.loads(p.read_text(encoding="utf-8") or "{}")
                    md = (data.get("metadata") or {})
                    if md.get("dossier_title_snapshot") != new_title:
                        md["dossier_title_snapshot"] = new_title
                        data["metadata"] = md
                        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                        changed += 1
                except Exception:
                    pass

        # Update georef artifacts
        gr_dir = dossiers_georefs_artifacts_root(dossier_id)
        if gr_dir.exists():
            for p in gr_dir.glob("*.json"):
                try:
                    data = json.loads(p.read_text(encoding="utf-8") or "{}")
                    md = (data.get("metadata") or {})
                    if md.get("dossier_title_snapshot") != new_title:
                        md["dossier_title_snapshot"] = new_title
                        data["metadata"] = md
                        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                        changed += 1
                except Exception:
                    pass

        # Update indices
        state_root = dossiers_state_root()
        idx_paths = [
            state_root / "schemas_index.json",
            state_root / "georefs_index.json",
        ]
        for idx in idx_paths:
            try:
                if idx.exists():
                    obj: Dict[str, Any] = json.loads(idx.read_text(encoding="utf-8") or "{}")
                    # Detect key present
                    if "schemas" in obj:
                        arr = obj.get("schemas", [])
                        for e in arr:
                            if (e or {}).get("dossier_id") == dossier_id and (e or {}).get("dossier_title_snapshot") != new_title:
                                e["dossier_title_snapshot"] = new_title
                                changed += 1
                        obj["schemas"] = arr
                    if "georefs" in obj:
                        arr = obj.get("georefs", [])
                        for e in arr:
                            if (e or {}).get("dossier_id") == dossier_id and (e or {}).get("dossier_title_snapshot") != new_title:
                                e["dossier_title_snapshot"] = new_title
                                changed += 1
                        obj["georefs"] = arr
                    idx.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass

        return changed


