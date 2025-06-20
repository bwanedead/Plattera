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

  const completedResults = results.filter(r => r.status === 'completed')
  const errorResults = results.filter(r => r.status === 'error')

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
            onClick={() => setSelectedResult(selectedResult === result.id ? null : result.id)}
          >
            <div className="result-summary">
              <span className="result-status">
                {result.status === 'completed' ? '✓' : '✗'}
              </span>
              <span className="result-preview">
                {result.input.substring(0, 80)}...
              </span>
            </div>

            {selectedResult === result.id && (
              <div className="result-details">
                {result.status === 'completed' ? (
                  <pre className="json-output">
                    {JSON.stringify(result.result, null, 2)}
                  </pre>
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