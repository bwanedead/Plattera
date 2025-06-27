import React from 'react';

interface CopyButtonProps {
  onCopy: () => void;
  title?: string;
  position?: 'floating-left' | 'floating-right' | 'inline' | 'toolbar';
  size?: 'small' | 'medium' | 'large';
}

export const CopyButton: React.FC<CopyButtonProps> = ({ 
  onCopy, 
  title = "Copy", 
  position = 'inline',
  size = 'medium'
}) => {
  const iconSize = size === 'small' ? 16 : size === 'large' ? 24 : 20;

  const getPositionStyles = (): React.CSSProperties => {
    switch(position) {
      case 'floating-left': 
        return { 
          position: 'absolute', 
          top: '1rem', 
          left: '-0.5rem',
          zIndex: 10
        };
      case 'floating-right': 
        return { 
          position: 'absolute', 
          top: '1rem', 
          right: '1rem',
          zIndex: 10
        };
      case 'toolbar': 
        return { 
          position: 'relative', 
          margin: '0 0.5rem'
        };
      default: 
        return { 
          position: 'relative'
        };
    }
  };

  return (
    <button 
      onClick={onCopy}
      title={title}
      className="copy-button"
      style={{
        ...getPositionStyles(),
        background: 'rgba(255, 0, 0, 0.3)',
        border: '1px solid yellow',
        padding: '0.5rem',
        cursor: 'pointer',
        opacity: 0.7,
        transition: 'all 0.2s ease',
        width: '40px',
        height: '40px'
      }}
    >
      <div style={{ color: 'white', fontSize: '10px' }}>COPY</div>
    </button>
  );
};