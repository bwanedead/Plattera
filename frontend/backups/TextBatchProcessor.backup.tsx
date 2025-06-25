import React, { useState } from 'react'

interface TextItem {
  id: string
  text: string
  parcelId?: string
}

interface ProcessingResult {
  id: string
  input: string
  result: any
  status: 'processing' | 'completed' | 'error'
  error?: string
}

interface TextBatchProcessorProps {
  onResults: (results: ProcessingResult[]) => void
}

const TextBatchProcessor: React.FC<TextBatchProcessorProps> = ({ onResults }) => {
  const [textItems, setTextItems] = useState<TextItem[]>([])
  const [processing, setProcessing] = useState(false)

  const addTextItem = () => {
    const newItem: TextItem = {
      id: `text_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      text: '',
      parcelId: ''
    }
    setTextItems(prev => [...prev, newItem])
  }

  const updateTextItem = (id: string, field: keyof TextItem, value: string) => {
    setTextItems(prev => 
      prev.map(item => 
        item.id === id ? { ...item, [field]: value } : item
      )
    )
  }

  const removeTextItem = (id: string) => {
    setTextItems(prev => prev.filter(item => item.id !== id))
  }

  const processAllTexts = async () => {
    if (textItems.length === 0 || processing) return

    setProcessing(true)
    const results: ProcessingResult[] = []

    for (const item of textItems) {
      if (!item.text.trim()) continue

      try {
        const response = await fetch('http://localhost:8000/api/process/text-to-schema', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            text: item.text,
            parcel_id: item.parcelId || undefined
          })
        })

        const data = await response.json()
        
        if (response.ok) {
          results.push({
            id: item.id,
            input: item.text,
            result: data.parcel_data,
            status: 'completed'
          })
        } else {
          results.push({
            id: item.id,
            input: item.text,
            result: null,
            status: 'error',
            error: data.detail || 'Processing failed'
          })
        }
      } catch (error) {
        results.push({
          id: item.id,
          input: item.text,
          result: null,
          status: 'error',
          error: `Network error: ${error.message}`
        })
      }
    }

    setProcessing(false)
    onResults(results)
  }

  return (
    <div className="text-batch-processor">
      <div className="processor-header">
        <h2>Plain Text Processor</h2>
        <p>Add one or more legal descriptions to process</p>
      </div>

      <div className="batch-controls">
        <button onClick={addTextItem} disabled={processing}>
          + Add Text Input
        </button>
        <button 
          onClick={processAllTexts}
          disabled={textItems.length === 0 || processing}
          className="process-button"
        >
          {processing ? 'Processing...' : `Process ${textItems.length} Item${textItems.length !== 1 ? 's' : ''}`}
        </button>
      </div>

      <div className="text-items">
        {textItems.map((item, index) => (
          <div key={item.id} className="text-item">
            <div className="text-item-header">
              <h4>Text Input #{index + 1}</h4>
              <button 
                onClick={() => removeTextItem(item.id)}
                className="remove-button"
                disabled={processing}
              >
                ✕
              </button>
            </div>

            <div className="text-item-fields">
              <div className="field-group">
                <label>Parcel ID (optional):</label>
                <input
                  type="text"
                  value={item.parcelId || ''}
                  onChange={(e) => updateTextItem(item.id, 'parcelId', e.target.value)}
                  placeholder="Leave blank for auto-generation"
                  disabled={processing}
                />
              </div>

              <div className="field-group">
                <label>Legal Description:</label>
                <textarea
                  value={item.text}
                  onChange={(e) => updateTextItem(item.id, 'text', e.target.value)}
                  placeholder="Paste legal property description here..."
                  rows={8}
                  disabled={processing}
                  required
                />
              </div>
            </div>
          </div>
        ))}

        {textItems.length === 0 && (
          <div className="empty-state">
            <p>No text inputs added yet. Click "Add Text Input" to get started.</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default TextBatchProcessor 