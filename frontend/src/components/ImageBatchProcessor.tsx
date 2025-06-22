import React, { useState } from 'react'

interface ProcessingResult {
  id: string
  input: string
  result: any
  status: 'processing' | 'completed' | 'error'
  error?: string
}

interface ImageBatchProcessorProps {
  onResults: (results: ProcessingResult[]) => void
}

const ImageBatchProcessor: React.FC<ImageBatchProcessorProps> = ({ onResults }) => {
  const [processing, setProcessing] = useState(false)
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || [])
    setSelectedFiles(prev => [...prev, ...files])
  }

  const removeFile = (index: number) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index))
  }

  const processImages = async () => {
    if (selectedFiles.length === 0) return

    setProcessing(true)
    const results: ProcessingResult[] = []

    for (const file of selectedFiles) {
      try {
        const formData = new FormData()
        formData.append('file', file)
        formData.append('extraction_mode', 'legal_document')
        formData.append('cleanup_after', 'true')

        const response = await fetch('http://localhost:8000/api/image/process', {
          method: 'POST',
          body: formData
        })

        const data = await response.json()

        if (data.status === 'success') {
          results.push({
            id: `img_${Date.now()}_${Math.random()}`,
            input: file.name,
            result: {
              extracted_text: data.extracted_text,
              file_info: data.file_info,
              processing_info: data.processing_info,
              pipeline_stats: data.pipeline_stats
            },
            status: 'completed'
          })
        } else {
          results.push({
            id: `img_${Date.now()}_${Math.random()}`,
            input: file.name,
            result: null,
            status: 'error',
            error: data.error || 'Processing failed'
          })
        }
      } catch (error) {
        results.push({
          id: `img_${Date.now()}_${Math.random()}`,
          input: file.name,
          result: null,
          status: 'error',
          error: error instanceof Error ? error.message : 'Unknown error'
        })
      }
    }

    onResults(results)
    setProcessing(false)
    setSelectedFiles([]) // Clear files after processing
  }

  return (
    <div className="image-batch-processor">
      <div className="processor-header">
        <h2>Image Processor</h2>
        <p>Upload handwritten or scanned legal descriptions</p>
      </div>

      <div className="batch-controls">
        <input
          type="file"
          accept="image/*,.pdf"
          multiple
          onChange={handleFileSelect}
          disabled={processing}
          style={{ display: 'none' }}
          id="file-input"
        />
        <label htmlFor="file-input" className={`file-select-button ${processing ? 'disabled' : ''}`}>
          📁 Select Images/PDFs
        </label>
        <button 
          onClick={processImages}
          disabled={selectedFiles.length === 0 || processing}
          className="process-button"
        >
          {processing ? 'Processing...' : `Process ${selectedFiles.length} File${selectedFiles.length !== 1 ? 's' : ''}`}
        </button>
      </div>

      <div className="file-list">
        {selectedFiles.map((file, index) => (
          <div key={index} className="file-item">
            <div className="file-info">
              <span className="file-name">{file.name}</span>
              <span className="file-size">({(file.size / 1024 / 1024).toFixed(1)}MB)</span>
            </div>
            <button 
              onClick={() => removeFile(index)}
              className="remove-button"
              disabled={processing}
            >
              ✕
            </button>
          </div>
        ))}

        {selectedFiles.length === 0 && (
          <div className="empty-state">
            <p>No files selected. Click "Select Images/PDFs" to get started.</p>
            <p className="format-note">Supported formats: JPEG, PNG, WEBP, PDF (up to 20MB each)</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default ImageBatchProcessor 