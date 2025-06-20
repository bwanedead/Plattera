import React from 'react'

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
  return (
    <div className="image-batch-processor">
      <div className="processor-header">
        <h2>Image Processor</h2>
        <p>Upload handwritten or scanned legal descriptions</p>
      </div>

      <div className="coming-soon">
        <div className="coming-soon-content">
          <h3>🚧 Coming Soon</h3>
          <p>Image processing and OCR functionality will be available in a future update.</p>
          <p>For now, please use the Plain Text processor to test the system.</p>
        </div>
      </div>
    </div>
  )
}

export default ImageBatchProcessor 