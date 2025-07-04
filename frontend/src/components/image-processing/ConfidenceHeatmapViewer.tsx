import React, { useState, useMemo } from 'react';
import { AlignmentResult, ConfidenceWord, AlignmentToken } from '../../types/imageProcessing';

interface ConfidenceHeatmapViewerProps {
  alignmentResult: AlignmentResult | null;
  selectedDraft: number | 'consensus' | 'best';
  currentText: string;
  onWordClick?: (word: ConfidenceWord, position: number) => void;
}

// Parse the actual alignment engine results to extract token-level confidence data
const parseAlignmentResults = (
  alignmentResult: AlignmentResult | null, 
  selectedDraft: number | 'consensus' | 'best',
  currentText: string
): AlignmentToken[] => {
  if (!alignmentResult || !alignmentResult.success) {
    return [];
  }

  // For consensus or best, we need to use the confidence data differently
  if (selectedDraft === 'consensus' || selectedDraft === 'best') {
    // Use overall confidence results to create tokens from current text
    const confidenceResults = alignmentResult.confidence_results;
    if (!confidenceResults?.block_confidences) {
      return [];
    }

    // Get the first block's confidence data (assuming single block for now)
    const blockIds = Object.keys(confidenceResults.block_confidences);
    if (blockIds.length === 0) {
      return [];
    }

    const blockConfidence = confidenceResults.block_confidences[blockIds[0]];
    const scores = blockConfidence.scores || [];
    const confidenceLevels = blockConfidence.confidence_levels || [];
    const tokenAgreements = blockConfidence.token_agreements || [];

    // Split current text into words and map to confidence data
    const words = currentText.split(/\s+/).filter(word => word.length > 0);
    const tokens: AlignmentToken[] = [];

    // Map words to confidence scores (this is approximate since alignment positions != word positions)
    words.forEach((word, wordIndex) => {
      // Use modulo to cycle through confidence scores if we have fewer scores than words
      const scoreIndex = Math.min(wordIndex, scores.length - 1);
      const confidence = scores[scoreIndex] || 1.0;
      const level = confidenceLevels[scoreIndex] || 'high';
      const agreement = tokenAgreements[scoreIndex] || {};

      // Extract alternatives from token_counts
      const tokenCounts = agreement.token_counts || {};
      const alternatives = Object.keys(tokenCounts).filter(token => token !== word);

      tokens.push({
        token: word,
        confidence: confidence,
        position: wordIndex,
        original_start: wordIndex,
        is_difference: level === 'low' || level === 'medium',
        alternatives: alternatives
      });
    });

    return tokens;
  }

  // For specific draft numbers, we need to use the alignment mapping
  if (typeof selectedDraft === 'number') {
    const alignmentResults = alignmentResult.alignment_results;
    const confidenceResults = alignmentResult.confidence_results;
    
    if (!alignmentResults?.blocks || !confidenceResults?.block_confidences) {
      return [];
    }

    // Get the first block (assuming single block structure)
    const blockIds = Object.keys(alignmentResults.blocks);
    if (blockIds.length === 0) {
      return [];
    }

    const blockId = blockIds[0];
    const blockData = alignmentResults.blocks[blockId];
    const blockConfidence = confidenceResults.block_confidences[blockId];

    if (!blockData?.aligned_sequences || !blockConfidence) {
      return [];
    }

    // Find the specific draft's sequence
    const draftSequence = blockData.aligned_sequences.find((seq: any) => 
      seq.draft_id === `Draft_${selectedDraft + 1}`
    );

    if (!draftSequence?.tokens) {
      return [];
    }

    const scores = blockConfidence.scores || [];
    const confidenceLevels = blockConfidence.confidence_levels || [];
    const tokenAgreements = blockConfidence.token_agreements || [];

    // Create tokens from the aligned sequence
    const tokens: AlignmentToken[] = [];
    draftSequence.tokens.forEach((token: string, index: number) => {
      if (token !== '-') { // Skip gaps
        const confidence = scores[index] || 1.0;
        const level = confidenceLevels[index] || 'high';
        const agreement = tokenAgreements[index] || {};

        // Extract alternatives from token_counts
        const tokenCounts = agreement.token_counts || {};
        const alternatives = Object.keys(tokenCounts).filter(t => t !== token);

        tokens.push({
          token: token,
          confidence: confidence,
          position: index,
          original_start: index,
          is_difference: level === 'low' || level === 'medium',
          alternatives: alternatives
        });
      }
    });

    return tokens;
  }

  return [];
};

export const ConfidenceHeatmapViewer: React.FC<ConfidenceHeatmapViewerProps> = ({
  alignmentResult,
  selectedDraft,
  currentText,
  onWordClick
}) => {
  const [selectedWord, setSelectedWord] = useState<AlignmentToken | null>(null);
  const [popupPosition, setPopupPosition] = useState<{ x: number; y: number } | null>(null);

  // Parse alignment results into displayable tokens
  const alignmentTokens = useMemo(() => 
    parseAlignmentResults(alignmentResult, selectedDraft, currentText),
    [alignmentResult, selectedDraft, currentText]
  );

  const getConfidenceClass = (confidence: number): string => {
    if (confidence >= 0.8) return 'high-confidence';
    if (confidence >= 0.5) return 'medium-confidence';
    return 'low-confidence';
  };

  const handleWordClick = (token: AlignmentToken, event: React.MouseEvent) => {
    if (!token.is_difference) return;

    const rect = (event.target as HTMLElement).getBoundingClientRect();
    setPopupPosition({
      x: rect.left + rect.width / 2,
      y: rect.top - 10
    });
    setSelectedWord(token);
    
    if (onWordClick) {
      const legacyWord: ConfidenceWord = {
        text: token.token,
        confidence: token.confidence,
        position: token.original_start,
        alternatives: token.alternatives || [],
        isClickable: token.is_difference,
      };
      onWordClick(legacyWord, legacyWord.position);
    }
  };

  const closePopup = () => {
    setSelectedWord(null);
    setPopupPosition(null);
  };

  // If we don't have alignment results or no tokens were parsed, show fallback
  if (!alignmentResult || !alignmentResult.success || alignmentTokens.length === 0) {
    return (
      <div className="confidence-heatmap-viewer">
        <div className="heatmap-text-container">
          <div className="heatmap-unavailable">
            <p>Confidence heatmap not available</p>
            <p>No alignment data found for the selected draft</p>
            <div className="debug-info" style={{ marginTop: '10px', fontSize: '0.8em', color: '#666' }}>
              <p>Debug: selectedDraft = {String(selectedDraft)}</p>
              <p>Debug: hasAlignmentResult = {!!alignmentResult}</p>
              <p>Debug: alignmentSuccess = {alignmentResult?.success}</p>
              <p>Debug: tokensFound = {alignmentTokens.length}</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="confidence-heatmap-viewer">
      <div className="heatmap-info-bar">
        <div className="heatmap-legend">
          <span className="legend-item"><span className="legend-color high-confidence"></span>High (80-100%)</span>
          <span className="legend-item"><span className="legend-color medium-confidence"></span>Medium (50-79%)</span>
          <span className="legend-item"><span className="legend-color low-confidence"></span>Low (0-49%)</span>
        </div>
        <div className="heatmap-draft-info">
          Viewing: {selectedDraft === 'best' ? 'Best Draft' : 
                   selectedDraft === 'consensus' ? 'Consensus' : 
                   `Draft ${selectedDraft + 1}`}
        </div>
      </div>

      <div className="heatmap-text-container">
        <div className="confidence-text">
          {alignmentTokens.map((token, index) => (
            <React.Fragment key={index}>
              <span
                className={`confidence-word ${getConfidenceClass(token.confidence)} ${
                  token.is_difference ? 'clickable' : ''
                }`}
                onClick={(e) => handleWordClick(token, e)}
                title={`Confidence: ${Math.round(token.confidence * 100)}%${token.is_difference ? ' (Click for alternatives)' : ''}`}
              >
                {token.token}
              </span>
              {index < alignmentTokens.length - 1 && ' '}
            </React.Fragment>
          ))}
        </div>
      </div>

      {/* Confidence Popup */}
      {selectedWord && popupPosition && (
        <div className="popup-overlay" onClick={closePopup}>
          <div
            className="confidence-popup"
            style={{
              left: popupPosition.x,
              top: popupPosition.y,
              transform: 'translateX(-50%) translateY(-100%)'
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="popup-content">
              <button className="popup-close" onClick={closePopup}>×</button>
              
              <div className="popup-word-info">
                <div className="popup-word">{selectedWord.token}</div>
                <div className="popup-confidence">
                  Confidence: {Math.round(selectedWord.confidence * 100)}%
                </div>
              </div>

              {selectedWord.alternatives && selectedWord.alternatives.length > 0 && (
                <div className="popup-alternatives">
                  <h5>Alternative versions:</h5>
                  {selectedWord.alternatives.map((alt, i) => (
                    <div key={i} className="alternative-option">{alt}</div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}; 