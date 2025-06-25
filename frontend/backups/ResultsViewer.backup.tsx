import React, { useState } from 'react'

interface ProcessingResult {
  id: string
  input: string
  result: any
  status: 'processing' | 'completed' | 'error'
  error?: string
}

interface ResultsViewerProps {
  results: ProcessingResult[]
}

const ResultsViewer: React.FC<ResultsViewerProps> = ({ results }) => {
  const [selectedResult, setSelectedResult] = useState<ProcessingResult | null>(null)
  const [viewMode, setViewMode] = useState<'text' | 'metadata'>('text')

  if (results.length === 0) {
    return null
  }

  const completedResults = results.filter(r => r.status === 'completed')
  const errorResults = results.filter(r => r.status === 'error')

  return (
    <div className="results-viewer">
      <div className="results-header">
        <h2>Processing Results</h2>
        <div className="results-summary">
          <span className="success-count">{completedResults.length} successful</span>
          {errorResults.length > 0 && (
            <span className="error-count">{errorResults.length} failed</span>
          )}
        </div>
      </div>

      <div className="results-list">
        {results.map((result) => (
          <div key={result.id} className={`result-item ${result.status}`}>
            <div className="result-header">
              <div className="result-info">
                <h4>{result.input}</h4>
                <span className={`status-badge ${result.status}`}>
                  {result.status}
                </span>
              </div>
              {result.status === 'completed' && (
                <button 
                  onClick={() => setSelectedResult(result)}
                  className="view-button"
                >
                  View Details
                </button>
              )}
            </div>

            {result.status === 'error' && (
              <div className="error-message">
                <p>Error: {result.error}</p>
              </div>
            )}

            {result.status === 'completed' && (
              <div className="result-preview">
                <div className="text-preview">
                  <p>{result.result.extracted_text?.substring(0, 200)}...</p>
                </div>
                <div className="result-stats">
                  <span>Words: {result.result.pipeline_stats?.word_count || 0}</span>
                  <span>Tokens: {result.result.pipeline_stats?.tokens_used || 0}</span>
                  <span>Confidence: {((result.result.pipeline_stats?.confidence || 0) * 100).toFixed(1)}%</span>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Detailed View Modal */}
      {selectedResult && (
        <div className="modal-overlay" onClick={() => setSelectedResult(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{selectedResult.input}</h3>
              <div className="view-mode-toggle">
                <button 
                  className={viewMode === 'text' ? 'active' : ''}
                  onClick={() => setViewMode('text')}
                >
                  Extracted Text
                </button>
                <button 
                  className={viewMode === 'metadata' ? 'active' : ''}
                  onClick={() => setViewMode('metadata')}
                >
                  Metadata
                </button>
              </div>
              <button 
                onClick={() => setSelectedResult(null)}
                className="close-button"
              >
                ✕
              </button>
            </div>

            <div className="modal-body">
              {viewMode === 'text' ? (
                <div className="extracted-text-view">
                  <div className="text-actions">
                    <button onClick={() => navigator.clipboard.writeText(selectedResult.result.extracted_text)}>
                      📋 Copy Text
                    </button>
                  </div>
                  <pre className="extracted-text">
                    {selectedResult.result.extracted_text}
                  </pre>
                </div>
              ) : (
                <div className="metadata-view">
                  <pre className="metadata-json">
                    {JSON.stringify(selectedResult.result, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default ResultsViewer 