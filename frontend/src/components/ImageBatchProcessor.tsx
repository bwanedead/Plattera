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

interface ImageItem {
  id: string
  file: File
}

const ImageBatchProcessor: React.FC<ImageBatchProcessorProps> = ({ onResults }) => {
  const [imageItems, setImageItems] = useState<ImageItem[]>([])
  const [processing, setProcessing] = useState(false)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files) return

    const newItems: ImageItem[] = Array.from(files).map((file) => ({
      id: `${file.name}_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`,
      file,
    }))
    setImageItems((prev) => [...prev, ...newItems])
  }

  const removeItem = (id: string) => {
    setImageItems((prev) => prev.filter((item) => item.id !== id))
  }

  const processImages = async () => {
    if (imageItems.length === 0 || processing) return
    setProcessing(true)

    const results: ProcessingResult[] = []
    for (const item of imageItems) {
      const formData = new FormData()
      formData.append('file', item.file)
      formData.append('extraction_mode', 'legal_document')
      formData.append('cleanup_after', 'true')

      try {
        const response = await fetch('http://localhost:8000/api/image/process', {
          method: 'POST',
          body: formData,
        })

        const data = await response.json()

        if (response.ok && data.extracted_text) {
          results.push({
            id: item.id,
            input: item.file.name,
            result: data.extracted_text,
            status: 'completed',
          })
        } else {
          results.push({
            id: item.id,
            input: item.file.name,
            result: null,
            status: 'error',
            error: data.detail || 'Processing failed',
          })
        }
      } catch (err: any) {
        results.push({
          id: item.id,
          input: item.file.name,
          result: null,
          status: 'error',
          error: `Network error: ${err.message}`,
        })
      }
    }

    setProcessing(false)
    setImageItems([])
    onResults(results)
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
          multiple
          accept="image/*,.pdf"
          onChange={handleFileChange}
          disabled={processing}
        />
        <button onClick={processImages} disabled={imageItems.length === 0 || processing} className="process-button">
          {processing ? 'Processing...' : `Process ${imageItems.length} Item${imageItems.length !== 1 ? 's' : ''}`}
        </button>
      </div>

      {imageItems.length > 0 && (
        <div className="text-items">
          {imageItems.map((item) => (
            <div key={item.id} className="text-item">
              <div className="text-item-header">
                <h4>{item.file.name}</h4>
                <button className="remove-button" onClick={() => removeItem(item.id)} disabled={processing}>
                  ✕
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default ImageBatchProcessor 