import { AlignmentDraft, AlignmentResult } from '../types/imageProcessing';

// --- Alignment Engine API Service ---

export const alignDraftsAPI = async (drafts: AlignmentDraft[], consensusStrategy: string = 'highest_confidence'): Promise<AlignmentResult> => {
  try {
    console.log(`Aligning ${drafts.length} drafts with strategy: ${consensusStrategy}`);
    
    const response = await fetch('http://localhost:8000/api/alignment/align-drafts', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        drafts,
        generate_visualization: true,
        consensus_strategy: consensusStrategy
      })
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();
    console.log("Alignment API response:", data);

    return data;
  } catch (error) {
    console.error('Alignment API error:', error);
    return {
      success: false,
      processing_time: 0,
      summary: {
        total_positions_analyzed: 0,
        total_differences_found: 0,
        average_confidence_score: 0,
        quality_assessment: 'Failed',
        confidence_distribution: {
          high: 0,
          medium: 0,
          low: 0
        }
      },
      error: error instanceof Error ? error.message : 'Unknown alignment error'
    };
  }
}; 