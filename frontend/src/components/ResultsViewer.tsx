import React, { useState } from 'react';
import { Allotment } from 'allotment';
import "allotment/dist/style.css";
import { ParcelTracerLoader } from './ParcelTracerLoader';
import { CopyButton } from './CopyButton';
import { DraftSelector } from './DraftSelector';
import { formatJsonPretty } from '../utils/jsonFormatter';

// Define interfaces for props to ensure type safety
interface ResultsViewerProps {
  isProcessing: boolean;
  sessionResults: any[];
  selectedResult: any;
  onSelectResult: (result: any) => void;
  isHistoryVisible: boolean;
  onToggleHistory: (visible: boolean) => void;
  getCurrentText: () => string;
  getRawText: () => string;
  isCurrentResultJson: () => boolean;
  onSaveDraft: () => void;
  selectedDraft: number | 'consensus' | 'best';
  onDraftSelect: (draft: number | 'consensus' | 'best') => void;
}

export const ResultsViewer: React.FC<ResultsViewerProps> = ({
  isProcessing,
  sessionResults,
  selectedResult,
  onSelectResult,
  isHistoryVisible,
  onToggleHistory,
  getCurrentText,
  getRawText,
  isCurrentResultJson,
  onSaveDraft,
  selectedDraft,
  onDraftSelect,
}) => {
  const [activeTab, setActiveTab] = useState('text');

  return (
    <div className="results-area" style={{ width: '100%', height: '100%' }}>
      <Allotment defaultSizes={[300, 700]} vertical={false}>
        {isHistoryVisible && (
          <Allotment.Pane minSize={200} maxSize={500}>
            <div className="results-history-panel visible">
              <div className="history-header">
                <h4>Session Log</h4>
                <button onClick={() => onToggleHistory(false)}>‹</button>
              </div>
              <div className="history-list-items">
                {sessionResults.map((res, i) => (
                  <div
                    key={i}
                    className={`log-item ${
                      selectedResult === res ? 'selected' : ''
                    } ${res.status}`}
                    onClick={() => onSelectResult(res)}
                  >
                    <span className={`log-item-status-dot ${res.status}`}></span>
                    {res.input}
                  </div>
                ))}
              </div>
            </div>
          </Allotment.Pane>
        )}
        <Allotment.Pane>
          <div className="results-viewer-panel">
            {!isHistoryVisible && (
              <button
                className="history-toggle-button"
                onClick={() => onToggleHistory(true)}
              >
                ›
              </button>
            )}
            {isProcessing && (
              <div className="loading-view">
                <ParcelTracerLoader />
                <h4>Tracing Parcels...</h4>
                <p>Analyzing document geometry.</p>
              </div>
            )}
            {!isProcessing && !selectedResult && (
              <div className="placeholder-view">
                <p>Your results will appear here.</p>
              </div>
            )}
            {!isProcessing && selectedResult && (
              <div className="result-display-area">
                <CopyButton
                  onCopy={() => {
                    if (activeTab === 'text') {
                      navigator.clipboard.writeText(getCurrentText());
                    } else if (activeTab === 'json') {
                      navigator.clipboard.writeText(formatJsonPretty(getRawText()));
                    } else if (activeTab === 'metadata') {
                      navigator.clipboard.writeText(
                        selectedResult.status === 'completed'
                          ? JSON.stringify(selectedResult.result?.metadata, null, 2)
                          : 'No metadata available for failed processing.'
                      );
                    }
                  }}
                  title={`Copy ${activeTab}`}
                  style={{
                    position: 'absolute',
                    top: '5rem',
                    left: '-3rem',
                    zIndex: 20,
                  }}
                />

                <DraftSelector
                  redundancyAnalysis={
                    selectedResult.result?.metadata?.redundancy_analysis
                  }
                  onDraftSelect={onDraftSelect}
                  selectedDraft={selectedDraft}
                />

                <div className="result-tabs">
                  <button
                    className={activeTab === 'text' ? 'active' : ''}
                    onClick={() => setActiveTab('text')}
                  >
                    📄 Text
                  </button>
                  {isCurrentResultJson() && (
                    <button
                      className={activeTab === 'json' ? 'active' : ''}
                      onClick={() => setActiveTab('json')}
                    >
                      🔧 JSON
                    </button>
                  )}
                  <button
                    className={activeTab === 'metadata' ? 'active' : ''}
                    onClick={() => setActiveTab('metadata')}
                  >
                    📊 Metadata
                  </button>
                </div>

                <div className="result-tab-content">
                  {activeTab === 'text' && (
                    <div
                      className="text-viewer-pane"
                      style={{ height: '100%' }}
                    >
                      <pre>{getCurrentText()}</pre>
                    </div>
                  )}
                  {activeTab === 'json' && isCurrentResultJson() && (
                    <div className="json-display">
                      <div className="json-actions">
                        <button
                          className="save-draft-button"
                          onClick={onSaveDraft}
                          title="Save this draft for future alignment testing"
                        >
                          💾 Save Draft
                        </button>
                      </div>
                      <pre className="json-content">
                        {formatJsonPretty(getRawText())}
                      </pre>
                    </div>
                  )}
                  {activeTab === 'metadata' && (
                    <div className="metadata-display">
                      <pre>
                        {selectedResult.status === 'completed'
                          ? JSON.stringify(
                              selectedResult.result?.metadata,
                              null,
                              2
                            )
                          : 'No metadata available for failed processing.'}
                      </pre>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </Allotment.Pane>
      </Allotment>
    </div>
  );
}; 