import React from 'react';

interface AlignmentData {
  alignment_results: any;
  confidence_results: any;
  summary: {
    processing_time_seconds?: number;
    total_blocks_processed?: number;
    total_positions_analyzed?: number;
    total_differences_found?: number;
    average_confidence_score?: number;
    accuracy_percentage?: number;
    quality_assessment?: string;
    confidence_distribution?: {
      high?: number;
      medium?: number;
      low?: number;
    };
    difference_categories?: {
      coordinate_differences?: number;
      word_differences?: number;
      punctuation_differences?: number;
      other_differences?: number;
    };
    alignment_method?: string;
    estimated_tcoffee_accuracy?: string;
  };
  processing_time?: number;
}

interface AlignmentAnalysisPanelProps {
  alignmentData: AlignmentData | null;
  isVisible: boolean;
  onClose: () => void;
}

export const AlignmentAnalysisPanel: React.FC<AlignmentAnalysisPanelProps> = ({
  alignmentData,
  isVisible,
  onClose
}) => {
  console.log('🔥 AlignmentAnalysisPanel render:', { isVisible, alignmentData });

  if (!isVisible || !alignmentData) {
    return null;
  }

  const { summary, processing_time } = alignmentData;

  // Map new summary fields to old variable names for UI
  const safeSummary = {
    total_positions: summary?.total_positions_analyzed || 0,
    high_confidence_positions: summary?.confidence_distribution?.high || 0,
    medium_confidence_positions: summary?.confidence_distribution?.medium || 0,
    low_confidence_positions: summary?.confidence_distribution?.low || 0,
    agreement_percentage: summary?.accuracy_percentage || 0,
    total_differences: summary?.total_differences_found || 0,
  };
  const safeProcessingTime = summary?.processing_time_seconds || processing_time || 0;

  console.log('🔥 AlignmentAnalysisPanel safeSummary:', safeSummary);

  return (
    <div className="alignment-analysis-panel">
      <div className="panel-header">
        <h3>🧬 BioPython Alignment Analysis</h3>
        <button className="close-button" onClick={onClose}>×</button>
      </div>
      
      <div className="panel-content">
        <div className="stats-section">
          <h4>📊 Confidence Statistics</h4>
          <div className="stat-item">
            <span className="stat-label">Total Positions:</span>
            <span className="stat-value">{safeSummary.total_positions}</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">Agreement:</span>
            <span className="stat-value">{safeSummary.agreement_percentage.toFixed(1)}%</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">Total Differences:</span>
            <span className="stat-value">{safeSummary.total_differences}</span>
          </div>
        </div>

        <div className="confidence-breakdown">
          <h4>🎯 Confidence Breakdown</h4>
          <div className="confidence-bar">
            <div 
              className="confidence-segment high" 
              style={{ 
                width: safeSummary.total_positions > 0 ? `${(safeSummary.high_confidence_positions / safeSummary.total_positions) * 100}%` : '0%'
              }}
              title={`High Confidence: ${safeSummary.high_confidence_positions} positions`}
            />
            <div 
              className="confidence-segment medium" 
              style={{ 
                width: safeSummary.total_positions > 0 ? `${(safeSummary.medium_confidence_positions / safeSummary.total_positions) * 100}%` : '0%'
              }}
              title={`Medium Confidence: ${safeSummary.medium_confidence_positions} positions`}
            />
            <div 
              className="confidence-segment low" 
              style={{ 
                width: safeSummary.total_positions > 0 ? `${(safeSummary.low_confidence_positions / safeSummary.total_positions) * 100}%` : '0%'
              }}
              title={`Low Confidence: ${safeSummary.low_confidence_positions} positions`}
            />
          </div>
          <div className="confidence-legend">
            <div className="legend-item">
              <div className="legend-color high"></div>
              <span>High ({safeSummary.high_confidence_positions})</span>
            </div>
            <div className="legend-item">
              <div className="legend-color medium"></div>
              <span>Medium ({safeSummary.medium_confidence_positions})</span>
            </div>
            <div className="legend-item">
              <div className="legend-color low"></div>
              <span>Low ({safeSummary.low_confidence_positions})</span>
            </div>
          </div>
        </div>

        <div className="processing-info">
          <h4>⚡ Processing Info</h4>
          <div className="stat-item">
            <span className="stat-label">Processing Time:</span>
            <span className="stat-value">{safeProcessingTime.toFixed(2)}s</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">Engine:</span>
            <span className="stat-value">BioPython MSA</span>
          </div>
        </div>
      </div>
    </div>
  );
}; 