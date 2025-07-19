import React from 'react';
import { BoundingBoxResult } from '../../types/boundingBox';

interface BoundingBoxViewerProps {
  boundingBoxResult: BoundingBoxResult;
  imageUrl: string;
  onClose: () => void;
}

export const BoundingBoxViewer: React.FC<BoundingBoxViewerProps> = ({
  boundingBoxResult,
  imageUrl,
  onClose
}) => {
  if (!boundingBoxResult.success) {
    return (
      <div className="bounding-box-viewer">
        <div className="viewer-header">
          <h3>Bounding Box Viewer</h3>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>
        <div className="viewer-content">
          <p className="error-message">
            {boundingBoxResult.error || 'Bounding box detection failed'}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="bounding-box-viewer">
      <div className="viewer-header">
        <h3>Bounding Box Analysis</h3>
        <button className="close-btn" onClick={onClose}>×</button>
      </div>
      
      <div className="viewer-content">
        <div className="image-container">
          <img src={imageUrl} alt="Document with bounding boxes" />
          <svg className="bounding-box-overlay">
            {/* Render bounding boxes here */}
            {boundingBoxResult.words_by_line.map((line, lineIndex) => (
              <g key={lineIndex}>
                {line.words.map((word, wordIndex) => (
                  <rect
                    key={`${lineIndex}-${wordIndex}`}
                    x={word.bounds.x1}
                    y={word.bounds.y1}
                    width={word.bounds.x2 - word.bounds.x1}
                    height={word.bounds.y2 - word.bounds.y1}
                    fill="none"
                    stroke={word.confidence > 0.8 ? "#00ff00" : word.confidence > 0.5 ? "#ffff00" : "#ff0000"}
                    strokeWidth="1"
                    opacity="0.7"
                  />
                ))}
              </g>
            ))}
          </svg>
        </div>
        
        <div className="bounding-box-stats">
          <div className="stat-item">
            <span className="stat-label">Total Lines:</span>
            <span className="stat-value">{boundingBoxResult.lines.length}</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">Total Words:</span>
            <span className="stat-value">{boundingBoxResult.total_words}</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">Processing Time:</span>
            <span className="stat-value">{boundingBoxResult.total_processing_time}ms</span>
          </div>
        </div>
      </div>
    </div>
  );
}; 