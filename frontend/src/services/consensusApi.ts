/**
 * Consensus Draft API Service
 * ===========================
 * 
 * Handles API calls for generating consensus drafts from alignment results.
 */

export interface ConsensusGenerationResponse {
  success: boolean;
  enhanced_alignment_results?: any;
  consensus_summary?: {
    total_blocks_processed: number;
    consensus_blocks_generated: number;
    average_confidence: number;
  };
  error?: string;
}

/**
 * Generate consensus drafts from alignment results
 */
export async function generateConsensusDrafts(alignmentResults: any): Promise<ConsensusGenerationResponse> {
  try {
    const response = await fetch('http://localhost:8000/api/consensus/generate-consensus', {  // ← FIX: Add full URL
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        alignment_results: alignmentResults
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Error generating consensus drafts:', error);
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error occurred'
    };
  }
}

/**
 * Check if alignment results contain consensus drafts
 */
export function hasConsensusDrafts(alignmentResult: any): boolean {
  if (!alignmentResult?.alignment_results?.blocks) {
    return false;
  }
  
  return Object.values(alignmentResult.alignment_results.blocks).some((block: any) => 
    block.aligned_sequences?.some((seq: any) => seq.draft_id === 'consensus')
  );
} 