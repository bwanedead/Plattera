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
  const [selectedResult, setSelectedResult] = useState<string | null>(null)
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const completedResults = results.filter(r => r.status === 'completed')
  const errorResults = results.filter(r => r.status === 'error')

  const handleCopyToClipboard = async (text: string, resultId: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedId(resultId)
      setTimeout(() => setCopiedId(null), 2000) // Reset after 2 seconds
    } catch (err) {
      console.error('Failed to copy text: ', err)
      // Fallback for older browsers
      const textArea = document.createElement('textarea')
      textArea.value = text
      document.body.appendChild(textArea)
      textArea.select()
      try {
        document.execCommand('copy')
        setCopiedId(resultId)
        setTimeout(() => setCopiedId(null), 2000)
      } catch (fallbackErr) {
        console.error('Fallback copy failed: ', fallbackErr)
      }
      document.body.removeChild(textArea)
    }
  }

  return (
    <div className="results-viewer">
      <div className="results-header">
        <h2>Processing Results</h2>
        <div className="results-summary">
          <span className="success-count">✓ {completedResults.length} successful</span>
          {errorResults.length > 0 && (
            <span className="error-count">✗ {errorResults.length} failed</span>
          )}
        </div>
      </div>

      <div className="results-list">
        {results.map((result) => (
          <div 
            key={result.id} 
            className={`result-item ${result.status}`}
          >
            <div 
              className="result-summary"
              onClick={() => setSelectedResult(selectedResult === result.id ? null : result.id)}
            >
              <span className="result-status">
                {result.status === 'completed' ? '✓' : '✗'}
              </span>
              <span className="result-preview">
                {result.input.substring(0, 80)}...
              </span>
              <span className="expand-indicator">
                {selectedResult === result.id ? '▼' : '▶'}
              </span>
            </div>

            {selectedResult === result.id && (
              <div 
                className="result-details"
                onClick={(e) => e.stopPropagation()} // Prevent closing when clicking on details
              >
                {result.status === 'completed' ? (
                  <div className="json-container">
                    <div className="json-header">
                      <span className="json-title">{typeof result.result === 'string' ? 'Extracted Text' : 'Structured Schema Output'}</span>
                      <button
                        className="copy-button"
                        onClick={() => handleCopyToClipboard(typeof result.result === 'string' ? result.result : JSON.stringify(result.result, null, 2), result.id)}
                        title="Copy to clipboard"
                      >
                        {copiedId === result.id ? '✓ Copied!' : '📋 Copy'}
                      </button>
                    </div>
                    <pre className="json-output">
                      {typeof result.result === 'string'
                        ? result.result
                        : JSON.stringify(result.result, null, 2)}
                    </pre>
                  </div>
                ) : (
                  <div className="error-details">
                    <strong>Error:</strong> {result.error}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export default ResultsViewer 