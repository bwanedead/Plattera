import React, { useState } from 'react'
import TextInputForm from '../components/TextInputForm'
import ProcessingStatus from '../components/ProcessingStatus'

const ProcessPage: React.FC = () => {
  const [isProcessing, setIsProcessing] = useState(false)
  const [results, setResults] = useState(null)

  const handleTextSubmit = async (text: string) => {
    setIsProcessing(true)
    
    try {
      // TODO: Call API to process text
      console.log('Processing text:', text)
      
      // Simulate processing delay
      await new Promise(resolve => setTimeout(resolve, 2000))
      
      setResults({ message: 'Processing complete!' })
    } catch (error) {
      console.error('Processing error:', error)
    } finally {
      setIsProcessing(false)
    }
  }

  return (
    <div className="page">
      <div className="container">
        <h1>Process Legal Description</h1>
        <TextInputForm onSubmit={handleTextSubmit} disabled={isProcessing} />
        {isProcessing && <ProcessingStatus />}
        {results && (
          <div className="results">
            <h3>Results</h3>
            <pre>{JSON.stringify(results, null, 2)}</pre>
          </div>
        )}
      </div>
    </div>
  )
}

export default ProcessPage 