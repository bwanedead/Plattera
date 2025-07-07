import { isJsonResult, formatJsonAsText } from './jsonFormatter';

export interface TextSelectionParams {
  selectedResult: any;
  selectedDraft: number | 'consensus' | 'best';
  selectedConsensusStrategy: string;
  alignmentResult?: any; // Add alignment result parameter
}

/**
 * Extract formatted text from alignment results
 */
const extractFormattedTextFromAlignment = (alignmentResult: any, selectedDraft: number | 'consensus' | 'best'): string | null => {
  if (!alignmentResult?.success || !alignmentResult.alignment_results?.blocks) {
    return null;
  }

  const blocks = alignmentResult.alignment_results.blocks;
  const blockTexts: string[] = [];

  // Process each block
  for (const [blockId, blockData] of Object.entries(blocks)) {
    const alignedSequences = (blockData as any)?.aligned_sequences || [];
    
    if (alignedSequences.length === 0) continue;

    let selectedSequence = null;

    // Find the sequence for the selected draft
    if (typeof selectedDraft === 'number') {
      // Find sequence by draft index
      selectedSequence = alignedSequences.find((seq: any) => {
        return seq.draft_id === `Draft_${selectedDraft + 1}` || 
               seq.draft_id === `draft_${selectedDraft + 1}` ||
               seq.draft_id === `Draft ${selectedDraft + 1}`;
      });
      
      // Fallback to array index if draft_id doesn't match
      if (!selectedSequence && selectedDraft < alignedSequences.length) {
        selectedSequence = alignedSequences[selectedDraft];
      }
    } else if (selectedDraft === 'consensus' || selectedDraft === 'best') {
      // For consensus/best, use the first sequence as default
      selectedSequence = alignedSequences[0];
    }

    if (selectedSequence && selectedSequence.tokens) {
      // Extract non-gap tokens and join them
      const tokens = selectedSequence.tokens.filter((token: string) => token && token !== '-');
      const blockText = tokens.join(' ');
      blockTexts.push(blockText);
    }
  }

  return blockTexts.join('\n\n');
};

export const getCurrentText = ({ selectedResult, selectedDraft, selectedConsensusStrategy, alignmentResult }: TextSelectionParams): string => {
  if (!selectedResult || selectedResult.status !== 'completed' || !selectedResult.result) {
    return selectedResult?.error || 'No result available';
  }

  const { result, error } = selectedResult;
  if (error) return error;
  if (!result) return 'No result available';

  // PRIORITY 1: Use formatted text from alignment results if available
  if (alignmentResult?.success) {
    const formattedText = extractFormattedTextFromAlignment(alignmentResult, selectedDraft);
    if (formattedText) {
      console.log('🎨 Using formatted text from alignment results');
      return isJsonResult(formattedText) ? formatJsonAsText(formattedText) : formattedText;
    }
  }

  // PRIORITY 2: Fall back to original redundancy analysis logic
  const redundancyAnalysis = result.metadata?.redundancy_analysis;
  
  // Use selected consensus strategy if available
  if (redundancyAnalysis?.all_consensus_results?.[selectedConsensusStrategy]) {
    const consensusText = redundancyAnalysis.all_consensus_results[selectedConsensusStrategy].consensus_text;
    // Format JSON as readable text if it's JSON
    return isJsonResult(consensusText) ? formatJsonAsText(consensusText) : consensusText;
  }
  
  // Fallback to original logic
  if (!redundancyAnalysis) {
    const extractedText = result.extracted_text || 'No text available';
    // Format JSON as readable text if it's JSON
    return isJsonResult(extractedText) ? formatJsonAsText(extractedText) : extractedText;
  }

  // UPDATED DRAFT SELECTION LOGIC
  if (selectedDraft === 'consensus') {
    const consensusText = redundancyAnalysis.consensus_text || result.extracted_text || '';
    // Format JSON as readable text if it's JSON
    return isJsonResult(consensusText) ? formatJsonAsText(consensusText) : consensusText;
  } else if (selectedDraft === 'best') {
    // "Best" now maps to the specific best draft index, not the main extracted text
    const bestIndex = redundancyAnalysis.best_result_index || 0;
    const individualResults = (redundancyAnalysis.individual_results || []).filter((r: any) => r.success);
    if (bestIndex < individualResults.length) {
      const bestDraftText = individualResults[bestIndex].text || '';
      return isJsonResult(bestDraftText) ? formatJsonAsText(bestDraftText) : bestDraftText;
    }
    // Fallback to main text if best index is invalid
    const extractedText = result.extracted_text || '';
    return isJsonResult(extractedText) ? formatJsonAsText(extractedText) : extractedText;
  } else if (typeof selectedDraft === 'number') {
    const individualResults = (redundancyAnalysis.individual_results || []).filter((r: any) => r.success);
    if (selectedDraft < individualResults.length) {
      const draftText = individualResults[selectedDraft].text || '';
      // Format JSON as readable text if it's JSON
      return isJsonResult(draftText) ? formatJsonAsText(draftText) : draftText;
    }
  }

  // Fallback to main text
  const fallbackText = result.extracted_text || '';
  return isJsonResult(fallbackText) ? formatJsonAsText(fallbackText) : fallbackText;
};

export const getRawText = ({ selectedResult, selectedDraft, selectedConsensusStrategy, alignmentResult }: TextSelectionParams): string => {
  if (!selectedResult || selectedResult.status !== 'completed' || !selectedResult.result) {
    return selectedResult?.error || 'No result available';
  }

  const { result, error } = selectedResult;
  if (error) return error;
  if (!result) return 'No result available';

  // PRIORITY 1: Use formatted text from alignment results if available
  if (alignmentResult?.success) {
    const formattedText = extractFormattedTextFromAlignment(alignmentResult, selectedDraft);
    if (formattedText) {
      console.log('🎨 Using formatted text from alignment results');
      return isJsonResult(formattedText) ? formatJsonAsText(formattedText) : formattedText;
    }
  }

  // PRIORITY 2: Fall back to original redundancy analysis logic
  const redundancyAnalysis = result.metadata?.redundancy_analysis;
  
  // Use selected consensus strategy if available
  if (redundancyAnalysis?.all_consensus_results?.[selectedConsensusStrategy]) {
    return redundancyAnalysis.all_consensus_results[selectedConsensusStrategy].consensus_text;
  }
  
  // Fallback to original logic
  if (!redundancyAnalysis) {
    return result.extracted_text || 'No text available';
  }

  // UPDATED DRAFT SELECTION LOGIC FOR RAW TEXT
  if (selectedDraft === 'consensus') {
    return redundancyAnalysis.consensus_text || result.extracted_text || '';
  } else if (selectedDraft === 'best') {
    // "Best" now maps to the specific best draft index, not the main extracted text
    const bestIndex = redundancyAnalysis.best_result_index || 0;
    const individualResults = (redundancyAnalysis.individual_results || []).filter((r: any) => r.success);
    if (bestIndex < individualResults.length) {
      return individualResults[bestIndex].text || '';
    }
    return result.extracted_text || '';
  } else if (typeof selectedDraft === 'number') {
    const individualResults = (redundancyAnalysis.individual_results || []).filter((r: any) => r.success);
    if (selectedDraft < individualResults.length) {
      return individualResults[selectedDraft].text || '';
    }
  }

  return result.extracted_text || '';
}; 