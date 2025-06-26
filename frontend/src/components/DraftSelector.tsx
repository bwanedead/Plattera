import React, { useState } from 'react';

interface DraftSelectorProps {
  redundancyAnalysis?: {
    individual_results: Array<{
      success: boolean;
      text: string;
      tokens: number;
      error?: string;
    }>;
    consensus_text: string;
    best_formatted_text: string;
    best_result_index: number;
  };
  onDraftSelect: (draftIndex: number | 'consensus' | 'best') => void;
  selectedDraft: number | 'consensus' | 'best';
}

export const DraftSelector: React.FC<DraftSelectorProps> = ({
  redundancyAnalysis,
  onDraftSelect,
  selectedDraft
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  // Don't render if no redundancy data
  if (!redundancyAnalysis || !redundancyAnalysis.individual_results) {
    return null;
  }

  const successfulResults = redundancyAnalysis.individual_results.filter(r => r.success);
  const totalDrafts = successfulResults.length;

  if (totalDrafts <= 1) {
    return null; // No point showing selector for single result
  }

  const handleDraftSelect = (draft: number | 'consensus' | 'best') => {
    onDraftSelect(draft);
    setIsExpanded(false);
  };

  const getCurrentDraftLabel = () => {
    if (selectedDraft === 'consensus') return 'Consensus';
    if (selectedDraft === 'best') return `Best (${redundancyAnalysis.best_result_index + 1})`;
    return `Draft ${selectedDraft + 1}`;
  };

  return (
    <div className="draft-selector-container">
      <div 
        className={`draft-selector-bubble ${isExpanded ? 'expanded' : ''}`}
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="draft-selector-current">
          <span className="draft-label">{getCurrentDraftLabel()}</span>
          <span className="draft-count">{totalDrafts} drafts</span>
          <span className={`expand-icon ${isExpanded ? 'rotated' : ''}`}>▼</span>
        </div>
        
        {isExpanded && (
          <div className="draft-selector-dropdown">
            <div 
              className={`draft-option ${selectedDraft === 'best' ? 'active' : ''}`}
              onClick={(e) => {
                e.stopPropagation();
                handleDraftSelect('best');
              }}
            >
              <span className="draft-option-label">Best Draft</span>
              <span className="draft-option-desc">Highest quality (Draft {redundancyAnalysis.best_result_index + 1})</span>
            </div>
            
            <div 
              className={`draft-option ${selectedDraft === 'consensus' ? 'active' : ''}`}
              onClick={(e) => {
                e.stopPropagation();
                handleDraftSelect('consensus');
              }}
            >
              <span className="draft-option-label">Consensus</span>
              <span className="draft-option-desc">Merged from all drafts</span>
            </div>
            
            <div className="draft-separator"></div>
            
            {successfulResults.map((result, index) => (
              <div 
                key={index}
                className={`draft-option ${selectedDraft === index ? 'active' : ''}`}
                onClick={(e) => {
                  e.stopPropagation();
                  handleDraftSelect(index);
                }}
              >
                <span className="draft-option-label">Draft {index + 1}</span>
                <span className="draft-option-desc">
                  {result.text.length} chars, {result.tokens} tokens
                  {index === redundancyAnalysis.best_result_index && (
                    <span className="best-badge">★</span>
                  )}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}; 