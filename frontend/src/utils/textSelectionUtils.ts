import { isJsonResult, formatJsonAsText } from './jsonFormatter';

export interface TextSelectionParams {
  selectedResult: any;
  selectedDraft: number | 'consensus' | 'best';
  selectedConsensusStrategy: string;
}

export const getCurrentText = ({ selectedResult, selectedDraft, selectedConsensusStrategy }: TextSelectionParams): string => {
  if (!selectedResult || selectedResult.status !== 'completed' || !selectedResult.result) {
    return selectedResult?.error || 'No result available';
  }

  const { result, error } = selectedResult;
  if (error) return error;
  if (!result) return 'No result available';

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

  // CRITICAL DRAFT SELECTION LOGIC
  if (selectedDraft === 'best') {
    const extractedText = result.extracted_text || '';
    // Format JSON as readable text if it's JSON
    return isJsonResult(extractedText) ? formatJsonAsText(extractedText) : extractedText;
  } else if (selectedDraft === 'consensus') {
    const consensusText = redundancyAnalysis.consensus_text || result.extracted_text || '';
    // Format JSON as readable text if it's JSON
    return isJsonResult(consensusText) ? formatJsonAsText(consensusText) : consensusText;
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

export const getRawText = ({ selectedResult, selectedDraft, selectedConsensusStrategy }: TextSelectionParams): string => {
  if (!selectedResult || selectedResult.status !== 'completed' || !selectedResult.result) {
    return selectedResult?.error || 'No result available';
  }

  const { result, error } = selectedResult;
  if (error) return error;
  if (!result) return 'No result available';

  const redundancyAnalysis = result.metadata?.redundancy_analysis;
  
  // Use selected consensus strategy if available
  if (redundancyAnalysis?.all_consensus_results?.[selectedConsensusStrategy]) {
    return redundancyAnalysis.all_consensus_results[selectedConsensusStrategy].consensus_text;
  }
  
  // Fallback to original logic
  if (!redundancyAnalysis) {
    return result.extracted_text || 'No text available';
  }

  // Draft selection logic for raw text
  if (selectedDraft === 'best') {
    return result.extracted_text || '';
  } else if (selectedDraft === 'consensus') {
    return redundancyAnalysis.consensus_text || result.extracted_text || '';
  } else if (typeof selectedDraft === 'number') {
    const individualResults = (redundancyAnalysis.individual_results || []).filter((r: any) => r.success);
    if (selectedDraft < individualResults.length) {
      return individualResults[selectedDraft].text || '';
    }
  }

  return result.extracted_text || '';
}; 