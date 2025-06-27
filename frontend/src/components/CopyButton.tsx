import React from 'react';

interface CopyButtonProps {
  onCopy: () => void;
  title?: string;
  className?: string;
  style?: React.CSSProperties;
}

export const CopyButton: React.FC<CopyButtonProps> = ({ 
  onCopy, 
  title = "Copy", 
  className = "",
  style = {}
}) => {
  return (
    <button 
      onClick={onCopy}
      title={title}
      className={`copy-button ${className}`}
      style={{
        background: 'none',
        border: 'none',
        padding: '0.5rem',
        cursor: 'pointer',
        opacity: 0.7,
        transition: 'all 0.2s ease',
        ...style
      }}
    >
      {/* Visible icon - always shown */}
      <svg 
        viewBox="0 0 24 24" 
        className="copy-icon-visible"
        style={{
          width: '20px',
          height: '20px',
          fill: '#cccccc',
          stroke: 'none',
          transition: 'opacity 0.2s ease'
        }}
      >
        <path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z" />
        <path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1z" />
      </svg>
      
      {/* Tracing animation - only appears on hover */}
      <svg 
        viewBox="0 0 24 24" 
        className="copy-icon-trace"
        style={{
          width: '20px',
          height: '20px',
          position: 'absolute',
          top: '0.5rem',
          left: '0.5rem',
          opacity: 0,
          transition: 'opacity 0.2s ease'
        }}
      >
        <path 
          d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z" 
          className="copy-path-back"
          style={{
            fill: 'none',
            stroke: 'var(--accent-primary)',
            strokeWidth: '0.8',
            strokeLinecap: 'round',
            strokeLinejoin: 'round',
            strokeDasharray: '150',
            strokeDashoffset: '150'
          }}
        />
        <path 
          d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1z" 
          className="copy-path-front"
          style={{
            fill: 'none',
            stroke: 'var(--accent-primary)',
            strokeWidth: '0.8',
            strokeLinecap: 'round',
            strokeLinejoin: 'round',
            strokeDasharray: '150',
            strokeDashoffset: '150'
          }}
        />
      </svg>
    </button>
  );
};