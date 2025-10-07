import React, { useState } from 'react';
import { AnimatedBorder } from '../AnimatedBorder';

interface AlignmentButtonProps {
  // visible is kept for backward compatibility but no longer hides the button
  visible?: boolean;
  onAlign: () => void;
  onTogglePanel?: () => void; // NEW: open/close panel without rerun
  isAligning: boolean;
  disabled?: boolean;
  tooltip?: string;
}

export const AlignmentButton: React.FC<AlignmentButtonProps> = ({
  visible = true,
  onAlign,
  onTogglePanel,
  isAligning,
  disabled = false,
  tooltip
}) => {
  const [isHovered, setIsHovered] = useState(false);

  // Always render; rely on disabled state instead of hiding entirely

  return (
    <div className="alignment-button-container">
      <AnimatedBorder
        isHovered={isHovered && !disabled}
        borderRadius={6}
        strokeWidth={2}
      >
        <button
          className={`alignment-button-bubble ${isAligning ? 'aligning' : ''} ${disabled ? 'disabled' : ''}`}
          onClick={() => {
            if (onTogglePanel && !isAligning) {
              onTogglePanel();
              return;
            }
            onAlign();
          }}
          onMouseEnter={() => setIsHovered(true)}
          onMouseLeave={() => setIsHovered(false)}
          disabled={disabled || isAligning}
          title={
            isAligning
              ? 'Aligning drafts...'
              : (disabled ? (tooltip || 'Requires redundancy > 1 (at least 2 drafts) to run alignment') : 'Align drafts or toggle alignment panel')
          }
        >
          {isAligning ? '⏳' : '🧬'}
        </button>
      </AnimatedBorder>
    </div>
  );
}; 