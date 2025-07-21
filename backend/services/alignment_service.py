"""
Alignment Service
================

Service layer for coordinating alignment workflow.
Handles preprocessing, alignment, and post-processing.
"""

import logging
from typing import Dict, List, Any, Optional
import time

# ABSOLUTE IMPORTS ONLY - never relative imports
from alignment.section_normalizer import SectionNormalizer
from alignment.biopython_engine import BioPythonAlignmentEngine
from alignment.alignment_utils import check_dependencies

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
    
    def process_alignment_request(self, draft_jsons: List[Dict[str, Any]], 
                                generate_visualization: bool = True,
                                consensus_strategy: str = "highest_confidence") -> Dict[str, Any]:
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
                    logger.info(f"✅ CONSENSUS COMPLETE ► Generated {len(consensus_text)} character text")
                except Exception as e:
                    logger.warning(f"⚠️ Consensus generation failed: {e}")
                    # Continue without consensus - it's optional
            
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
    
    def check_service_status(self) -> Dict[str, Any]:
        """Check the health and status of the alignment service"""
        try:
            dependencies_available, missing_packages = check_dependencies()
            engine_info = self.alignment_engine.get_engine_info()
            
            return {
                'service_status': 'healthy',
                'dependencies_available': dependencies_available,
                'missing_dependencies': missing_packages,
                'section_normalizer_available': True,
                'biopython_engine_info': engine_info
            }
            
        except Exception as e:
            return {
                'service_status': 'error',
                'error': str(e)
            } 