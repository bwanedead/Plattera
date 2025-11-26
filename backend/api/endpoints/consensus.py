"""
Consensus Draft API Endpoints
============================

Dedicated endpoints for consensus draft generation from alignment results.
Handles creating consensus drafts from Type 2 alignment table output.
"""

from fastapi import APIRouter, HTTPException, Form
from pydantic import BaseModel
from typing import Dict, Any, Optional
import logging
import json
from datetime import datetime
from pathlib import Path

# Import the consensus generator
from alignment.consensus_draft_generator import ConsensusDraftGenerator
from config.paths import dossiers_views_root

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic Models
class ConsensusRequest(BaseModel):
    """Request model for consensus draft generation"""
    alignment_results: Dict[str, Any]


class ConsensusResponse(BaseModel):
    """Response model for consensus draft generation"""
    success: bool
    enhanced_alignment_results: Optional[Dict[str, Any]] = None
    consensus_summary: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@router.post("/generate-consensus", response_model=ConsensusResponse)
async def generate_consensus_drafts(request: ConsensusRequest):
    """
    Generate consensus drafts from Type 2 alignment results.
    
    Takes existing alignment results and creates consensus drafts
    by selecting the most common token at each position from the
    Type 2 display tokens.
    
    Returns the original alignment results enhanced with consensus sequences.
    """
    logger.info("🎯 CONSENSUS API ► Generating consensus drafts")
    
    try:
        # Initialize consensus generator
        consensus_generator = ConsensusDraftGenerator()
        
        # Generate consensus sequences
        consensus_sequences = consensus_generator.generate_consensus_draft(
            request.alignment_results
        )
        
        # Add consensus sequences to the original alignment results
        enhanced_results = request.alignment_results.copy()
        
        # Add consensus to each block
        for block_id, consensus_sequence in consensus_sequences.items():
            if block_id in enhanced_results.get('blocks', {}):
                block = enhanced_results['blocks'][block_id]
                
                # Add consensus sequence to aligned_sequences
                if 'aligned_sequences' not in block:
                    block['aligned_sequences'] = []
                
                block['aligned_sequences'].append(consensus_sequence)
                
                # Update block metadata
                block['draft_count'] = len(block['aligned_sequences'])
                block['has_consensus'] = True
                
                logger.info(f"   ✅ Added consensus to block {block_id}")
        
        # Update summary
        if 'summary' not in enhanced_results:
            enhanced_results['summary'] = {}
        
        enhanced_results['summary']['consensus_blocks_generated'] = len(consensus_sequences)
        enhanced_results['summary']['consensus_generation_method'] = 'type2_most_common'
        
        # Create consensus summary
        consensus_summary = {
            'total_blocks_processed': len(enhanced_results.get('blocks', {})),
            'consensus_blocks_generated': len(consensus_sequences),
            'generation_method': 'type2_most_common',
            'requires_minimum_drafts': 2
        }
        
        logger.info(f"✅ CONSENSUS API ► Generated consensus for {len(consensus_sequences)} blocks")
        
        return ConsensusResponse(
            success=True,
            enhanced_alignment_results=enhanced_results,
            consensus_summary=consensus_summary
        )
        
    except Exception as e:
        logger.error(f"❌ CONSENSUS API ► Error: {e}")
        return ConsensusResponse(
            success=False,
            error=str(e)
        )


@router.post("/save-consensus-draft")
async def save_consensus_draft(
    transcription_id: str = Form(...),
    consensus_id: str = Form(...),
    consensus_data: str = Form(...)  # JSON string
):
    """
    Save an alignment consensus draft to the dossier structure.
    This creates a new draft file that will be discoverable in the dossier manager.
    """
    try:
        logger.info(f"💾 Saving alignment consensus draft: {consensus_id}")

        # Parse the consensus data
        try:
            consensus_info = json.loads(consensus_data)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Invalid consensus data JSON: {e}")

        # Find the transcription directory
        transcriptions_dir = dossiers_views_root()

        # Find the transcription directory that contains our transcription_id
        transcription_dir = None
        for subdir in transcriptions_dir.iterdir():
            if subdir.is_dir():
                for file in subdir.iterdir():
                    if file.name.startswith(transcription_id) and file.suffix == '.json':
                        transcription_dir = subdir
                        break
                if transcription_dir:
                    break

        if not transcription_dir:
            raise HTTPException(status_code=404, detail=f"Transcription directory for {transcription_id} not found")

        # Save the consensus draft JSON file
        consensus_file = transcription_dir / f"{consensus_id}.json"
        with open(consensus_file, 'w', encoding='utf-8') as cf:
            json.dump({
                "type": consensus_info.get("type", "alignment_consensus"),
                "model": consensus_info.get("model", "biopython_alignment"),
                "strategy": consensus_info.get("strategy", "highest_confidence"),
                "title": f"Alignment Consensus ({consensus_info.get('source_drafts', 0)} drafts)",
                "text": consensus_info.get("text", ""),
                "source_drafts": consensus_info.get("source_drafts", 0),
                "tokens_used": consensus_info.get("tokens_used", 0),
                "created_at": consensus_info.get("created_at", datetime.now().isoformat()),
                "metadata": consensus_info.get("metadata", {})
            }, cf, indent=2, ensure_ascii=False)

        logger.info(f"💾 Persisted alignment consensus JSON: {consensus_file}")

        return {
            "status": "success",
            "consensus_id": consensus_id,
            "file_path": str(consensus_file),
            "message": "Alignment consensus draft saved successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to save alignment consensus draft: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save consensus draft: {str(e)}")


@router.get("/health")
async def consensus_health_check():
    """Simple health check for consensus service"""
    return {"status": "healthy", "service": "consensus_draft_generator"} 