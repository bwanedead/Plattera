"""
Dossier Management Service
=========================

Handles core CRUD operations for dossiers themselves.
Focused responsibility: dossier lifecycle management.
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime

from .models import Dossier, DossierSummary
from .purge_service import DossierPurgeService
from .event_bus import event_bus
from config.paths import (
    dossiers_management_root,
    dossiers_views_root,
    dossier_run_root,
)

logger = logging.getLogger(__name__)


class DossierManagementService:
    """
    Service for managing dossier lifecycle.
    Handles creation, retrieval, updates, and deletion of dossiers.

    Storage: JSON files in backend/dossiers/management/
    """

    def __init__(self):
        # New canonical storage under dossiers_data (centralized root)
        self.storage_dir = dossiers_management_root()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        logger.info("📁 Dossier Management Service initialized")

    def create_dossier(self, title: str, description: str = None) -> Dossier:
        """
        Create a new dossier.

        Args:
            title: Human-readable title for the dossier
            description: Optional description

        Returns:
            Dossier: The created dossier object
        """
        logger.info(f"📝 MANAGEMENT SERVICE: Creating new dossier: '{title}'")
        logger.info(f"📝 MANAGEMENT SERVICE: Description: '{description}'")
        logger.info(f"📝 MANAGEMENT SERVICE: Storage dir: {self.storage_dir}")
        logger.info(f"📝 MANAGEMENT SERVICE: Storage dir exists: {self.storage_dir.exists()}")

        dossier = Dossier(title=title, description=description)
        self._save_dossier(dossier)

        logger.info(f"✅ Created dossier: {dossier.id}")
        return dossier

    def get_dossier(self, dossier_id: str) -> Optional[Dossier]:
        """
        Retrieve a dossier by ID with populated segments/runs/drafts.

        Args:
            dossier_id: The dossier identifier

        Returns:
            Dossier object or None if not found
        """
        dossier_file = self.storage_dir / f"dossier_{dossier_id}.json"

        if not dossier_file.exists():
            logger.warning(f"📂 Dossier not found: {dossier_id}")
            return None

        try:
            with open(dossier_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            dossier = Dossier.from_dict(data)

            # Populate segments, runs, and drafts from associations
            self._populate_dossier_hierarchy(dossier)

            logger.info(f"📖 Retrieved dossier: {dossier_id} with {len(dossier.segments)} segments")
            return dossier
        except Exception as e:
            logger.error(f"❌ Error reading dossier {dossier_id}: {e}")
            return None

    def _populate_dossier_hierarchy(self, dossier: Dossier) -> None:
        """
        Populate the dossier's segments, runs, and drafts from transcription associations.
        Applies overrides to auto segments and preserves manual segments.

        Args:
            dossier: The dossier to populate
        """
        from .association_service import TranscriptionAssociationService
        from .models import Segment, Run, Draft

        association_service = TranscriptionAssociationService()
        transcriptions = association_service.get_dossier_transcriptions(dossier.id)
        # Removed noisy populate logs

        if not transcriptions:
            logger.debug(f"📄 No transcriptions found for dossier {dossier.id}")
            return

        # Start with manual segments already loaded in dossier.segments

        # Group transcriptions by segment (for now, each transcription = one segment)
        realized_runs = 0
        realized_drafts = 0
        for transcription in transcriptions:
            # Create stable segment ID based on transcription_id
            segment_id = f"segment_auto_{transcription.transcription_id}"
            segment = Segment(
                segment_id=segment_id,
                name=f"Segment {len(dossier.segments) + 1}",
                description=f"Auto-generated segment for transcription {transcription.transcription_id}",
                position=len(dossier.segments)
            )

            # Apply override if exists
            if segment_id in dossier.segment_name_overrides:
                segment.name = dossier.segment_name_overrides[segment_id]

            # Create run
            run_id = f"run_{transcription.transcription_id}"
            run = Run(
                run_id=run_id,
                transcription_id=transcription.transcription_id,
                position=0
            )

            # Try to load run metadata from run.json
            run_metadata = self.get_run_metadata(dossier.id, transcription.transcription_id)
            if run_metadata:
                run.status = run_metadata.get('status', 'processing')
                run.has_llm_consensus = run_metadata.get('has_llm_consensus', False)
                run.has_alignment_consensus = run_metadata.get('has_alignment_consensus', False)
                run.redundancy_count = run_metadata.get('redundancy_count', 1)
                run.completed_drafts = run_metadata.get('completed_drafts', [])
                run.processing_params = run_metadata.get('processing_params', {})
                run.started_at = run_metadata.get('timestamps', {}).get('started_at')
                run.finished_at = run_metadata.get('timestamps', {}).get('finished_at')
            else:
                # Fallback to legacy behavior
                run.status = 'completed'
                run.has_llm_consensus = False
                run.has_alignment_consensus = False
                run.redundancy_count = 1
                run.completed_drafts = []
                run.processing_params = {}

            # Attach images metadata from association (if available)
            try:
                assoc_meta = getattr(transcription, 'metadata', {}) or {}
                if isinstance(assoc_meta, dict):
                    images_meta = assoc_meta.get('images')
                    if images_meta:
                        run.metadata = (run.metadata or {})
                        run.metadata['images'] = images_meta
                    # Optionally pass through provenance summary for future use
                    if assoc_meta.get('provenance'):
                        run.metadata = (run.metadata or {})
                        run.metadata.setdefault('provenance', {})
                        run.metadata['provenance'] = assoc_meta['provenance']
            except Exception as _em:
                logger.debug(f"(non-critical) Could not merge association metadata into run: {_em}")

            # Build drafts list based on run metadata (placeholders first)
            run.drafts = []

            # Create placeholder drafts for redundancy
            redundancy_count = getattr(run, 'redundancy_count', 1)
            completed_drafts = getattr(run, 'completed_drafts', [])
            if isinstance(completed_drafts, str):
                completed_drafts = [completed_drafts]

            # Create placeholder drafts for all expected redundancy drafts
            for i in range(max(1, redundancy_count)):
                draft_id = f"{transcription.transcription_id}_v{i+1}"
                draft = Draft(
                    draft_id=draft_id,
                    transcription_id=transcription.transcription_id,
                    position=i,
                    is_best=False
                )

                # Mark as completed if in completed_drafts list
                is_completed = draft_id in completed_drafts
                draft.metadata = {
                    'sizeBytes': 0,
                    'quality': 'unknown',
                    'confidence': 0,
                    'status': 'completed' if is_completed else 'processing'
                }
                run.drafts.append(draft)

            # If redundancy not enabled yet, still show at least one placeholder
            if redundancy_count <= 0:
                redundancy_count = 1

            # Determine longest draft by reading persisted versioned drafts and set is_best accordingly
            try:
                from pathlib import Path as _Path

                # Use structured path: dossiers_data/views/transcriptions/{dossier_id}/{transcription_id}/{raw,alignment,consensus}
                run_root = dossier_run_root(str(dossier.id), str(transcription.transcription_id))
                _struct_raw = run_root / "raw"
                _struct_align = run_root / "alignment"
                _struct_cons = run_root / "consensus"
                _head_path = run_root / "head.json"
                head_map = {}
                try:
                    if _head_path.exists():
                        with open(_head_path, "r", encoding="utf-8") as hf:
                            head_map = json.load(hf) or {}
                except Exception:
                    head_map = {}

                longest_idx = None
                max_len = -1

                for i, d in enumerate(run.drafts):
                    fpath = _struct_raw / f"{transcription.transcription_id}_v{i+1}.json"
                    # Version flags for UI: raw v1 always implied, raw v2 only if .v2.json exists
                    raw_v2_path = _struct_raw / f"{transcription.transcription_id}_v{i+1}.v2.json"
                    align_v1_path = _struct_align / f"draft_{i+1}_v1.json"
                    align_v2_path = _struct_align / f"draft_{i+1}_v2.json"
                    # Heads
                    raw_heads = (head_map.get("raw_heads") or {}) if isinstance(head_map, dict) else {}
                    alignment_heads = (head_map.get("alignment_heads") or {}) if isinstance(head_map, dict) else {}
                    raw_head_val = raw_heads.get(f"{transcription.transcription_id}_v{i+1}") or "v1"
                    align_head_val = alignment_heads.get(f"{transcription.transcription_id}_draft_{i+1}")

                    # Final selection for stitching and UI
                    final_selected_id = (
                        (head_map.get("final") or {}).get("selected_id")
                        if isinstance(head_map, dict)
                        else None
                    )

                    length = 0
                    if fpath.exists():
                        with open(fpath, "r", encoding="utf-8") as fp:
                            content = json.load(fp)

                        # Determine if this is a real (non-placeholder) draft with usable content
                        is_real = False
                        text = ""
                        if isinstance(content, dict):
                            # If placeholder flag is explicitly set, do not treat as real
                            if content.get("_placeholder") is True:
                                is_real = False
                            # Respect explicit completion status if present
                            if content.get("_status") == "completed":
                                is_real = True
                            sections = content.get("sections")
                            if isinstance(sections, list):
                                text = " ".join(
                                    str(s.get("body", "")) for s in sections if isinstance(s, dict)
                                )
                                if any(
                                    (s.get("body") or "").strip()
                                    for s in sections
                                    if isinstance(s, dict)
                                ):
                                    is_real = True
                            elif "extracted_text" in content:
                                text = str(content.get("extracted_text", ""))
                                is_real = bool(text and text.strip())
                            elif "text" in content:
                                text = str(content.get("text", ""))
                                is_real = bool(text and text.strip())
                            # Support generic schema mainText
                            if not is_real and isinstance(content.get("mainText"), str):
                                mt = content.get("mainText") or ""
                                text = mt if len(mt) > len(text) else text
                                is_real = bool(mt.strip())

                        length = len((text or "").strip())

                        if is_real:
                            try:
                                d.metadata["status"] = "completed"
                            except Exception:
                                pass
                            realized_drafts += 1

                    if length > max_len:
                        max_len = length
                        longest_idx = i

                    # Attach version flags for UI consumption
                    try:
                        d.metadata = d.metadata or {}
                        versions = {
                            "raw": {
                                "v1": True,
                                # Consider head map indicating v2 to avoid transient misses
                                "v2": (raw_v2_path.exists() or (raw_head_val == "v2")),
                                "head": raw_head_val,
                            },
                            "alignment": {
                                "v1": align_v1_path.exists(),
                                "v2": align_v2_path.exists(),
                                "head": align_head_val,
                            },
                            "consensus": {
                                "llm": {
                                    "v1": (
                                        _struct_cons
                                        / f"llm_{transcription.transcription_id}_v1.json"
                                    ).exists(),
                                    "v2": (
                                        _struct_cons
                                        / f"llm_{transcription.transcription_id}_v2.json"
                                    ).exists(),
                                    "head": (
                                        (head_map.get("consensus") or {})
                                        .get("llm", {})
                                        .get("head")
                                        if isinstance(head_map, dict)
                                        else None
                                    ),
                                },
                                "alignment": {
                                    "v1": (
                                        _struct_cons
                                        / f"alignment_{transcription.transcription_id}_v1.json"
                                    ).exists(),
                                    "v2": (
                                        _struct_cons
                                        / f"alignment_{transcription.transcription_id}_v2.json"
                                    ).exists(),
                                    "head": (
                                        (head_map.get("consensus") or {})
                                        .get("alignment", {})
                                        .get("head")
                                        if isinstance(head_map, dict)
                                        else None
                                    ),
                                },
                            },
                        }
                        d.metadata["versions"] = versions
                    except Exception:
                        pass

                if longest_idx is not None:
                    for i, d in enumerate(run.drafts):
                        d.is_best = i == longest_idx

                # Expose final selection at run-level metadata for FE and stitching
                try:
                    from services.dossier.final_registry_service import FinalRegistryService

                    fr = FinalRegistryService()
                    # Prefer registry value if present
                    seg_id = getattr(segment, "id", None)
                    reg_val = (
                        fr.get_segment_final(str(dossier.id), str(seg_id))
                        if (getattr(dossier, "id", None) and seg_id)
                        else None
                    )
                    chosen_final = None
                    if isinstance(reg_val, dict):
                        chosen_final = reg_val.get("draft_id")
                    if not chosen_final:
                        # Read-only fallback to head.json legacy field computed above
                        chosen_final = final_selected_id
                    run.metadata = run.metadata or {}
                    run.metadata["final_selected_id"] = chosen_final
                except Exception:
                    pass
            except Exception as _e:
                logger.warning(
                    f"⚠️ Failed to determine best draft by length for {transcription.transcription_id}: {_e}"
                )

            # Append LLM consensus draft if enabled or present; show failure/processing states
            if getattr(run, 'has_llm_consensus', False) or run.processing_params.get('auto_llm_consensus'):
                try:
                    from pathlib import Path as _Path2
                    from config.paths import dossiers_views_root as _dossiers_views_root

                    _root = _dossiers_views_root()

                    structured_llm = _root / str(dossier.id) / str(transcription.transcription_id) / "consensus" / f"llm_{transcription.transcription_id}.json"
                    flat_llm = _root / f"{transcription.transcription_id}_consensus_llm.json"
                    _llm_path = structured_llm if structured_llm.exists() else (flat_llm if flat_llm.exists() else None)
                    if _llm_path:
                        consensus_draft = Draft(
                            draft_id=f"{transcription.transcription_id}_consensus_llm",
                            transcription_id=transcription.transcription_id,
                            position=len(run.drafts),
                            is_best=False
                        )
                        consensus_draft.metadata = {
                            'type': 'llm_consensus',
                            'label': 'AI Generated Consensus',
                            'status': 'completed'
                        }
                        # Attach consensus version flags for LLM consensus
                        try:
                            cons_v1 = (_struct_cons / f"llm_{transcription.transcription_id}_v1.json").exists()
                            cons_v2 = (_struct_cons / f"llm_{transcription.transcription_id}_v2.json").exists()
                            cons_head = (head_map.get('consensus') or {}).get('llm', {}).get('head') if isinstance(head_map, dict) else None
                            consensus_draft.metadata['versions'] = {
                                'consensus': {
                                    'llm': {
                                        'v1': cons_v1,
                                        'v2': cons_v2,
                                        'head': cons_head
                                    }
                                }
                            }
                        except Exception:
                            pass
                        run.drafts.append(consensus_draft)
                    else:
                        # Create placeholder if enabled but not yet completed
                        consensus_draft = Draft(
                            draft_id=f"{transcription.transcription_id}_consensus_llm",
                            transcription_id=transcription.transcription_id,
                            position=len(run.drafts),
                            is_best=False
                        )
                        consensus_draft.metadata = {
                            'type': 'llm_consensus',
                            'label': 'AI Generated Consensus',
                            'status': 'failed' if run_metadata.get('llm_consensus_status') == 'failed' else 'processing'
                        }
                        try:
                            cons_head = (head_map.get('consensus') or {}).get('llm', {}).get('head') if isinstance(head_map, dict) else None
                            consensus_draft.metadata['versions'] = {
                                'consensus': {
                                    'llm': {
                                        'v1': False,
                                        'v2': False,
                                        'head': cons_head
                                    }
                                }
                            }
                        except Exception:
                            pass
                        run.drafts.append(consensus_draft)
                except Exception as _e2:
                    logger.warning(f"⚠️ Failed to append LLM consensus draft for {transcription.transcription_id}: {_e2}")

            # Append alignment consensus draft if file exists OR run metadata indicates it's expected
            try:
                from pathlib import Path as _Path3
                from config.paths import dossiers_views_root as _dossiers_views_root

                _root = _dossiers_views_root()
                structured_align = _root / str(dossier.id) / str(transcription.transcription_id) / "consensus" / f"alignment_{transcription.transcription_id}.json"
                flat_align = _root / f"{transcription.transcription_id}_consensus_alignment.json"
                _align_path = structured_align if structured_align.exists() else (flat_align if flat_align.exists() else None)

                if _align_path:
                    alignment_consensus_draft = Draft(
                        draft_id=f"{transcription.transcription_id}_consensus_alignment",
                        transcription_id=transcription.transcription_id,
                        position=len(run.drafts),
                        is_best=False
                    )
                    alignment_consensus_draft.metadata = {
                        'type': 'alignment_consensus',
                        'label': 'Alignment Consensus',
                        'status': 'completed'
                    }
                    # Attach consensus version flags for alignment consensus
                    try:
                        cons_v1 = (_struct_cons / f"alignment_{transcription.transcription_id}_v1.json").exists()
                        cons_v2 = (_struct_cons / f"alignment_{transcription.transcription_id}_v2.json").exists()
                        cons_head = (head_map.get('consensus') or {}).get('alignment', {}).get('head') if isinstance(head_map, dict) else None
                        alignment_consensus_draft.metadata['versions'] = {
                            'consensus': {
                                'alignment': {
                                    'v1': cons_v1,
                                    'v2': cons_v2,
                                    'head': cons_head
                                }
                            }
                        }
                    except Exception:
                        pass
                    run.drafts.append(alignment_consensus_draft)
                elif getattr(run, 'has_alignment_consensus', False):
                    # Create placeholder if expected by run metadata but file not yet present
                    alignment_consensus_draft = Draft(
                        draft_id=f"{transcription.transcription_id}_consensus_alignment",
                        transcription_id=transcription.transcription_id,
                        position=len(run.drafts),
                        is_best=False
                    )
                    alignment_consensus_draft.metadata = {
                        'type': 'alignment_consensus',
                        'label': 'Alignment Consensus',
                        'status': 'processing'
                    }
                    try:
                        cons_head = (head_map.get('consensus') or {}).get('alignment', {}).get('head') if isinstance(head_map, dict) else None
                        alignment_consensus_draft.metadata['versions'] = {
                            'consensus': {
                                'alignment': {
                                    'v1': False,
                                    'v2': False,
                                    'head': cons_head
                                }
                            }
                        }
                    except Exception:
                        pass
                    run.drafts.append(alignment_consensus_draft)
            except Exception as _e3:
                logger.warning(f"⚠️ Failed to append alignment consensus draft for {transcription.transcription_id}: {_e3}")

            # Build hierarchy
            segment.runs.append(run)
            dossier.segments.append(segment)
            realized_runs += 1

        # Removed noisy populate logs

    # -----------------------------
    # Segment management operations
    # -----------------------------

    def add_segment(self, dossier_id: str, name: str) -> Optional[Dict[str, Any]]:
        """Create a new manual segment in a dossier and persist it."""
        dossier = self.get_dossier(dossier_id)
        if not dossier:
            logger.warning(f"⚠️ Cannot add segment; dossier not found: {dossier_id}")
            return None

        # Generate a stable manual segment id
        segment_index = len(dossier.manual_segments) + len(dossier.segment_name_overrides)
        segment_id = f"segment_manual_{segment_index}_{dossier_id[:8]}"

        from .models import Segment
        segment = Segment(segment_id=segment_id, name=name or f"Manual Segment {segment_index + 1}", position=segment_index)

        # Add to manual segments and persist
        dossier.manual_segments.append(segment.to_dict())
        dossier.segments.append(segment)  # Also add to runtime segments

        # Persist by saving dossier back to disk
        self._save_dossier(dossier)
        logger.info(f"✅ Added manual segment '{segment.name}' to dossier {dossier_id}")
        return segment.to_dict()

    def update_segment_by_id(self, segment_id: str, name: str) -> bool:
        """Update a segment's name by scanning dossiers for the segment id."""
        try:
            dossier_files = list(self.storage_dir.glob("dossier_*.json"))
            for file_path in dossier_files:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Check manual segments first
                manual_segments = data.get('manual_segments', [])
                updated = False
                for seg in manual_segments:
                    if seg.get('id') == segment_id:
                        seg['name'] = name
                        updated = True
                        break

                # If not in manual segments, check if it's an auto segment and use overrides
                if not updated and segment_id.startswith('segment_auto_'):
                    segment_name_overrides = data.get('segment_name_overrides', {})
                    segment_name_overrides[segment_id] = name
                    data['segment_name_overrides'] = segment_name_overrides
                    updated = True

                if updated:
                    # Save file and return
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    logger.info(f"✅ Updated segment {segment_id} name to '{name}' in {file_path.name}")
                    return True

            logger.warning(f"⚠️ Segment id not found for update: {segment_id}")
            return False
        except Exception as e:
            logger.error(f"❌ Failed to update segment {segment_id}: {e}")
            return False

    def delete_segment_by_id(self, segment_id: str) -> bool:
        """Delete a segment by scanning dossiers for the segment id."""
        try:
            dossier_files = list(self.storage_dir.glob("dossier_*.json"))
            for file_path in dossier_files:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Check manual segments first
                manual_segments = data.get('manual_segments', [])
                deleted = False

                # Remove from manual segments
                original_length = len(manual_segments)
                manual_segments = [seg for seg in manual_segments if seg.get('id') != segment_id]
                if len(manual_segments) < original_length:
                    data['manual_segments'] = manual_segments
                    deleted = True

                # If not in manual segments, check if it's an auto segment and remove from overrides
                if not deleted and segment_id.startswith('segment_auto_'):
                    segment_name_overrides = data.get('segment_name_overrides', {})
                    if segment_id in segment_name_overrides:
                        del segment_name_overrides[segment_id]
                        data['segment_name_overrides'] = segment_name_overrides
                        deleted = True

                if deleted:
                    # Save file and return
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    logger.info(f"✅ Deleted segment {segment_id} from {file_path.name}")
                    return True

            logger.warning(f"⚠️ Segment id not found for deletion: {segment_id}")
            return False
        except Exception as e:
            logger.error(f"❌ Failed to delete segment {segment_id}: {e}")
            return False

    def update_dossier(self, dossier_id: str, updates: Dict[str, Any]) -> Optional[Dossier]:
        """
        Update a dossier with new data.

        Args:
            dossier_id: The dossier to update
            updates: Dictionary of fields to update

        Returns:
            Dossier: Updated dossier object or None if not found
        """
        logger.info(f"🔄 Updating dossier: {dossier_id}")

        dossier = self.get_dossier(dossier_id)
        if not dossier:
            logger.warning(f"⚠️ Cannot update non-existent dossier: {dossier_id}")
            return None

        # Apply updates
        if 'title' in updates:
            dossier.title = updates['title']
            logger.info(f"🔄 Applied title update: '{dossier.title}'")
            # Propagate to artifacts and indices (best-effort)
            try:
                from .title_propagation_service import TitlePropagationService
                TitlePropagationService().propagate(str(dossier_id), str(dossier.title))
            except Exception as _pe:
                logger.warning(f"Title propagation failed for dossier {dossier_id}: {_pe}")
        if 'description' in updates:
            dossier.description = updates['description']
            logger.info(f"🔄 Applied description update: '{dossier.description}'")

        dossier.updated_at = datetime.now()  # Update timestamp explicitly
        logger.info(f"🔄 Updated timestamp to: {dossier.updated_at}")

        self._save_dossier(dossier)
        logger.info(f"✅ Updated dossier: {dossier_id}")
        return dossier

    def delete_dossier(self, dossier_id: str, purge: bool = True) -> bool:
        """
        Delete a dossier.

        By default, only deletes dossier metadata. When purge=True, also deletes
        associated data under views/transcriptions/<dossier_id>/ and the dossier's
        association file. Attempts to clean up legacy flat files for this dossier's
        transcriptions based on associations.

        Args:
            dossier_id: The dossier to delete

        Returns:
            bool: Success status
        """
        logger.info(f"🗑️ Deleting dossier: {dossier_id} (purge={purge})")

        dossier_file = self.storage_dir / f"dossier_{dossier_id}.json"

        if not dossier_file.exists():
            logger.warning(f"⚠️ Cannot delete non-existent dossier: {dossier_id}")
            return False

        try:
            # Verify dossier exists (metadata file present)
            if not dossier_file.exists():
                logger.warning(f"⚠️ Cannot delete non-existent dossier: {dossier_id}")
                return False

            # Delegate to centralized purge service
            purge_service = DossierPurgeService()
            summary = purge_service.purge_dossier(str(dossier_id), scrub_jobs=True)
            logger.info(f"✅ Purged dossier via service: {dossier_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Error deleting dossier {dossier_id}: {e}")
            return False

    def list_dossiers(self, limit: int = 50, offset: int = 0) -> List[Dossier]:
        """
        List all dossiers with populated hierarchy.

        Args:
            limit: Maximum number of dossiers to return
            offset: Number of dossiers to skip

        Returns:
            List of full Dossier objects with populated segments/runs/drafts
        """
        # Reduce noisy listing logs; keep at trace-level (debug)
        logger.debug("API:list_dossiers")
        # Quiet verbose path existence logs

        dossiers = []
        total_segments = 0
        total_runs = 0
        total_drafts = 0
        try:
            dossier_files = list(self.storage_dir.glob("dossier_*.json"))
            # Quiet file count logs (kept at debug already)

            for file_path in dossier_files:
                try:
                    # Suppress per-file read logs
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    dossier = Dossier.from_dict(data)

                    # Populate segments, runs, and drafts from associations
                    self._populate_dossier_hierarchy(dossier)

                    seg_count = len(dossier.segments)
                    run_count = sum(len(s.runs) for s in dossier.segments)
                    draft_count = sum(len(r.drafts) for s in dossier.segments for r in s.runs)
                    total_segments += seg_count
                    total_runs += run_count
                    total_drafts += draft_count
                    # Suppress per-dossier detail logs
                    dossiers.append(dossier)

                except Exception as e:
                    logger.warning(f"⚠️ Error reading dossier file {file_path}: {e}")
                    continue

            # Sort by updated_at desc and apply pagination
            dossiers.sort(key=lambda d: d.updated_at, reverse=True)
            dossiers = dossiers[offset:offset + limit]

            logger.debug(
                f"DOSS_LIST_SUMMARY files={len(dossier_files)} returned={len(dossiers)} "
                f"segments={total_segments} runs={total_runs} drafts={total_drafts}"
            )
            return dossiers

        except Exception as e:
            logger.error(f"❌ Error listing dossiers: {e}")
            return []

    def dossier_exists(self, dossier_id: str) -> bool:
        """
        Check if a dossier exists.

        Args:
            dossier_id: The dossier ID to check

        Returns:
            bool: True if dossier exists
        """
        dossier_file = self.storage_dir / f"dossier_{dossier_id}.json"
        return dossier_file.exists()

    def create_run_metadata(self, dossier_id: str, transcription_id: str,
                           redundancy_count: int, processing_params: Dict[str, Any]) -> bool:
        """
        Create initial run.json metadata for a processing run.

        If the metadata already exists, this is a no-op to preserve progressive updates.

        Args:
            dossier_id: The dossier ID
            transcription_id: The transcription/run ID
            redundancy_count: Number of redundant drafts to generate
            processing_params: Processing parameters

        Returns:
            bool: Success status
        """
        try:
            # Create run directory structure
            run_dir = self._get_run_dir(dossier_id, transcription_id)
            run_dir.mkdir(parents=True, exist_ok=True)

            run_file = run_dir / "run.json"
            if run_file.exists():
                logger.info(f"📋 Run metadata already exists, preserving progressive state: {run_file}")
                return True

            run_metadata = {
                "status": "processing",
                "redundancy_count": redundancy_count,
                "completed_drafts": [],
                "has_llm_consensus": False,
                "has_alignment_consensus": False,
                "timestamps": {
                    "started_at": datetime.now().isoformat(),
                    "last_update_at": datetime.now().isoformat(),
                    "finished_at": None
                },
                "processing_params": processing_params
            }

            with open(run_file, 'w', encoding='utf-8') as f:
                json.dump(run_metadata, f, indent=2, ensure_ascii=False)

            logger.info(f"📋 Created run metadata: {run_file}")
            # Notify listeners
            try:
                import asyncio
                asyncio.create_task(event_bus.publish({
                    "type": "dossier:update",
                    "dossier_id": str(dossier_id),
                    "transcription_id": str(transcription_id),
                    "event": "run_created"
                }))
            except Exception:
                pass
            return True
        except Exception as e:
            logger.error(f"❌ Failed to create run metadata: {e}")
            return False

    def update_run_metadata(self, dossier_id: str, transcription_id: str,
                           updates: Dict[str, Any]) -> bool:
        """
        Update run.json metadata for a processing run.

        Args:
            dossier_id: The dossier ID
            transcription_id: The transcription/run ID
            updates: Fields to update

        Returns:
            bool: Success status
        """
        try:
            run_file = self._get_run_dir(dossier_id, transcription_id) / "run.json"
            if not run_file.exists():
                logger.warning(f"⚠️ Run metadata not found: {run_file}")
                return False

            with open(run_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

            # --- Observability: capture pre-state ---
            prev_status = metadata.get("status")
            prev_completed = metadata.get("completed_drafts", [])
            if isinstance(prev_completed, str):
                prev_completed = [prev_completed]
            prev_completed_set = set(prev_completed)

            # Update fields
            for key, value in updates.items():
                if key == "status" or key.startswith("has_"):
                    metadata[key] = value
                elif key == "completed_drafts":
                    if isinstance(value, list):
                        metadata["completed_drafts"] = value
                    else:
                        if value not in metadata["completed_drafts"]:
                            metadata["completed_drafts"].append(value)
                elif key == "timestamps":
                    if isinstance(metadata.get("timestamps"), dict):
                        metadata["timestamps"].update(value)
                    else:
                        metadata["timestamps"] = value

            # Always update last_update_at
            metadata["timestamps"]["last_update_at"] = datetime.now().isoformat()

            with open(run_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

            # --- Observability: capture post-state and log concise delta ---
            new_status = metadata.get("status")
            new_completed = metadata.get("completed_drafts", [])
            if isinstance(new_completed, str):
                new_completed = [new_completed]
            new_completed_set = set(new_completed)

            added = list(sorted(new_completed_set - prev_completed_set))
            removed = list(sorted(prev_completed_set - new_completed_set))

            try:
                total = int(metadata.get("redundancy_count") or 0)
                logger.info(
                    f"RUN_STATUS_UPDATE dossier={dossier_id} transcription={transcription_id} "
                    f"status:{prev_status}->{new_status} completed:{len(new_completed_set)}/{total} "
                    f"added={added} removed={removed}"
                )
            except Exception:
                logger.info(
                    f"RUN_STATUS_UPDATE dossier={dossier_id} transcription={transcription_id} "
                    f"status:{prev_status}->{new_status} completed_ids={sorted(new_completed_set)}"
                )

            logger.debug(f"📝 Updated run metadata: {run_file}")
            # Notify listeners
            try:
                import asyncio
                asyncio.create_task(event_bus.publish({
                    "type": "dossier:update",
                    "dossier_id": str(dossier_id),
                    "transcription_id": str(transcription_id),
                    "event": "run_updated"
                }))
            except Exception:
                pass
            return True
        except Exception as e:
            logger.error(f"❌ Failed to update run metadata: {e}")
            return False

    def get_run_metadata(self, dossier_id: str, transcription_id: str) -> Optional[Dict[str, Any]]:
        """
        Get run metadata for a processing run.

        Args:
            dossier_id: The dossier ID
            transcription_id: The transcription/run ID

        Returns:
            Dict with run metadata or None if not found
        """
        try:
            run_file = self._get_run_dir(dossier_id, transcription_id) / "run.json"
            if not run_file.exists():
                return None

            with open(run_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"❌ Failed to read run metadata: {e}")
            return None

    def _get_run_dir(self, dossier_id: str, transcription_id: str) -> Path:
        """Get the run directory path"""
        return dossier_run_root(str(dossier_id), str(transcription_id))

    def _save_dossier(self, dossier: Dossier) -> None:
        """Internal method to save dossier to disk"""
        dossier_file = self.storage_dir / f"dossier_{dossier.id}.json"

        logger.info(f"💾 MANAGEMENT SERVICE: Saving dossier to file: {dossier_file}")
        logger.info(f"💾 MANAGEMENT SERVICE: File exists before save: {dossier_file.exists()}")
        logger.info(f"💾 MANAGEMENT SERVICE: Dossier data: {dossier.to_dict()}")

        try:
            with open(dossier_file, 'w', encoding='utf-8') as f:
                json.dump(dossier.to_dict(), f, indent=2, ensure_ascii=False)
            logger.info(f"💾 MANAGEMENT SERVICE: Successfully saved dossier file: {dossier_file}")
            logger.info(f"💾 MANAGEMENT SERVICE: File exists after save: {dossier_file.exists()}")
            logger.info(f"💾 MANAGEMENT SERVICE: File size: {dossier_file.stat().st_size} bytes")
        except Exception as e:
            logger.error(f"❌ Error saving dossier {dossier.id}: {e}")
            logger.error(f"❌ Error details: {type(e).__name__}: {str(e)}")
            raise
