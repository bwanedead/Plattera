"""
Consensus Draft API Endpoints
============================

Dedicated endpoints for consensus draft generation from alignment results.
Handles creating consensus drafts from Type 2 alignment table output.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
import logging

# Import the consensus generator
from alignment.consensus_draft_generator import ConsensusDraftGenerator

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


@router.get("/health")
async def consensus_health_check():
    """Simple health check for consensus service"""
    return {"status": "healthy", "service": "consensus_draft_generator"} 