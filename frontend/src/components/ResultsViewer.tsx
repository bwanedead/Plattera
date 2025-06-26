import React, { useState } from 'react'
import { 
  isJsonResult, 
  formatJsonAsText, 
  formatJsonPretty, 
  getWordCount, 
  extractDisplayMetadata,
  ProcessingResult as FormatterProcessingResult
} from '../utils/jsonFormatter'

interface ProcessingResult {
  id: string
  input: string
  result: FormatterProcessingResult
  status: 'processing' | 'completed' | 'error'
  error?: string
}

interface ResultsViewerProps {
  results: ProcessingResult[]
}

type ViewMode = 'text' | 'json' | 'metadata'

const ResultsViewer: React.FC<ResultsViewerProps> = ({ results }) => {
  const [selectedResult, setSelectedResult] = useState<ProcessingResult | null>(null)
  const [viewMode, setViewMode] = useState<ViewMode>('text')

  if (results.length === 0) {
    return null
  }

  const completedResults = results.filter(r => r.status === 'completed')
  const errorResults = results.filter(r => r.status === 'error')

  const getDisplayText = (result: FormatterProcessingResult): string => {
    if (isJsonResult(result.extracted_text)) {
      return formatJsonAsText(result.extracted_text)
    }
    return result.extracted_text
  }

  const getPreviewText = (result: FormatterProcessingResult): string => {
    const displayText = getDisplayText(result)
    return displayText.substring(0, 200) + (displayText.length > 200 ? '...' : '')
  }

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
    } catch (err) {
      console.error('Failed to copy text:', err)
    }
  }

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
                {result.status === 'completed' && isJsonResult(result.result.extracted_text) && (
                  <span className="format-badge json">JSON</span>
                )}
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
                  <p>{getPreviewText(result.result)}</p>
                </div>
                <div className="result-stats">
                  <span>Words: {getWordCount(result.result.extracted_text)}</span>
                  <span>Tokens: {result.result.tokens_used || result.result.pipeline_stats?.tokens_used || 0}</span>
                  <span>Confidence: {((result.result.confidence_score || result.result.pipeline_stats?.confidence || 0) * 100).toFixed(1)}%</span>
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
                  📄 Text
                </button>
                {isJsonResult(selectedResult.result.extracted_text) && (
                  <button 
                    className={viewMode === 'json' ? 'active' : ''}
                    onClick={() => setViewMode('json')}
                  >
                    🔧 JSON
                  </button>
                )}
                <button 
                  className={viewMode === 'metadata' ? 'active' : ''}
                  onClick={() => setViewMode('metadata')}
                >
                  📊 Metadata
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
              {viewMode === 'text' && (
                <div className="text-view">
                  <div className="text-actions">
                    <button onClick={() => copyToClipboard(getDisplayText(selectedResult.result))}>
                      📋 Copy Text
                    </button>
                    {isJsonResult(selectedResult.result.extracted_text) && (
                      <span className="format-info">
                        ✨ Formatted from JSON structure
                      </span>
                    )}
                  </div>
                  <div className="formatted-text">
                    {getDisplayText(selectedResult.result).split('\n').map((line, index) => {
                      // Check if line is a section divider (contains only dashes)
                      if (/^─+$/.test(line.trim())) {
                        return <hr key={index} className="section-divider" />
                      }
                      // Empty lines for spacing
                      if (!line.trim()) {
                        return <div key={index} className="line-break" />
                      }
                      // Regular text lines
                      return <p key={index} className="text-line">{line}</p>
                    })}
                  </div>
                </div>
              )}

              {viewMode === 'json' && isJsonResult(selectedResult.result.extracted_text) && (
                <div className="json-view">
                  <div className="json-actions">
                    <button onClick={() => copyToClipboard(formatJsonPretty(selectedResult.result.extracted_text))}>
                      📋 Copy JSON
                    </button>
                    <button onClick={() => copyToClipboard(selectedResult.result.extracted_text)}>
                      📋 Copy Raw
                    </button>
                  </div>
                  <pre className="json-content">
                    {formatJsonPretty(selectedResult.result.extracted_text)}
                  </pre>
                </div>
              )}

              {viewMode === 'metadata' && (
                <div className="metadata-view">
                  <div className="metadata-actions">
                    <button onClick={() => copyToClipboard(JSON.stringify(extractDisplayMetadata(selectedResult.result), null, 2))}>
                      📋 Copy Metadata
                    </button>
                  </div>
                  <div className="metadata-grid">
                    {Object.entries(extractDisplayMetadata(selectedResult.result)).map(([key, value]) => (
                      <div key={key} className="metadata-item">
                        <span className="metadata-key">{key}:</span>
                        <span className="metadata-value">{String(value)}</span>
                      </div>
                    ))}
                  </div>
                  <div className="raw-metadata">
                    <h4>Full Processing Result</h4>
                    <pre className="metadata-json">
                      {JSON.stringify(selectedResult.result, null, 2)}
                    </pre>
                  </div>
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