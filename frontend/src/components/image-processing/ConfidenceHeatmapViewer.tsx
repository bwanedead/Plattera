import React, { useState, useCallback } from 'react';
import { AlignmentResult, ConfidenceWord } from '../../types/imageProcessing';

interface ConfidenceHeatmapViewerProps {
  alignmentResult: AlignmentResult | null;
  selectedDraft: number | 'consensus' | 'best';
  currentText: string;
  onWordClick?: (word: ConfidenceWord, position: number) => void;
}

export const ConfidenceHeatmapViewer: React.FC<ConfidenceHeatmapViewerProps> = ({
  alignmentResult,
  selectedDraft,
  currentText,
  onWordClick
}) => {
  const [selectedWord, setSelectedWord] = useState<ConfidenceWord | null>(null);
  const [popupPosition, setPopupPosition] = useState<{ x: number; y: number } | null>(null);

  // Parse the text into words with confidence scores
  const parseTextWithConfidence = useCallback((): ConfidenceWord[] => {
    if (!alignmentResult || !alignmentResult.success) {
      // Fallback: parse text without confidence data
      return currentText.split(/\s+/).map((word, index) => ({
        text: word,
        confidence: 1.0,
        position: index,
        alternatives: [],
        isClickable: false
      }));
    }

    // TODO: Parse alignment result to extract per-word confidence
    // For now, create mock confidence data based on text
    const words = currentText.split(/\s+/);
    return words.map((word, index) => {
      // Mock confidence calculation (replace with actual alignment data parsing)
      const mockConfidence = Math.random() * 0.4 + 0.6; // 0.6 to 1.0
      
      return {
        text: word,
        confidence: mockConfidence,
        position: index,
        alternatives: [], // TODO: Extract from alignment result
        isClickable: mockConfidence < 0.9 // Make low-confidence words clickable
      };
    });
  }, [alignmentResult, currentText]);

  const confidenceWords = parseTextWithConfidence();

  const getConfidenceClass = (confidence: number): string => {
    if (confidence >= 0.8) return 'high-confidence';
    if (confidence >= 0.5) return 'medium-confidence';
    return 'low-confidence';
  };

  const handleWordClick = (word: ConfidenceWord, event: React.MouseEvent) => {
    if (!word.isClickable) return;

    const rect = (event.target as HTMLElement).getBoundingClientRect();
    setPopupPosition({
      x: rect.left + rect.width / 2,
      y: rect.top - 10
    });
    setSelectedWord(word);
    
    if (onWordClick) {
      onWordClick(word, word.position);
    }
  };

  const closePopup = () => {
    setSelectedWord(null);
    setPopupPosition(null);
  };

  if (!alignmentResult) {
    return (
      <div className="confidence-heatmap-viewer">
        <div className="heatmap-text-container">
          <div className="heatmap-unavailable">
            <p>Confidence heatmap not available</p>
            <p>Run alignment analysis to see confidence visualization</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="confidence-heatmap-viewer">
      <div className="heatmap-info-bar">
        <div className="heatmap-legend">
          <span className="legend-item">
            <span className="legend-color high-confidence"></span>
            High (80-100%)
          </span>
          <span className="legend-item">
            <span className="legend-color medium-confidence"></span>
            Medium (50-79%)
          </span>
          <span className="legend-item">
            <span className="legend-color low-confidence"></span>
            Low (0-49%)
          </span>
        </div>
        <div className="heatmap-draft-info">
          Viewing: {selectedDraft === 'best' ? 'Best Draft' : 
                   selectedDraft === 'consensus' ? 'Consensus' : 
                   `Draft ${selectedDraft + 1}`}
        </div>
      </div>

      <div className="heatmap-text-container">
        <div className="confidence-text">
          {confidenceWords.map((word, index) => (
            <React.Fragment key={index}>
              <span
                className={`confidence-word ${getConfidenceClass(word.confidence)} ${
                  word.isClickable ? 'clickable' : ''
                }`}
                onClick={(e) => handleWordClick(word, e)}
                title={`Confidence: ${Math.round(word.confidence * 100)}%`}
              >
                {word.text}
              </span>
              {index < confidenceWords.length - 1 && ' '}
            </React.Fragment>
          ))}
        </div>
      </div>

      {/* Confidence Popup */}
      {selectedWord && popupPosition && (
        <div
          className="confidence-popup"
          style={{
            left: popupPosition.x,
            top: popupPosition.y,
            transform: 'translateX(-50%) translateY(-100%)'
          }}
        >
          <div className="popup-content">
            <button className="popup-close" onClick={closePopup}>×</button>
            
            <div className="popup-word-info">
              <div className="popup-word">{selectedWord.text}</div>
              <div className="popup-confidence">
                Confidence: {Math.round(selectedWord.confidence * 100)}%
              </div>
            </div>

            {selectedWord.alternatives && selectedWord.alternatives.length > 0 && (
              <div className="popup-alternatives">
                <h5>Alternative versions:</h5>
                {selectedWord.alternatives.map((alt, index) => (
                  <div key={index} className="alternative-option">
                    {alt}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Click overlay to close popup */}
      {selectedWord && (
        <div className="popup-overlay" onClick={closePopup}></div>
      )}
    </div>
  );
}; 