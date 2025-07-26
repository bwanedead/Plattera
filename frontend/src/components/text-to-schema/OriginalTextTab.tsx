import React from 'react';
import { CopyButton } from '../CopyButton';

interface OriginalTextTabProps {
  text: string;
}

export const OriginalTextTab: React.FC<OriginalTextTabProps> = ({ text }) => {
  return (
    <div className="original-text-tab">
      <div className="tab-header">
        <h4>Original Text</h4>
        <CopyButton
          onCopy={() => navigator.clipboard.writeText(text)}
          title="Copy original text"
        />
      </div>
      <div className="text-content">
        <pre className="original-text">
          {text}
        </pre>
      </div>
    </div>
  );
}; 