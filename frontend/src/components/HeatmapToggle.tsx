import React, { useState } from 'react';
import { AnimatedBorder } from './AnimatedBorder';

interface HeatmapToggleProps {
  isEnabled: boolean;
  onToggle: (enabled: boolean) => void;
  hasRedundancyData: boolean;
}

export const HeatmapToggle: React.FC<HeatmapToggleProps> = ({
  isEnabled,
  onToggle,
  hasRedundancyData
}) => {
  const [isHovered, setIsHovered] = useState(false);

  // Don't render if no redundancy data available
  if (!hasRedundancyData) {
    return null;
  }

  const handleToggle = () => {
    onToggle(!isEnabled);
  };

  return (
    <div className="heatmap-toggle-container">
      <AnimatedBorder
        isHovered={isHovered}
        borderRadius={6}
        strokeWidth={2}
      >
        <button 
          className={`heatmap-toggle-button ${isEnabled ? 'enabled' : 'disabled'}`}
          onClick={handleToggle}
          onMouseEnter={() => setIsHovered(true)}
          onMouseLeave={() => setIsHovered(false)}
          title={isEnabled ? 'Hide Confidence Heatmap' : 'Show Confidence Heatmap'}
        >
          🔥
        </button>
      </AnimatedBorder>
    </div>
  );
}; 