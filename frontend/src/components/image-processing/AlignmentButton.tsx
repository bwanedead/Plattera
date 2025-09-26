import React, { useState } from 'react';
import { AnimatedBorder } from '../AnimatedBorder';

interface AlignmentButtonProps {
  // visible is kept for backward compatibility but no longer hides the button
  visible?: boolean;
  onAlign: () => void;
  isAligning: boolean;
  disabled?: boolean;
}

export const AlignmentButton: React.FC<AlignmentButtonProps> = ({
  visible = true,
  onAlign,
  isAligning,
  disabled = false
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
          onClick={onAlign}
          onMouseEnter={() => setIsHovered(true)}
          onMouseLeave={() => setIsHovered(false)}
          disabled={disabled || isAligning}
          title={isAligning ? 'Aligning drafts...' : 'Align drafts for confidence analysis'}
        >
          {isAligning ? '⏳' : '🧬'}
        </button>
      </AnimatedBorder>
    </div>
  );
}; 