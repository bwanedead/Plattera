import React, { useState } from 'react';
import { AnimatedBorder } from './AnimatedBorder';

interface HeatmapToggleProps {
  isEnabled: boolean;
  onToggle: (enabled: boolean) => void;
  hasRedundancyData: boolean;
  redundancyAnalysis?: {
    individual_results: Array<{
      success: boolean;
      text: string;
      tokens: number;
      error?: string;
    }>;
  };
}

export const HeatmapToggle: React.FC<HeatmapToggleProps> = ({
  isEnabled,
  onToggle,
  hasRedundancyData,
  redundancyAnalysis
}) => {
  const [isHovered, setIsHovered] = useState(false);
  const [showSingleDraftMessage, setShowSingleDraftMessage] = useState(false);

  // Don't render if no redundancy data available
  if (!hasRedundancyData) {
    return null;
  }

  // Check if we have multiple successful drafts
  const successfulDrafts = redundancyAnalysis?.individual_results?.filter(r => r.success) || [];
  const hasMultipleDrafts = successfulDrafts.length > 1;

  const handleToggle = () => {
    if (!hasMultipleDrafts) {
      // Show message instead of enabling heatmap for single drafts
      setShowSingleDraftMessage(true);
      setTimeout(() => setShowSingleDraftMessage(false), 3000);
      return;
    }
    onToggle(!isEnabled);
  };

  const getTitle = () => {
    if (!hasMultipleDrafts) {
      return 'Heatmap requires multiple drafts for confidence analysis';
    }
    return isEnabled ? 'Hide Confidence Heatmap' : 'Show Confidence Heatmap';
  };

  const getButtonClass = () => {
    if (!hasMultipleDrafts) {
      return 'heatmap-toggle-button disabled single-draft';
    }
    return `heatmap-toggle-button ${isEnabled ? 'enabled' : 'disabled'}`;
  };

  return (
    <div className="heatmap-toggle-container">
      <AnimatedBorder
        isHovered={isHovered}
        borderRadius={6}
        strokeWidth={2}
      >
        <button 
          className={getButtonClass()}
          onClick={handleToggle}
          onMouseEnter={() => setIsHovered(true)}
          onMouseLeave={() => setIsHovered(false)}
          title={getTitle()}
        >
          {!hasMultipleDrafts ? '🚫' : '🔥'}
        </button>
      </AnimatedBorder>
      
      {showSingleDraftMessage && (
        <div className="single-draft-tooltip">
          Only 1 draft succeeded.
          <br />
          Heatmap needs multiple drafts for confidence analysis.
        </div>
      )}
    </div>
  );
}; 