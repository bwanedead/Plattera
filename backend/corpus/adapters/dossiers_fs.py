from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

from config.paths import (
    dossier_runs_root,
    dossiers_management_root,
    dossiers_root,
    dossiers_state_root,
    dossiers_views_root,
)


@dataclass
class DossiersFSAdapter:
    """
    Filesystem adapter over `dossiers_data/` (dev) or app data (frozen).

    This remains intentionally light; it exists so corpus + retrieval code never
    hardcodes storage paths.
    """

    # In-process cache for draft path resolution (keyed by (dossier_id, draft_id))
    _draft_path_cache: Dict[Tuple[str, str], Optional[Path]] = field(
        default_factory=dict, repr=False
    )

    def dossiers_root(self) -> Path:
        return dossiers_root()

    def transcriptions_root(self) -> Path:
        return dossiers_views_root()

    # ----- Finalized snapshots -----

    def finalized_snapshot_dir(self, dossier_id: str) -> Path:
        return dossiers_views_root() / str(dossier_id) / "final"

    def finalized_pointer_path(self, dossier_id: str) -> Path:
        return self.finalized_snapshot_dir(dossier_id) / "dossier_final.json"

    def latest_finalized_snapshot_path(self, dossier_id: str) -> Optional[Path]:
        d = self.finalized_snapshot_dir(dossier_id)
        if not d.exists():
            return None
        pointer = self.finalized_pointer_path(dossier_id)
        if pointer.exists():
            return pointer
        snaps = sorted(d.glob("dossier_final_*.json"), reverse=True)
        return snaps[0] if snaps else None

    def _finalized_index_path(self) -> Path:
        return dossiers_state_root() / "finalized_index.json"

    def iter_finalized_dossier_ids(self) -> Iterable[str]:
        """
        Enumerate dossier_ids with finalized snapshots.

        Prefer the finalized_index.json written by FinalizationService, falling
        back to scanning the views/transcriptions tree.
        """

        idx_path = self._finalized_index_path()
        if idx_path.exists():
            try:
                import json

                with idx_path.open("r", encoding="utf-8") as f:
                    data = json.load(f) or {}
                for entry in data.get("finalized", []) or []:
                    did = (entry or {}).get("dossier_id")
                    if isinstance(did, str) and did.strip():
                        yield did.strip()
                return
            except Exception:
                # Fall back to scan
                pass

        root = self.transcriptions_root()
        if not root.exists():
            return
        for child in root.iterdir():
            if child.is_dir() and (child / "final").exists():
                yield child.name

    # ----- Dossier ids (generic) -----

    def iter_dossier_ids(self) -> Iterable[str]:
        """
        Enumerate dossier_ids present in the workspace.

        Prefer management metadata files (dossier_*.json); fall back to
        transcriptions folders.
        """

        mgmt_root = dossiers_management_root()
        if mgmt_root.exists():
            for p in mgmt_root.glob("dossier_*.json"):
                name = p.stem
                # dossier_<id>
                if name.startswith("dossier_"):
                    did = name[len("dossier_") :]
                    if did:
                        yield did
            # If we found any via management, stop there
            return

        root = self.transcriptions_root()
        if not root.exists():
            return
        for child in root.iterdir():
            if child.is_dir():
                yield child.name

    # ----- Transcription runs (HEAD only) -----

    def transcript_raw_path(self, dossier_id: str, transcription_id: str) -> Path:
        """
        Canonical path for a raw transcription JSON file.
        """

        return (
            self.transcriptions_root()
            / str(dossier_id)
            / str(transcription_id)
            / "raw"
            / f"{transcription_id}.json"
        )

    def iter_transcription_heads(self, dossier_id: Optional[str] = None) -> Iterator[Tuple[str, str, Path]]:
        """
        Conservative enumeration of transcription "heads".

        For each (dossier_id, transcription_id) pair, yield a single raw JSON
        file path if it exists:
        - dossiers_data/views/transcriptions/<dossier_id>/<transcription_id>/raw/<transcription_id>.json
        """

        root = self.transcriptions_root()
        if not root.exists():
            return

        dossiers: List[Path]
        if dossier_id:
            dossiers = [root / str(dossier_id)]
        else:
            dossiers = [p for p in root.iterdir() if p.is_dir()]

        for ddir in dossiers:
            did = ddir.name
            for run_dir in ddir.iterdir():
                if not run_dir.is_dir():
                    continue
                tid = run_dir.name
                raw = run_dir / "raw" / f"{tid}.json"
                if raw.exists():
                    yield (did, tid, raw)

    # ----- Draft resolution (for segment-final hydration) -----

    def resolve_draft_path(
        self,
        dossier_id: str,
        draft_id: str,
        *,
        use_rglob_fallback: bool = False,
    ) -> Optional[Path]:
        """
        Resolve a draft_id to a filesystem path within a dossier.

        Handles various draft ID formats:
        - Simple transcription_id (e.g., "abc123")
        - Per-draft versioned IDs (e.g., "abc123_v3", "abc123_v3_v1")
        - Consensus drafts (e.g., "abc123_consensus_llm")
        - Alignment drafts (e.g., "abc123_draft_1")

        Args:
            dossier_id: The dossier containing the draft
            draft_id: The draft identifier to resolve
            use_rglob_fallback: If True, allows expensive rglob fallback search.
                Defaults to False for performance. Only enable when exhaustive
                search is acceptable (e.g., one-time migrations or debugging).

        Returns None if the draft cannot be resolved (caller should handle gracefully).
        """
        # Check cache first
        cache_key = (dossier_id, draft_id)
        if cache_key in self._draft_path_cache:
            return self._draft_path_cache[cache_key]

        result = self._resolve_draft_path_uncached(dossier_id, draft_id, use_rglob_fallback)
        self._draft_path_cache[cache_key] = result
        return result

    def _resolve_draft_path_uncached(
        self,
        dossier_id: str,
        draft_id: str,
        use_rglob_fallback: bool,
    ) -> Optional[Path]:
        """Internal uncached implementation of draft path resolution."""
        root = dossier_runs_root(str(dossier_id))

        # --- Consensus (LLM) ---
        if "_consensus_llm" in draft_id:
            # e.g., abc123_consensus_llm or abc123_consensus_llm_v1
            if draft_id.endswith("_consensus_llm_v1") or draft_id.endswith("_consensus_llm_v2"):
                base_id = draft_id.split("_consensus_llm_")[0]
                ver = "v1" if draft_id.endswith("_v1") else "v2"
                p = root / base_id / "consensus" / f"llm_{base_id}_{ver}.json"
                if p.exists():
                    return p
                return None  # Explicit version requested, no fallback
            else:
                base_id = draft_id.removesuffix("_consensus_llm")
                p = root / base_id / "consensus" / f"llm_{base_id}.json"
                if p.exists():
                    return p

        # --- Consensus (alignment) ---
        if "_consensus_alignment" in draft_id:
            if draft_id.endswith("_consensus_alignment_v1") or draft_id.endswith("_consensus_alignment_v2"):
                base_id = draft_id.split("_consensus_alignment_")[0]
                ver = "v1" if draft_id.endswith("_v1") else "v2"
                p = root / base_id / "consensus" / f"alignment_{base_id}_{ver}.json"
                if p.exists():
                    return p
                return None
            else:
                base_id = draft_id.removesuffix("_consensus_alignment")
                p = root / base_id / "consensus" / f"alignment_{base_id}.json"
                if p.exists():
                    return p

        # --- Alignment per-draft IDs (e.g., abc123_draft_1, abc123_draft_1_v1) ---
        if "_draft_" in draft_id:
            base_id, _, tail = draft_id.partition("_draft_")
            if tail.endswith("_v1") or tail.endswith("_v2"):
                ver = tail.split("_")[-1]
                n = tail.split("_")[0]
                p = root / base_id / "alignment" / f"draft_{n}_{ver}.json"
                if p.exists():
                    return p
            else:
                n = tail
                p = root / base_id / "alignment" / f"draft_{n}.json"
                if p.exists():
                    return p

        # --- Raw versioned files (e.g., abc123_v3, abc123_v3_v1) ---
        if "_v" in draft_id:
            # Folder is the transcription root (before first _v<number>)
            folder_tid = re.split(r"_v\d+", draft_id)[0] or draft_id
            # Per-draft base (e.g., abc123_v3) = up to first _v<number>
            m = re.match(r"(.+?_v\d+)", draft_id)
            base_draft = m.group(1) if m else draft_id

            ver = None
            if draft_id.endswith("_v1"):
                ver = "v1"
            elif draft_id.endswith("_v2"):
                ver = "v2"

            raw_dir = root / folder_tid / "raw"

            if ver:
                # Explicit version requested — try multiple naming conventions
                # 1) dot-suffix (e.g., base.v1.json)
                dot_path = raw_dir / f"{base_draft}.{ver}.json"
                if dot_path.exists():
                    return dot_path
                # 2) underscore full id (e.g., base_v1.json)
                underscore_full = raw_dir / f"{base_draft}_{ver}.json"
                if underscore_full.exists():
                    return underscore_full
                # 3) plain base for v1 (common saver output): base.json
                if ver == "v1":
                    plain_v1 = raw_dir / f"{base_draft}.json"
                    if plain_v1.exists():
                        return plain_v1
                # Explicit version requested but not found — no fallback
                return None

            # No explicit version — try HEAD variants
            raw_versioned = raw_dir / f"{draft_id}.json"
            if raw_versioned.exists():
                return raw_versioned

            head_path = raw_dir / f"{base_draft}.json"
            if head_path.exists():
                return head_path

            # Last resort: base aggregated file
            raw_base = raw_dir / f"{folder_tid}.json"
            if raw_base.exists():
                return raw_base

        # --- Non-versioned raw file ---
        raw_exact = root / draft_id / "raw" / f"{draft_id}.json"
        if raw_exact.exists():
            return raw_exact

        # --- Fallback: global rglob search (expensive, opt-in only) ---
        if use_rglob_fallback:
            transcriptions_root = self.transcriptions_root()
            candidates = list(transcriptions_root.rglob(f"**/raw/{draft_id}.json"))
            if candidates:
                return candidates[0]

        return None

    def clear_draft_path_cache(self) -> None:
        """Clear the in-process draft path cache."""
        self._draft_path_cache.clear()

