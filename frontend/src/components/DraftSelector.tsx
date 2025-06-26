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
  const [isVisible, setIsVisible] = useState(false);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);

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
    setIsDropdownOpen(false);
  };

  const getCurrentDraftLabel = () => {
    if (selectedDraft === 'consensus') return 'Consensus';
    if (selectedDraft === 'best') return `Best (${redundancyAnalysis.best_result_index + 1})`;
    return `Draft ${selectedDraft + 1}`;
  };

  const toggleVisibility = () => {
    setIsVisible(!isVisible);
    if (!isVisible) {
      setIsDropdownOpen(false); // Close dropdown when hiding
    }
  };

  // Collapsed state - just a small icon
  if (!isVisible) {
    return (
      <div className="draft-selector-collapsed">
        <button 
          className="draft-selector-icon"
          onClick={toggleVisibility}
          title={`${totalDrafts} drafts available - Currently viewing: ${getCurrentDraftLabel()}`}
        >
          <span className="draft-icon">📄</span>
          <span className="draft-count">{totalDrafts}</span>
        </button>
      </div>
    );
  }

  // Expanded state - compact header with dropdown
  return (
    <div className="draft-selector-expanded">
      <div className="draft-selector-header">
        <div className="draft-header-left">
          <span className="draft-label">Drafts</span>
          <span className="draft-count-badge">{totalDrafts}</span>
        </div>
        <button 
          className="draft-close-btn"
          onClick={toggleVisibility}
          title="Hide draft selector"
        >
          ×
        </button>
      </div>
      
      <div className="draft-current-selection">
        <button 
          className="draft-current-btn"
          onClick={() => setIsDropdownOpen(!isDropdownOpen)}
        >
          <span className="current-draft-name">{getCurrentDraftLabel()}</span>
          <span className={`dropdown-arrow ${isDropdownOpen ? 'open' : ''}`}>▼</span>
        </button>
      </div>
      
      {isDropdownOpen && (
        <div className="draft-dropdown">
          <div 
            className={`draft-item ${selectedDraft === 'best' ? 'active' : ''}`}
            onClick={() => handleDraftSelect('best')}
          >
            <span className="draft-name">Best <span className="recommended">★</span></span>
            <span className="draft-desc">Highest quality</span>
          </div>
          
          <div 
            className={`draft-item ${selectedDraft === 'consensus' ? 'active' : ''}`}
            onClick={() => handleDraftSelect('consensus')}
          >
            <span className="draft-name">Consensus</span>
            <span className="draft-desc">Merged result</span>
          </div>
          
          <div className="draft-divider"></div>
          
          {successfulResults.map((result, index) => (
            <div 
              key={index}
              className={`draft-item ${selectedDraft === index ? 'active' : ''}`}
              onClick={() => handleDraftSelect(index)}
            >
              <span className="draft-name">
                Draft {index + 1}
                {index === redundancyAnalysis.best_result_index && (
                  <span className="best-indicator">★</span>
                )}
              </span>
              <span className="draft-desc">{result.tokens} tokens</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}; 