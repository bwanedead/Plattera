import React from 'react';
import { AlignmentResult } from '../../types/imageProcessing';

interface AlignmentPanelProps {
  alignmentResult: AlignmentResult | null;
  showHeatmap: boolean;
  onToggleHeatmap: (show: boolean) => void;
  onClose: () => void;
}

export const AlignmentPanel: React.FC<AlignmentPanelProps> = ({
  alignmentResult,
  showHeatmap,
  onToggleHeatmap,
  onClose
}) => {
  if (!alignmentResult || !alignmentResult.success) {
    return (
      <div className="alignment-panel">
        <div className="alignment-panel-header">
          <h3>Alignment Analysis</h3>
          <button className="panel-close-btn" onClick={onClose}>
            ×
          </button>
        </div>
        <div className="alignment-panel-content">
          <div className="alignment-error">
            <p>Alignment failed or not available</p>
            {alignmentResult?.error && (
              <p className="error-message">{alignmentResult.error}</p>
            )}
          </div>
        </div>
      </div>
    );
  }

  const { summary } = alignmentResult;
  const confidencePercentage = Math.round(summary.average_confidence * 100);
  
  // Calculate quality color based on confidence
  const getQualityColor = (confidence: number) => {
    if (confidence >= 0.8) return 'high-quality';
    if (confidence >= 0.5) return 'medium-quality';
    return 'low-quality';
  };

  const qualityColor = getQualityColor(summary.average_confidence);

  return (
    <div className="alignment-panel">
      <div className="alignment-panel-header">
        <h3>Alignment Analysis</h3>
        <button className="panel-close-btn" onClick={onClose}>
          ×
        </button>
      </div>
      
      <div className="alignment-panel-content">
        <div className="alignment-stats">
          <div className="stat-item">
            <span className="stat-label">Average Confidence</span>
            <span className={`stat-value ${qualityColor}`}>
              {confidencePercentage}%
            </span>
          </div>
          
          <div className="stat-item">
            <span className="stat-label">Total Positions</span>
            <span className="stat-value">{summary.total_positions}</span>
          </div>
          
          <div className="stat-item">
            <span className="stat-label">Differences Found</span>
            <span className="stat-value">{summary.total_differences}</span>
          </div>
          
          <div className="stat-item">
            <span className="stat-label">Quality Assessment</span>
            <span className={`stat-value ${qualityColor}`}>
              {summary.quality_assessment}
            </span>
          </div>
        </div>

        <div className="confidence-breakdown">
          <h4>Confidence Breakdown</h4>
          <div className="confidence-bars">
            <div className="confidence-bar">
              <span className="confidence-label">High (80-100%)</span>
              <div className="confidence-bar-track">
                <div 
                  className="confidence-bar-fill high-confidence"
                  style={{ 
                    width: `${(summary.high_confidence_positions / summary.total_positions) * 100}%` 
                  }}
                ></div>
              </div>
              <span className="confidence-count">{summary.high_confidence_positions}</span>
            </div>
            
            <div className="confidence-bar">
              <span className="confidence-label">Medium (50-79%)</span>
              <div className="confidence-bar-track">
                <div 
                  className="confidence-bar-fill medium-confidence"
                  style={{ 
                    width: `${(summary.medium_confidence_positions / summary.total_positions) * 100}%` 
                  }}
                ></div>
              </div>
              <span className="confidence-count">{summary.medium_confidence_positions}</span>
            </div>
            
            <div className="confidence-bar">
              <span className="confidence-label">Low (0-49%)</span>
              <div className="confidence-bar-track">
                <div 
                  className="confidence-bar-fill low-confidence"
                  style={{ 
                    width: `${(summary.low_confidence_positions / summary.total_positions) * 100}%` 
                  }}
                ></div>
              </div>
              <span className="confidence-count">{summary.low_confidence_positions}</span>
            </div>
          </div>
        </div>

        <div className="heatmap-controls">
          <h4>Visualization</h4>
          <label className="heatmap-toggle">
            <input
              type="checkbox"
              checked={showHeatmap}
              onChange={(e) => onToggleHeatmap(e.target.checked)}
            />
            <span className="toggle-slider"></span>
            <span className="toggle-label">Show Confidence Heatmap</span>
          </label>
          <p className="heatmap-hint">
            Highlight text with colors based on alignment confidence
          </p>
        </div>

        <div className="processing-info">
          <span className="processing-time">
            Processed in {alignmentResult.processing_time.toFixed(2)}s
          </span>
        </div>
      </div>
    </div>
  );
}; 