import React, { useState } from 'react';
import { AnimatedBorder } from './AnimatedBorder';

interface HeatmapToggleProps {
  isEnabled: boolean;
  onToggle: (enabled: boolean) => void;
  hasRedundancyData: boolean;
  isLoading?: boolean;
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
  isLoading = false,
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
    if (isLoading) {
      return; // Don't allow clicks while loading
    }
    
    if (!hasMultipleDrafts) {
      // Show message instead of enabling heatmap for single drafts
      setShowSingleDraftMessage(true);
      setTimeout(() => setShowSingleDraftMessage(false), 3000);
      return;
    }
    onToggle(!isEnabled);
  };

  const getTitle = () => {
    if (isLoading) {
      return 'Running BioPython alignment analysis...';
    }
    if (!hasMultipleDrafts) {
      return 'BioPython visualization requires multiple drafts for alignment analysis';
    }
    return 'Show BioPython Alignment Visualization';
  };

  const getButtonClass = () => {
    if (isLoading) {
      return 'heatmap-toggle-button loading';
    }
    if (!hasMultipleDrafts) {
      return 'heatmap-toggle-button disabled single-draft';
    }
    return 'heatmap-toggle-button enabled'; // Always show as enabled since it's not a toggle
  };

  const getButtonContent = () => {
    if (isLoading) {
      return '⏳'; // Loading spinner emoji
    }
    if (!hasMultipleDrafts) {
      return '🚫';
    }
    return '🔥';
  };

  return (
    <div className="heatmap-toggle-container">
      <AnimatedBorder
        isHovered={isHovered && !isLoading}
        borderRadius={6}
        strokeWidth={2}
      >
        <button 
          className={getButtonClass()}
          onClick={handleToggle}
          onMouseEnter={() => setIsHovered(true)}
          onMouseLeave={() => setIsHovered(false)}
          title={getTitle()}
          disabled={isLoading}
        >
          {getButtonContent()}
        </button>
      </AnimatedBorder>
      
      {isLoading && (
        <div className="alignment-loading-tooltip">
          Running BioPython alignment...
        </div>
      )}
      
      {showSingleDraftMessage && !isLoading && (
        <div className="single-draft-tooltip">
          Only 1 draft succeeded.
          <br />
          Heatmap needs multiple drafts for confidence analysis.
        </div>
      )}
    </div>
  );
}; 