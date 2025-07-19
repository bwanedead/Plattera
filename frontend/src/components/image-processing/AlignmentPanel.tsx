import React from 'react';
import { AlignmentResult } from '../../types/imageProcessing';

interface AlignmentPanelProps {
  alignmentResult: AlignmentResult | null;
  showHeatmap: boolean;
  onToggleHeatmap: (show: boolean) => void;
  onClose: () => void;
  onToggleAlignmentTable: (show: boolean) => void;
  boundingBoxResult: {
    success: boolean;
    lines: Array<{
      line_index: number;
      bounds: { y1: number; y2: number; x1: number; x2: number };
      confidence: number;
    }>;
    words_by_line: Array<{
      line_index: number;
      line_bounds: { y1: number; y2: number; x1: number; x2: number };
      words: Array<{
        word: string;
        bounds: { x1: number; y1: number; x2: number; y2: number };
        confidence: number;
      }>;
      processing_time: number;
    }>;
    total_processing_time: number;
    total_words: number;
    error?: string;
  } | null;
  onGenerateBoundingBoxes: () => void;
  onToggleBoundingBoxViewer: (show: boolean) => void;
  isProcessing: boolean;
}

export const AlignmentPanel: React.FC<AlignmentPanelProps> = ({
  alignmentResult,
  showHeatmap,
  onToggleHeatmap,
  onClose,
  onToggleAlignmentTable,
  boundingBoxResult,
  onGenerateBoundingBoxes,
  onToggleBoundingBoxViewer,
  isProcessing,
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

  // --- Map backend property names to frontend expectations ---
  const summary = {
    average_confidence: alignmentResult.summary.average_confidence_score ?? 0,
    total_positions: alignmentResult.summary.total_positions_analyzed ?? 0,
    total_differences: alignmentResult.summary.total_differences_found ?? 0,
    quality_assessment: alignmentResult.summary.quality_assessment ?? 'N/A',
    high_confidence_positions: alignmentResult.summary.confidence_distribution?.high ?? 0,
    medium_confidence_positions: alignmentResult.summary.confidence_distribution?.medium ?? 0,
    low_confidence_positions: alignmentResult.summary.confidence_distribution?.low ?? 0,
  };
  
  const confidencePercentage = (summary.average_confidence * 100).toFixed(1);
  
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
                    width: `${summary.total_positions > 0 ? (summary.high_confidence_positions / summary.total_positions) * 100 : 0}%` 
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
                    width: `${summary.total_positions > 0 ? (summary.medium_confidence_positions / summary.total_positions) * 100 : 0}%` 
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
                    width: `${summary.total_positions > 0 ? (summary.low_confidence_positions / summary.total_positions) * 100 : 0}%` 
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
          <button 
            className="view-table-btn"
            onClick={() => onToggleAlignmentTable(true)}
          >
            View Alignment Table
          </button>
        </div>

        <div className="bounding-box-controls">
          <h4>Bounding Box Analysis</h4>
          
          {boundingBoxResult ? (
            <>
              <div className="bounding-box-stats">
                <div className="stat-item">
                  <span className="stat-label">Lines:</span>
                  <span className="stat-value">{boundingBoxResult.lines.length}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Words:</span>
                  <span className="stat-value">{boundingBoxResult.total_words}</span>
                </div>
                <div className="stat-item">
                  <span className="stat-label">Time:</span>
                  <span className="stat-value">{boundingBoxResult.total_processing_time}ms</span>
                </div>
              </div>
              
              <button 
                className="view-bounding-boxes-btn"
                onClick={() => onToggleBoundingBoxViewer(true)}
              >
                View Bounding Boxes
              </button>
            </>
          ) : (
            <button 
              className="generate-bounding-boxes-btn"
              onClick={onGenerateBoundingBoxes}
              disabled={isProcessing}
            >
              Generate Bounding Boxes
            </button>
          )}
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