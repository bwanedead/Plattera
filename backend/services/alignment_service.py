"""
Alignment Service
================

Service layer for coordinating alignment workflow.
Handles preprocessing, alignment, and post-processing.
"""

import logging
from typing import Dict, List, Any, Optional
import time
import gc

# ABSOLUTE IMPORTS ONLY - never relative imports
from alignment.section_normalizer import SectionNormalizer
from alignment.biopython_engine import BioPythonAlignmentEngine
from alignment.alignment_utils import check_dependencies
from services.dossier.event_bus import event_bus
from config.paths import dossiers_views_root

logger = logging.getLogger(__name__)


class AlignmentService:
    """
    Service class for coordinating the complete alignment workflow.
    
    Orchestrates:
    1. Section normalization (preprocessing)
    2. BioPython alignment (core processing) 
    3. Results compilation (post-processing)
    """
    
    def __init__(self):
        self.section_normalizer = SectionNormalizer()
        self.alignment_engine = BioPythonAlignmentEngine()
        logger.info("🔧 Alignment Service initialized")
    
    def force_cleanup(self) -> Dict[str, Any]:
        """
        Best-effort cleanup of alignment-related resources.
        
        This is intentionally lightweight so it is safe in both dev and frozen
        (PyInstaller) modes and does not introduce new dependencies. It is
        primarily used by the /api/cleanup endpoint to free memory and allow
        the process to exit cleanly when running as a sidecar.
        """
        try:
            # Clear any engine-level caches if an explicit hook is available.
            if hasattr(self.alignment_engine, "cleanup"):
                try:
                    self.alignment_engine.cleanup()
                except Exception as e:
                    logger.debug(f"Alignment engine cleanup hook failed (non-critical): {e}")

            # Force a garbage collection pass to encourage memory release.
            gc.collect()

            return {
                "status": "success",
                "actions_performed": ["gc_collect", "engine_cleanup"],
                "memory_before_mb": 0,  # intentionally omitted to avoid psutil
                "memory_after_mb": 0,
                "errors": [],
            }
        except Exception as e:
            logger.error(f"Force cleanup failed: {e}")
            return {
                "status": "error",
                "errors": [str(e)],
                "memory_before_mb": 0,
                "memory_after_mb": 0,
            }
    
    def process_alignment_request(self, draft_jsons: List[Dict[str, Any]], 
                                generate_visualization: bool = True,
                                consensus_strategy: str = "highest_confidence",
                                save_context: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Process complete alignment workflow with section normalization.
        
        Args:
            draft_jsons: List of draft dictionaries
            generate_visualization: Whether to generate HTML visualization
            consensus_strategy: Strategy for consensus generation
            
        Returns:
            Complete alignment results with all processing steps
        """
        start_time = time.time()
        logger.info(f"🚀 ALIGNMENT SERVICE ► Starting workflow for {len(draft_jsons)} drafts")
        
        # Guard: alignment requires at least two drafts
        if len(draft_jsons) < 2:
            return {
                'success': False,
                'error': 'At least 2 drafts are required for alignment',
                'processing_time': time.time() - start_time
            }
        
        try:
            # Check dependencies first
            dependencies_available, missing_packages = check_dependencies()
            if not dependencies_available:
                return {
                    'success': False,
                    'error': f"Missing required dependencies: {', '.join(missing_packages)}",
                    'processing_time': time.time() - start_time
                }
            
            # STEP 1: Section Normalization (Preprocessing)
            logger.info("🔧 STEP 1 ► Section normalization preprocessing")
            normalized_draft_jsons = self.section_normalizer.normalize_draft_sections(draft_jsons)
            logger.info(f"✅ SECTION NORMALIZATION ► Processed {len(normalized_draft_jsons)} drafts")
            
            # Persist alignment v1 per-draft if dossier context given
            try:
                if save_context and isinstance(save_context.get('transcription_id'), str):
                    from services.dossier.edit_persistence_service import EditPersistenceService as _EPS
                    _svc = _EPS()
                    dossier_id = (save_context or {}).get('dossier_id') or ''
                    transcription_id = (save_context or {}).get('transcription_id') or ''
                    for i, nd in enumerate(normalized_draft_jsons):
                        # Expect nd to be { blocks: [{id, text}, ...] } or already sectioned
                        sections = []
                        try:
                            # Prefer existing sections if present
                            if isinstance(nd, dict) and isinstance(nd.get('sections'), list):
                                sections = nd.get('sections')
                            else:
                                blocks = nd.get('blocks') if isinstance(nd, dict) else None
                                if isinstance(blocks, list) and len(blocks) > 0:
                                    # Convert each block.text into a section
                                    sections = [{ 'id': idx + 1, 'body': str(b.get('text', '')) } for idx, b in enumerate(blocks) if isinstance(b, dict)]
                                else:
                                    # Fallback: single section with joined text
                                    text = ''
                                    try:
                                        text = ' '.join([str(b.get('text','')) for b in (blocks or []) if isinstance(b, dict)])
                                    except Exception:
                                        text = ''
                                    if not text and isinstance(nd, dict) and isinstance(nd.get('text'), str):
                                        text = nd.get('text')
                                    sections = [{ 'id': 1, 'body': text }]
                        except Exception:
                            sections = [{ 'id': 1, 'body': '' }]
                        _svc.save_alignment_v1(str(dossier_id), str(transcription_id), i, sections)
            except Exception as _persist_av1_err:
                logger.warning(f"⚠️ Failed to persist alignment v1 drafts (non-critical): {_persist_av1_err}")

            # STEP 2: BioPython Alignment (Core Processing)
            logger.info("🧬 STEP 2 ► BioPython alignment processing")
            alignment_results = self.alignment_engine.align_drafts(
                normalized_draft_jsons, 
                generate_visualization=generate_visualization
            )
            
            if not alignment_results.get('success', False):
                logger.error(f"❌ Alignment processing failed: {alignment_results.get('error')}")
                return alignment_results
            
            # STEP 3: Consensus Generation (Optional Post-processing)
            consensus_text = None
            if consensus_strategy and consensus_strategy != "none":
                logger.info(f"📝 STEP 3 ► Consensus generation using '{consensus_strategy}'")
                try:
                    consensus_text = self.alignment_engine.generate_consensus_text(
                        alignment_results['alignment_results'],
                        alignment_results['confidence_results'], 
                        consensus_strategy
                    )
                    logger.info("✅ Consensus generation completed")
                except Exception as e:
                    logger.warning(f"⚠️ Consensus generation failed: {e}")
                    # Continue without consensus - it's optional
            
            # Persist alignment consensus if requested
            try:
                consensus_text_for_save = consensus_text
                if save_context and consensus_text_for_save:
                    from datetime import datetime as _dt
                    import json as _json

                    base_root = dossiers_views_root()

                    dossier_id = (save_context or {}).get("dossier_id")
                    transcription_id = (save_context or {}).get("transcription_id")
                    consensus_id = (save_context or {}).get("consensus_draft_id") or (
                        f"{transcription_id}_consensus_alignment" if transcription_id else None
                    )

                    if transcription_id and consensus_id:
                        # Structured preferred path
                        if dossier_id:
                            run_dir = base_root / str(dossier_id) / str(transcription_id)
                        else:
                            run_dir = base_root / "_unassigned" / str(transcription_id)

                        consensus_dir = run_dir / "consensus"
                        consensus_dir.mkdir(parents=True, exist_ok=True)
                        # Save with per-transcription filename to match view/management lookups
                        consensus_file = consensus_dir / f"alignment_{transcription_id}.json"

                        payload = {
                            "type": "alignment_consensus",
                            "model": "biopython_alignment",
                            "strategy": consensus_strategy,
                            "title": "Alignment Consensus",
                            "text": consensus_text_for_save,
                            "source_drafts": len(draft_jsons),
                            "tokens_used": 0,
                            "created_at": _dt.now().isoformat(),
                            "metadata": {
                                "alignment_summary": alignment_results.get("summary", {}),
                                "processing_time": alignment_results.get("processing_time", 0),
                            },
                        }
                        try:
                            with open(consensus_file, "w", encoding="utf-8") as cf:
                                _json.dump(payload, cf, indent=2, ensure_ascii=False)
                            logger.info(f"💾 Persisted alignment consensus JSON: {consensus_file}")

                            # Update run metadata with alignment consensus and emit refresh event
                            try:
                                from services.dossier.management_service import (
                                    DossierManagementService as _DMS,
                                )

                                _ms = _DMS()
                                _ms.update_run_metadata(
                                    dossier_id=str(dossier_id),
                                    transcription_id=str(transcription_id),
                                    updates={
                                        "has_alignment_consensus": True,
                                        "status": "completed",
                                        "timestamps": {"finished_at": _dt.now().isoformat()},
                                    },
                                )
                                logger.info("📝 Updated run metadata for alignment consensus")
                                # Emit event for UI auto-refresh (non-blocking)
                                try:
                                    import asyncio

                                    asyncio.create_task(
                                        event_bus.publish(
                                            {
                                                "type": "dossier:update",
                                                "dossier_id": str(dossier_id),
                                                "transcription_id": str(transcription_id),
                                                "event": "alignment_consensus_saved",
                                            }
                                        )
                                    )
                                except Exception:
                                    pass
                            except Exception as meta_err:
                                logger.warning(
                                    f"⚠️ Failed to update run metadata for alignment consensus: {meta_err}"
                                )
                        except Exception as se:
                            logger.warning(f"⚠️ Failed to persist alignment consensus JSON: {se}")
            except Exception as persist_err:
                logger.warning(f"⚠️ Consensus persistence step failed (non-critical): {persist_err}")

            # STEP 4: Compile Final Results
            total_processing_time = time.time() - start_time
            
            final_results = {
                **alignment_results,  # Include all alignment results
                'consensus_text': consensus_text,
                'total_processing_time': total_processing_time,
                'workflow_steps': {
                    'section_normalization': 'completed',
                    'biopython_alignment': 'completed', 
                    'consensus_generation': 'completed' if consensus_text else 'skipped'
                }
            }
            
            # Simple cleanup
            gc.collect()
            
            logger.info(f"✅ ALIGNMENT SERVICE COMPLETE ► Total time: {total_processing_time:.2f}s")
            return final_results
            
        except Exception as e:
            logger.error(f"❌ ALIGNMENT SERVICE ERROR: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            
            return {
                'success': False,
                'error': f"Service processing error: {str(e)}",
                'processing_time': time.time() - start_time
            } 