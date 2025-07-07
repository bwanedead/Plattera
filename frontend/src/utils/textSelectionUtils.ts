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
  console.log('🔍 FRONTEND DEBUG: extractFormattedTextFromAlignment called');
  console.log('🔍 FRONTEND DEBUG: alignmentResult:', alignmentResult);
  console.log('🔍 FRONTEND DEBUG: selectedDraft:', selectedDraft);
  
  if (!alignmentResult?.success || !alignmentResult.alignment_results?.blocks) {
    console.log('⚠️ FRONTEND DEBUG: No alignment results or blocks found');
    return null;
  }

  const blocks = alignmentResult.alignment_results.blocks;
  console.log('🔍 FRONTEND DEBUG: Found blocks:', Object.keys(blocks));
  const blockTexts: string[] = [];

  // Process each block
  for (const [blockId, blockData] of Object.entries(blocks)) {
    console.log(`🔍 FRONTEND DEBUG: Processing block ${blockId}`);
    const alignedSequences = (blockData as any)?.aligned_sequences || [];
    console.log(`🔍 FRONTEND DEBUG: Found ${alignedSequences.length} sequences in block ${blockId}`);
    
    if (alignedSequences.length === 0) {
      console.log(`⚠️ FRONTEND DEBUG: No sequences in block ${blockId}, skipping`);
      continue;
    }

    let selectedSequence = null;

    // Find the sequence for the selected draft
    if (typeof selectedDraft === 'number') {
      console.log(`🔍 FRONTEND DEBUG: Looking for draft ${selectedDraft} (numeric)`);
      // Find sequence by draft index
      selectedSequence = alignedSequences.find((seq: any) => {
        const matches = seq.draft_id === `Draft_${selectedDraft + 1}` || 
               seq.draft_id === `draft_${selectedDraft + 1}` ||
               seq.draft_id === `Draft ${selectedDraft + 1}`;
        console.log(`🔍 FRONTEND DEBUG: Checking sequence ${seq.draft_id} against Draft_${selectedDraft + 1}: ${matches}`);
        return matches;
      });
      
      // Fallback to array index if draft_id doesn't match
      if (!selectedSequence && selectedDraft < alignedSequences.length) {
        console.log(`🔍 FRONTEND DEBUG: Using fallback array index ${selectedDraft}`);
        selectedSequence = alignedSequences[selectedDraft];
      }
    } else if (selectedDraft === 'consensus' || selectedDraft === 'best') {
      console.log(`🔍 FRONTEND DEBUG: Using first sequence for ${selectedDraft}`);
      // For consensus/best, use the first sequence as default
      selectedSequence = alignedSequences[0];
    }

    console.log('🔍 FRONTEND DEBUG: Selected sequence:', selectedSequence);

    if (selectedSequence && selectedSequence.tokens) {
      console.log(`🔍 FRONTEND DEBUG: Sequence has ${selectedSequence.tokens.length} tokens`);
      console.log('🔍 FRONTEND DEBUG: First 10 tokens:', selectedSequence.tokens.slice(0, 10));
      console.log('🔍 FRONTEND DEBUG: Formatting applied flag:', selectedSequence.formatting_applied);
      
      // Extract non-gap tokens and join them
      const tokens = selectedSequence.tokens.filter((token: string) => token && token !== '-');
      console.log(`🔍 FRONTEND DEBUG: After filtering gaps: ${tokens.length} tokens`);
      console.log('🔍 FRONTEND DEBUG: First 10 filtered tokens:', tokens.slice(0, 10));
      
      const blockText = tokens.join(' ');
      console.log(`🔍 FRONTEND DEBUG: Block text length: ${blockText.length} characters`);
      console.log('🔍 FRONTEND DEBUG: Block text preview:', blockText.substring(0, 200) + '...');
      
      blockTexts.push(blockText);
    } else {
      console.log(`⚠️ FRONTEND DEBUG: No tokens found in selected sequence for block ${blockId}`);
    }
  }

  console.log(`🔍 FRONTEND DEBUG: Total block texts: ${blockTexts.length}`);
  const result = blockTexts.join('\n\n');
  console.log(`🔍 FRONTEND DEBUG: Final result length: ${result.length} characters`);
  console.log('🔍 FRONTEND DEBUG: Final result preview:', result.substring(0, 300) + '...');
  
  return result;
};

export const getCurrentText = ({ selectedResult, selectedDraft, selectedConsensusStrategy, alignmentResult }: TextSelectionParams): string => {
  console.log('🔍 FRONTEND DEBUG: getCurrentText called');
  console.log('🔍 FRONTEND DEBUG: selectedResult status:', selectedResult?.status);
  console.log('🔍 FRONTEND DEBUG: selectedDraft:', selectedDraft);
  console.log('🔍 FRONTEND DEBUG: alignmentResult success:', alignmentResult?.success);
  
  if (!selectedResult || selectedResult.status !== 'completed' || !selectedResult.result) {
    console.log('⚠️ FRONTEND DEBUG: No valid result available');
    return selectedResult?.error || 'No result available';
  }

  const { result, error } = selectedResult;
  if (error) {
    console.log('⚠️ FRONTEND DEBUG: Result has error:', error);
    return error;
  }
  if (!result) {
    console.log('⚠️ FRONTEND DEBUG: No result data');
    return 'No result available';
  }

  // PRIORITY 1: Use formatted text from alignment results if available
  if (alignmentResult?.success) {
    console.log('✅ FRONTEND DEBUG: Alignment result available, attempting to extract formatted text');
    const formattedText = extractFormattedTextFromAlignment(alignmentResult, selectedDraft);
    if (formattedText) {
      console.log('✅ FRONTEND DEBUG: Using formatted text from alignment results');
      console.log('🔍 FRONTEND DEBUG: Formatted text length:', formattedText.length);
      return isJsonResult(formattedText) ? formatJsonAsText(formattedText) : formattedText;
    } else {
      console.log('⚠️ FRONTEND DEBUG: No formatted text extracted from alignment results');
    }
  } else {
    console.log('⚠️ FRONTEND DEBUG: No alignment result available');
  }

  // PRIORITY 2: Fall back to original redundancy analysis logic
  console.log('🔍 FRONTEND DEBUG: Falling back to redundancy analysis');
  const redundancyAnalysis = result.metadata?.redundancy_analysis;
  
  // Use selected consensus strategy if available
  if (redundancyAnalysis?.all_consensus_results?.[selectedConsensusStrategy]) {
    console.log('✅ FRONTEND DEBUG: Using consensus strategy:', selectedConsensusStrategy);
    const consensusText = redundancyAnalysis.all_consensus_results[selectedConsensusStrategy].consensus_text;
    // Format JSON as readable text if it's JSON
    return isJsonResult(consensusText) ? formatJsonAsText(consensusText) : consensusText;
  }
  
  // Fallback to original logic
  if (!redundancyAnalysis) {
    console.log('⚠️ FRONTEND DEBUG: No redundancy analysis, using extracted text');
    const extractedText = result.extracted_text || 'No text available';
    // Format JSON as readable text if it's JSON
    return isJsonResult(extractedText) ? formatJsonAsText(extractedText) : extractedText;
  }

  // UPDATED DRAFT SELECTION LOGIC
  if (selectedDraft === 'consensus') {
    console.log('✅ FRONTEND DEBUG: Using consensus text');
    const consensusText = redundancyAnalysis.consensus_text || result.extracted_text || '';
    // Format JSON as readable text if it's JSON
    return isJsonResult(consensusText) ? formatJsonAsText(consensusText) : consensusText;
  } else if (selectedDraft === 'best') {
    console.log('✅ FRONTEND DEBUG: Using best draft');
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
    console.log('✅ FRONTEND DEBUG: Using specific draft:', selectedDraft);
    const individualResults = (redundancyAnalysis.individual_results || []).filter((r: any) => r.success);
    if (selectedDraft < individualResults.length) {
      const draftText = individualResults[selectedDraft].text || '';
      // Format JSON as readable text if it's JSON
      return isJsonResult(draftText) ? formatJsonAsText(draftText) : draftText;
    }
  }

  // Fallback to main text
  console.log('⚠️ FRONTEND DEBUG: Using fallback main text');
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