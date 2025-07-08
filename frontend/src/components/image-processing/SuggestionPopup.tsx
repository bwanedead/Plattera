import React from 'react';

// A more structured alternative type
export interface SuggestionAlternative {
  text: string;
  source: string; // e.g., "Draft 2", "Consensus"
}

interface SuggestionPopupProps {
  position: { top: number; left: number };
  isVisible: boolean;
  word?: {
    text: string;
    confidence: number;
    alternatives?: SuggestionAlternative[];
  };
  onSelectAlternative: (alternative: string) => void;
  onEdit: () => void;
  // Pass mouse handlers to keep the popup open
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}

export const SuggestionPopup: React.FC<SuggestionPopupProps> = ({
  position,
  isVisible,
  word,
  onSelectAlternative,
  onEdit,
  onMouseEnter,
  onMouseLeave,
}) => {
  if (!word) return null;

  const agreement = (word.confidence * 100).toFixed(0);

  return (
    <div 
      className={`suggestion-popup ${isVisible ? 'visible' : ''}`}
      style={{ top: position.top, left: position.left }}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      {/* Compact percentage display in corner */}
      <div className="confidence-display">
        {agreement}%
      </div>
      
      <div className="suggestion-content">
        {/* Current word option */}
        <button
          className="suggestion-item current-word"
          onClick={() => onSelectAlternative(word.text)}
        >
          <span className="option-icon">✓</span>
          <div className="option-content">
            <span className="alternative-text">{word.text}</span>
            <span className="alternative-source">Keep current</span>
          </div>
        </button>

        {/* Alternative options */}
        {word.alternatives && word.alternatives.length > 0 && (
          word.alternatives
            .filter(alt => alt.text.toLowerCase().trim() !== word.text.toLowerCase().trim())
            .map((alt, index) => (
              <button
                key={index}
                className="suggestion-item alternative"
                onClick={() => onSelectAlternative(alt.text)}
              >
                <span className="option-icon">↻</span>
                <div className="option-content">
                  <span className="alternative-text">{alt.text}</span>
                  <span className="alternative-source">{alt.source}</span>
                </div>
              </button>
            ))
        )}
      </div>
      
      <div className="suggestion-footer">
        <button className="edit-button" onClick={onEdit}>
          <span className="option-icon">✎</span>
          <span>Edit</span>
        </button>
      </div>
    </div>
  );
}; 