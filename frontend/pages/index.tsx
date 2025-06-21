import React, { useState } from 'react'
import TextBatchProcessor from '../src/components/TextBatchProcessor'
import ImageBatchProcessor from '../src/components/ImageBatchProcessor'
import ResultsViewer from '../src/components/ResultsViewer'

type EntryPoint = 'text' | 'image' | null
type ProcessingResult = {
  id: string
  input: string
  result: any
  status: 'processing' | 'completed' | 'error'
  error?: string
}

const App: React.FC = () => {
  const [entryPoint, setEntryPoint] = useState<EntryPoint>(null)
  const [results, setResults] = useState<ProcessingResult[]>([])

  const handleBackToMenu = () => {
    setEntryPoint(null)
  }

  const handleTextResults = (newResults: ProcessingResult[]) => {
    setResults(prev => [...prev, ...newResults])
  }

  const handleImageResults = (newResults: ProcessingResult[]) => {
    setResults(prev => [...prev, ...newResults])
  }

  return (
    <div className="app-container">
      <div className="app-header">
        <h1>Plattera</h1>
        <p>Legal Property Description Processor</p>
        {entryPoint && (
          <button onClick={handleBackToMenu} className="back-button">
            ← Back to Menu
          </button>
        )}
      </div>

      <div className="app-content">
        {!entryPoint && (
          <div className="entry-point-selector">
            <h2>Choose Entry Point</h2>
            <div className="entry-options">
              <div 
                className="entry-card"
                onClick={() => setEntryPoint('text')}
              >
                <div className="entry-icon">📝</div>
                <h3>Plain Text</h3>
                <p>Import typed/digitized legal descriptions</p>
                <p className="entry-note">Ready for testing</p>
              </div>

              <div
                className="entry-card"
                onClick={() => setEntryPoint('image')}
              >
                <div className="entry-icon">📷</div>
                <h3>Handwritten Images</h3>
                <p>Upload scanned documents or photos</p>
                <p className="entry-note">Beta</p>
              </div>
            </div>
          </div>
        )}

        {entryPoint === 'text' && (
          <TextBatchProcessor onResults={handleTextResults} />
        )}

        {entryPoint === 'image' && (
          <ImageBatchProcessor onResults={handleImageResults} />
        )}

        {results.length > 0 && (
          <ResultsViewer results={results} />
        )}
      </div>
    </div>
  )
}

export default App 